#!/usr/bin/env python3
"""Validate configurable-depth UCE prefetch transactions in fst2vcd output.

UCE admission, forward-pump issue, and consumed responses are separate events.
Optional AXI evidence tracks accepted AR transactions through ordered R bursts
on the AXI clock, independently of the UCE clock. AXI acceptance overlap does
not establish parallel DRAM-bank service. Unknown controls, unmatched replies,
slot reuse, malformed bursts, and incomplete transactions invalidate the trace.
"""

import argparse
from collections import Counter, deque
import json
import sys

from cache_overlap_vcd import EvidenceError, rising_edges


UCE_SIGNALS = {
    'clock': 'clk_i', 'reset': 'reset_i',
    'request_v': 'cache_req_v_i', 'request_yumi': 'cache_req_yumi_o',
    'request_address': 'cache_req_cast_i.addr', 'request_type': 'cache_req_cast_i.msg_type',
    'allocate': 'prefetch_allocate', 'allocate_slot': 'prefetch_free_slot',
    'issue': 'prefetch_issue',
    'issue_slot': 'prefetch_issue_slot', 'response': 'prefetch_response',
    'fwd_v': 'fsm_fwd_v_lo', 'fwd_ready': 'fsm_fwd_ready_then_li',
    'fwd_new': 'fsm_fwd_new_lo', 'fwd_last': 'fsm_fwd_last_lo',
    'rev_v': 'fsm_rev_v_li', 'rev_yumi': 'fsm_rev_yumi_lo',
    'rev_new': 'fsm_rev_new_li', 'rev_last': 'fsm_rev_last_li',
}
OPTIONAL_UCE_SIGNALS = {
    # Older traces expose same-line merging. Current RTL acknowledges and drops
    # hints only when all configured slots are reserved.
    'duplicate': 'prefetch_duplicate',
    'drop': 'prefetch_drop',
}
for _side, _header in (('fwd', 'fsm_fwd_header_lo'), ('rev', 'fsm_rev_header_li')):
    # Verilator traces the BedRock message-type union through its members.
    for _label, _field in (('address', 'addr'), ('type', 'msg_type.' + _side), ('size', 'size'),
                           ('prefetch', 'payload.prefetch'), ('slot', 'payload.way_id'),
                           ('state', 'payload.state')):
        UCE_SIGNALS[_side + '_' + _label] = _header + '.' + _field

AXI_SIGNALS = {
    'axi_clock': 'clk_i', 'axi_reset': 'reset_i',
    'ar_v': 'axi_arvalid_i', 'ar_ready': 'axi_arready_o',
    'ar_address': 'axi_araddr_i', 'ar_id': 'axi_arid_i', 'ar_len': 'axi_arlen_i',
    'r_v': 'axi_rvalid_o', 'r_ready': 'axi_rready_i', 'r_id': 'axi_rid_o',
    'r_last': 'axi_rlast_o', 'r_resp': 'axi_rresp_o',
}


def signal_names(uce_prefix='dcache_uce', axi_prefix=None):
    names = {key: uce_prefix.rstrip('.') + '.' + suffix for key, suffix in UCE_SIGNALS.items()}
    names.update({key: uce_prefix.rstrip('.') + '.' + suffix
                  for key, suffix in OPTIONAL_UCE_SIGNALS.items()})
    if axi_prefix is not None:
        names.update({key: axi_prefix.rstrip('.') + '.' + suffix for key, suffix in AXI_SIGNALS.items()})
    return names


def read_header(stream, names, optional=()):
    """Resolve exact suffixes; never silently select one of several cores."""
    scopes, found, timescale = [], {}, []
    in_timescale = False
    for line in stream:
        words = line.split()
        if '$timescale' in line:
            in_timescale = True
        if in_timescale:
            timescale.extend(word for word in words if word not in ('$timescale', '$end'))
            if '$end' in line:
                in_timescale = False
        if words[:1] == ['$scope']:
            scopes.append(words[2])
        elif words[:1] == ['$upscope']:
            scopes.pop()
        elif words[:1] == ['$var']:
            full = '.'.join(scopes + [words[4]])
            for label, suffix in names.items():
                if full == suffix or full.endswith('.' + suffix):
                    found.setdefault(label, []).append((words[3], full))
        elif words[:1] == ['$enddefinitions']:
            break
    else:
        raise EvidenceError('missing VCD enddefinitions')
    for label, suffix in names.items():
        if label not in found:
            if label in optional:
                continue
            raise EvidenceError('missing required signal: ' + suffix)
        if len(found[label]) != 1:
            raise EvidenceError('ambiguous signal: ' + suffix)
    if not timescale:
        raise EvidenceError('missing VCD timescale')
    return {label: matches[0] for label, matches in found.items()}, ''.join(timescale)


def known(values, label):
    value = values.get(label)
    if value is None:
        raise EvidenceError('unknown ' + label)
    return value


def bit(values, label):
    value = known(values, label)
    if value not in (0, 1):
        raise EvidenceError('nonbinary control ' + label)
    return value


def boundary(cycle, timestamp):
    return dict(cycle=cycle, timestamp=timestamp)


def overlap_summary(records):
    """Strict open intervals exclude a response and new issue on one edge."""
    before_first, before_complete = [], []
    events = []
    for record in records:
        issue = record['issue']['timestamp']
        complete = record['complete']['timestamp']
        # Complete events sort before new issues at a shared edge.
        if complete > issue:
            events.extend(((issue, 1), (complete, -1)))
        for previous in record.pop('_prior', []):
            if previous['issue']['timestamp'] < issue < previous['first_response']['timestamp']:
                before_first.append([previous['id'], record['id']])
            if previous['issue']['timestamp'] < issue < previous['complete']['timestamp']:
                before_complete.append([previous['id'], record['id']])
    outstanding = maximum = 0
    for _, delta in sorted(events):
        outstanding += delta
        maximum = max(maximum, outstanding)
    return dict(transactions=len(records), max_outstanding=maximum,
                issue_before_prior_first_response=bool(before_first),
                issue_before_prior_completion=bool(before_complete),
                before_first_response_pairs=before_first, before_completion_pairs=before_complete)


def request_summary(records):
    """Summarize accepted non-prefetch UCE requests by type and 4 KiB page."""
    by_type = Counter(record['msg_type'] for record in records)
    by_page = Counter(record['address'] >> 12 for record in records)
    return dict(count=len(records),
                by_msg_type={str(key): value for key, value in sorted(by_type.items())},
                by_4k_page={hex(key << 12): value for key, value in sorted(by_page.items())})


def prefetch_demand_matches(prefetches, demands, line_bytes=64):
    """Correlate accepted hints with later normal L1 miss requests by line."""
    result = []
    for hint in prefetches:
        matches = [request for request in demands
                   if request['msg_type'] == 0
                   and request['address'] // line_bytes == hint['address'] // line_bytes
                   and request['timestamp'] > hint['issue']['timestamp']]
        result.append(dict(prefetch_id=hint['id'], address=hint['address'],
                           normal_miss_count=len(matches),
                           normal_miss_cycles=[request['cycle'] for request in matches]))
    return result


class Transactions:
    def __init__(self, line_bytes=64, fill_bytes=8, axi=False, prefetch_slots=2,
                 admission_mode='drop'):
        for name, value in (('line-bytes', line_bytes), ('fill-bytes', fill_bytes)):
            if value <= 0 or value & (value - 1):
                raise EvidenceError(name + ' must be a positive power of two')
        if prefetch_slots <= 0:
            raise EvidenceError('prefetch-slots must be positive')
        self.line_bytes, self.fill_bytes, self.axi = line_bytes, fill_bytes, axi
        self.prefetch_slots = prefetch_slots
        self.admission_mode = admission_mode
        self.slots, self.normal_pending, self.axi_pending = {}, [], deque()
        self.prefetches, self.normal_reads, self.hints, self.demands, self.axi_reads = [], [], [], [], []
        self.axi_id = None
        self.cycles = dict(clock=0, axi_clock=0)

    def uce(self, v, cycle, timestamp):
        event = boundary(cycle, timestamp)
        if bit(v, 'reset'):
            if self.slots or self.normal_pending:
                raise EvidenceError('UCE reset with incomplete transactions')
            return
        admission = 'drop' if self.admission_mode == 'drop' else 'duplicate'
        for label in ('request_v', 'request_yumi', 'allocate', admission, 'issue',
                      'response', 'fwd_v', 'fwd_ready', 'rev_v', 'rev_yumi'):
            bit(v, label)
        accepted = v['request_v'] and v['request_yumi']
        if v['request_yumi'] and not v['request_v']:
            raise EvidenceError('request consumed without valid')
        hint = accepted and known(v, 'request_type') == 9
        if v['allocate'] and not hint:
            raise EvidenceError('prefetch allocation without accepted hint')
        if v[admission] and not hint:
            raise EvidenceError('prefetch %s without accepted hint' % admission)
        if hint:
            address = known(v, 'request_address')
            matching = [record for record in self.slots.values()
                        if record['address'] // self.line_bytes == address // self.line_bytes]
            self.hints.append(dict(event, address=address,
                                   **{admission: bool(v[admission])}))
            if self.admission_mode == 'duplicate' and v['duplicate']:
                if v['allocate'] or not matching:
                    raise EvidenceError('duplicate hint has no matching reserved line')
            elif self.admission_mode == 'drop' and v['drop']:
                if v['allocate'] or len(self.slots) != self.prefetch_slots:
                    raise EvidenceError('dropped hint without a full prefetch queue')
            else:
                if not v['allocate']:
                    raise EvidenceError('accepted hint was neither allocated nor advisory-dropped')
                if self.admission_mode == 'duplicate' and matching:
                    raise EvidenceError('new hint did not allocate a unique line')
                slot = known(v, 'allocate_slot')
                if not 0 <= slot < self.prefetch_slots or slot in self.slots:
                    raise EvidenceError('duplicate or invalid prefetch slot allocation')
                record = dict(id=len(self.prefetches), slot=slot, address=address & ~7,
                              accept=event, issue=None, first_response=None, complete=None)
                self.slots[slot] = record
                self.prefetches.append(record)
        elif accepted:
            self.demands.append(dict(event, address=known(v, 'request_address'),
                                     msg_type=known(v, 'request_type')))

        fwd = v['fwd_v'] and v['fwd_ready']
        issued_prefetch = False
        if fwd:
            msg_type = known(v, 'fwd_type')
            prefetch = bit(v, 'fwd_prefetch')
            if prefetch and msg_type != 0:
                raise EvidenceError('prefetch forward is not mem_rd')
            if msg_type in (0, 2):
                if not bit(v, 'fwd_new') or not bit(v, 'fwd_last'):
                    raise EvidenceError('unsupported multibeat forward read/AMO')
                address, size, wire_tag, wire_state = (
                    known(v, 'fwd_' + key) for key in ('address', 'size', 'slot', 'state'))
                if size > 6:
                    raise EvidenceError('unsupported BedRock read size')
                if prefetch:
                    slot = known(v, 'issue_slot')
                    record = self.slots.get(slot)
                    if (record is None or record['issue'] is not None
                            or record['accept']['timestamp'] >= timestamp):
                        raise EvidenceError('prefetch issue has no earlier unissued slot allocation')
                    if size != 3 or address != record['address']:
                        raise EvidenceError('prefetch issue address/size mismatch')
                    if not v['issue']:
                        raise EvidenceError('prefetch issue pulse/slot mismatch')
                    if any(other.get('wire_tag') == wire_tag
                           and other.get('wire_state') == wire_state
                           for other in self.slots.values() if other is not record):
                        raise EvidenceError('duplicate outstanding prefetch response identity')
                    record['_prior'] = [other for other in self.slots.values()
                                        if other['issue'] is not None]
                    record['wire_tag'] = wire_tag
                    record['wire_state'] = wire_state
                    record['issue'] = event
                    issued_prefetch = True
                else:
                    if self.normal_pending:
                        raise EvidenceError('multiple normal UCE reads are unsupported')
                    if any(other['address'] // self.line_bytes == address // self.line_bytes
                           for other in self.slots.values()):
                        raise EvidenceError('normal read issued before same-line prefetch completion')
                    record = dict(id=len(self.normal_reads), address=address, slot=wire_tag,
                                  msg_type=msg_type, size=size, issue=event,
                                  first_response=None, complete=None, beats=0)
                    self.normal_reads.append(record)
                    self.normal_pending.append(record)
        if bool(v['issue']) != issued_prefetch:
            raise EvidenceError('prefetch issue without accepted forward read')

        response = v['rev_v'] and v['rev_yumi']
        consumed_prefetch = False
        if response:
            msg_type, prefetch = known(v, 'rev_type'), bit(v, 'rev_prefetch')
            if prefetch and msg_type != 0:
                raise EvidenceError('prefetch response is not mem_rd')
            if msg_type in (0, 2):
                address, size, wire_tag, wire_state = (
                    known(v, 'rev_' + key) for key in ('address', 'size', 'slot', 'state'))
                first, last = bit(v, 'rev_new'), bit(v, 'rev_last')
                if prefetch:
                    matching = [record for record in self.slots.values()
                                if record['issue'] is not None
                                and record['wire_tag'] == wire_tag
                                and record['wire_state'] == wire_state]
                    if len(matching) != 1:
                        raise EvidenceError('unmatched prefetch response')
                    record = matching[0]
                    if address != record['address'] or size != 3 or not first or not last:
                        raise EvidenceError('prefetch response address/size/boundary mismatch')
                    record['first_response'] = record['complete'] = event
                    del self.slots[record['slot']]
                    consumed_prefetch = True
                else:
                    if not self.normal_pending:
                        raise EvidenceError('unmatched normal read response')
                    record = self.normal_pending[0]
                    if (address, size, wire_tag, msg_type) != tuple(record[key] for key in ('address', 'size', 'slot', 'msg_type')):
                        raise EvidenceError('normal read response identity mismatch')
                    expected = max(1, (1 << size) // self.fill_bytes)
                    if first != (record['beats'] == 0) or last != (record['beats'] + 1 == expected):
                        raise EvidenceError('normal read response boundary/count mismatch')
                    record['beats'] += 1
                    if first:
                        record['first_response'] = event
                    if last:
                        record['complete'] = event
                        self.normal_pending.pop(0)
        if bool(v['response']) != consumed_prefetch:
            raise EvidenceError('prefetch response pulse without consumed response')

    def axi_edge(self, v, cycle, timestamp):
        event = boundary(cycle, timestamp)
        if bit(v, 'axi_reset'):
            if self.axi_pending:
                raise EvidenceError('AXI reset with incomplete transactions')
            self.axi_id = None
            return
        for label in ('ar_v', 'ar_ready', 'r_v', 'r_ready'):
            bit(v, label)
        if v['ar_v'] and v['ar_ready']:
            txn_id = known(v, 'ar_id')
            if self.axi_id is not None and txn_id != self.axi_id:
                raise EvidenceError('multiple AXI IDs unsupported; ordered same-ID trace required')
            self.axi_id = txn_id
            length = known(v, 'ar_len')
            if not 0 <= length <= 255:
                raise EvidenceError('invalid AXI ARLEN')
            record = dict(id=len(self.axi_reads), axi_id=txn_id,
                          address=known(v, 'ar_address'), expected_beats=length + 1, beats=0,
                          issue=event, first_response=None, complete=None,
                          _prior=list(self.axi_pending))
            self.axi_reads.append(record)
            self.axi_pending.append(record)
        if v['r_v'] and v['r_ready']:
            if not self.axi_pending:
                raise EvidenceError('unmatched AXI response')
            record = self.axi_pending[0]
            if known(v, 'r_id') != record['axi_id'] or known(v, 'r_resp') != 0:
                raise EvidenceError('AXI response ID mismatch or non-OKAY response')
            record['beats'] += 1
            last = bit(v, 'r_last')
            if last != (record['beats'] == record['expected_beats']):
                raise EvidenceError('AXI RLAST/count mismatch')
            if record['first_response'] is None:
                record['first_response'] = event
            if last:
                record['complete'] = event
                self.axi_pending.popleft()

    def finish(self, allow_no_prefetch=False):
        if self.slots or self.normal_pending or self.axi_pending:
            raise EvidenceError('trace ended with incomplete transactions')
        if not self.prefetches and not allow_no_prefetch:
            raise EvidenceError('no allocated prefetch transactions')
        uce = overlap_summary(self.prefetches)
        uce['max_reserved_slots'] = max_reserved_slots(self.prefetches)
        axi = overlap_summary(self.axi_reads) if self.axi else None
        return dict(verdict='valid_transactions', prefetch_summary=uce, axi_summary=axi,
                    prefetches=self.prefetches, accepted_hints=self.hints,
                    normal_requests=self.demands, normal_reads=self.normal_reads,
                    normal_request_summary=request_summary(self.demands),
                    axi_reads=self.axi_reads if self.axi else None,
                    backing_service_overlap='not observable from AXI handshakes',
                    axi_prefetch_attribution='not inferred; AXI also carries other cache traffic')


def analyze(stream, uce_prefix='dcache_uce', axi_prefix=None, line_bytes=64, fill_bytes=8,
            prefetch_slots=2, allow_no_prefetch=False):
    selected, timescale = read_header(stream, signal_names(uce_prefix, axi_prefix),
                                      optional=OPTIONAL_UCE_SIGNALS)
    admission_modes = [label for label in OPTIONAL_UCE_SIGNALS if label in selected]
    if len(admission_modes) != 1:
        raise EvidenceError('trace must contain exactly one prefetch admission policy signal')
    tracker = Transactions(line_bytes, fill_bytes, axi_prefix is not None, prefetch_slots,
                           admission_modes[0])
    clocks = ('clock', 'axi_clock') if axi_prefix is not None else ('clock',)
    for _, timestamp, values in rising_edges(stream, selected, clocks):
        for clock in values.get('_rising_clocks', ['clock']):
            cycle = tracker.cycles[clock]
            tracker.cycles[clock] += 1
            try:
                if clock == 'clock':
                    tracker.uce(values, cycle, timestamp)
                else:
                    tracker.axi_edge(values, cycle, timestamp)
            except EvidenceError as error:
                raise EvidenceError('%s cycle %d timestamp %d: %s' % (clock, cycle, timestamp, error)) from error
    for clock in clocks:
        if tracker.cycles[clock] == 0:
            raise EvidenceError('no observed rising edges for ' + clock)
    report = tracker.finish(allow_no_prefetch=allow_no_prefetch)
    report['prefetch_demand_matches'] = prefetch_demand_matches(
        report['prefetches'], report['normal_requests'], line_bytes)
    report.update(timescale=timescale, line_bytes=line_bytes, fill_bytes=fill_bytes,
                  configured_prefetch_slots=prefetch_slots,
                  prefetch_admission_mode=admission_modes[0],
                  signals={key: value[1] for key, value in selected.items()},
                  cycles=tracker.cycles,
                  sampling='stable values before each domain rising edge; independent cycle counters',
                  uce_issue_boundary='accepted UCE forward-pump read, not AXI acceptance')
    return report


def max_reserved_slots(records):
    """Return peak accepted/issued-but-incomplete transactions in *records*."""
    events = [((record.get('accept') or record['issue'])['timestamp'], 1)
              for record in records]
    events += [(record['complete']['timestamp'], -1) for record in records]
    reserved = maximum = 0
    for _, delta in sorted(events):
        reserved += delta
        maximum = max(maximum, reserved)
    return maximum


def region_summary(report, address, span_bytes, axi_address_xor=0):
    """Qualify AXI evidence by a physical data region and an outstanding hint.

    The AXI protocol carries no UCE slot ID. A matching line and time interval
    are recorded as correlation, not as a traced end-to-end transaction ID.
    Earlier loader reads and later demand reads cannot satisfy that interval.
    """
    if report.get('verdict') != 'valid_transactions':
        raise EvidenceError('region selection requires validated transactions')
    if address < 0 or span_bytes <= 0 or axi_address_xor < 0:
        raise EvidenceError('invalid address region or AXI address mapping')
    end = address + span_bytes
    line_bytes = report['line_bytes']

    def in_region(value):
        return address <= value < end

    def summarize(records):
        copies, pending = [], []
        for original in records:
            record = dict(original)
            pending = [prior for prior in pending
                       if prior['complete']['timestamp'] >= record['issue']['timestamp']]
            record['_prior'] = list(pending)
            copies.append(record)
            pending.append(record)
        summary = overlap_summary(copies)
        summary['max_reserved_slots'] = max_reserved_slots(records)
        return summary

    prefetches = [record for record in report['prefetches'] if in_region(record['address'])]
    if not prefetches:
        raise EvidenceError('no prefetch transactions in selected region')
    candidates, correlated = [], []
    for record in report['axi_reads'] or []:
        physical = record['address'] ^ axi_address_xor
        if not in_region(physical):
            continue
        timestamp = record['issue']['timestamp']
        matches = [hint['id'] for hint in prefetches
                   if hint['address'] // line_bytes == physical // line_bytes
                   and hint['issue']['timestamp'] < timestamp < hint['complete']['timestamp']
                   and record['complete']['timestamp'] <= hint['complete']['timestamp']]
        if len(matches) > 1:
            raise EvidenceError('ambiguous prefetch/AXI line and time correlation')
        item = dict(record, physical_address=physical, matching_prefetch_ids=matches)
        candidates.append(item)
        if matches:
            correlated.append(item)
    return dict(address_range=[address, end], axi_address_xor=axi_address_xor,
                prefetches=prefetches, prefetch_summary=summarize(prefetches),
                axi_region_reads=candidates, axi_correlated_reads=correlated,
                axi_summary=summarize(correlated) if report['axi_reads'] is not None else None,
                attribution='same physical line, AXI acceptance after prefetch issue, and AXI completion no later than prefetch response; correlation, not an AXI transaction source ID')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uce-prefix', default='dcache_uce')
    parser.add_argument('--axi-prefix', help='optional AXI memory module prefix, typically axi_mem')
    parser.add_argument('--line-bytes', type=int, default=64)
    parser.add_argument('--fill-bytes', type=int, default=8)
    parser.add_argument('--prefetch-slots', type=int, default=2)
    parser.add_argument('--address', type=lambda value: int(value, 0), help='optional physical data-region start')
    parser.add_argument('--span-bytes', type=lambda value: int(value, 0))
    parser.add_argument('--axi-address-xor', type=lambda value: int(value, 0), default=0,
                        help='map AXI addresses to physical addresses for region correlation')
    parser.add_argument('--require-uce-overlap', action='store_true')
    parser.add_argument('--require-axi-overlap', action='store_true')
    parser.add_argument('--require-reserved-slots', type=int, default=0,
                        help='fail unless at least this many UCE slots coexist')
    parser.add_argument('--allow-no-prefetch', action='store_true',
                        help='accept a demand-only trace and still report cache traffic')
    args = parser.parse_args()
    try:
        if (args.address is None) != (args.span_bytes is None):
            raise EvidenceError('address and span-bytes must be supplied together')
        report = analyze(sys.stdin, args.uce_prefix, args.axi_prefix, args.line_bytes,
                         args.fill_bytes, args.prefetch_slots, args.allow_no_prefetch)
        if args.address is not None:
            report['region'] = region_summary(report, args.address, args.span_bytes, args.axi_address_xor)
    except (EvidenceError, ValueError) as error:
        print(json.dumps(dict(verdict='invalid_trace', error=str(error))))
        return 2
    print(json.dumps(report, indent=2))
    gate = report.get('region', report)
    return int((args.require_uce_overlap and not gate['prefetch_summary']['issue_before_prior_first_response'])
               or (args.require_axi_overlap and not (gate['axi_summary'] and gate['axi_summary']['issue_before_prior_first_response']))
               or gate['prefetch_summary']['max_reserved_slots'] < args.require_reserved_slots)


if __name__ == '__main__':
    sys.exit(main())
