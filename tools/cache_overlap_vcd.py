#!/usr/bin/env python3
"""Stream ``fst2vcd dump.fst`` on stdin and report cold-load overlap as JSON.

Samples use the stable values immediately BEFORE each rising edge of be.clk_i,
not the settled values after that edge or a guessed global clock period. Cycle
numbers count observed BE rising edges from zero; timestamps use the VCD timescale.
Architectural retirement before critical refill proves overlap with critical-data
latency. Retirement before complete refill separately proves useful work during
an outstanding full-line fill, even if critical data has already arrived. Both
intervals exclude boundary cycles. Dispatch and integer-divider acceptance are
separate, weaker evidence. The target PC must identify the intended useful work.
"""

import argparse
import json
import re
import sys

DCACHE = 'be.calculator.pipe_mem.dcache.'
REQUIRED = {
    'clock': 'be.clk_i',
    'reset': 'be.reset_i',
    'request_v': DCACHE + 'cache_req_v_o',
    'request_yumi': DCACHE + 'cache_req_yumi_i',
    'address': DCACHE + 'cache_req_cast_o.addr',
    'msg_type': DCACHE + 'cache_req_cast_o.msg_type',
    'blocking_sent': DCACHE + 'blocking_sent',
    'critical_recv': DCACHE + 'critical_recv',
    'complete_recv': DCACHE + 'complete_recv',
    'dispatch_v': 'be.scheduler.dispatch_pkt_cast_o.v',
    'dispatch_pc': 'be.scheduler.dispatch_pkt_cast_o.pc',
    'dispatch_thread': 'be.scheduler.dispatch_pkt_cast_o.thread_id',
    'commit_v': 'be.calculator.commit_pkt_cast_o.instret',
    'commit_pc': 'be.calculator.commit_pkt_cast_o.pc',
    'commit_thread': 'be.retire_thread_id_lo',
}
OPTIONAL_GROUPS = {
    'integer_divider': {
        'long_v': 'be.calculator.pipe_long.idiv.v_i',
        'long_ready': 'be.calculator.pipe_long.idiv.ready_and_o',
        'long_reset': 'be.calculator.pipe_long.idiv.reset_i',
        'long_pc': 'be.calculator.pipe_long.pc',
        'long_thread': 'be.calculator.pipe_long.reservation_thread_id',
    },
    'late_writeback': {
        'late_v': 'be.late_wb_v_lo',
        'late_yumi': 'be.late_wb_yumi_li',
        'late_thread': 'be.calculator.late_wb_pkt_cast_o.thread_id',
        'late_rd': 'be.calculator.late_wb_pkt_cast_o.rd_addr',
    },
}


class EvidenceError(ValueError):
    """The trace cannot establish the requested boundary safely."""


def header(stream):
    scopes, found, timescale = [], {}, []
    watch = dict(REQUIRED)
    for group in OPTIONAL_GROUPS.values():
        watch.update(group)
    in_timescale = False
    for line in stream:
        words = line.split()
        if '$timescale' in line:
            in_timescale = True
        if in_timescale:
            timescale.extend(w for w in words if w not in ('$timescale', '$end'))
            if '$end' in line:
                in_timescale = False
        if words[:1] == ['$scope']:
            scopes.append(words[2])
        elif words[:1] == ['$upscope']:
            scopes.pop()
        elif words[:1] == ['$var']:
            full = '.'.join(scopes + [words[4]])
            for label, suffix in watch.items():
                if full == suffix or full.endswith('.' + suffix):
                    found.setdefault(label, []).append((words[3], full))
        elif words[:1] == ['$enddefinitions']:
            break
    else:
        raise EvidenceError('missing VCD enddefinitions')
    for label in REQUIRED:
        if label not in found:
            raise EvidenceError('missing required signal: ' + REQUIRED[label])
    for label, matches in found.items():
        if len(matches) != 1:
            raise EvidenceError('ambiguous signal: ' + watch[label])
    capabilities = {}
    for name, group in OPTIONAL_GROUPS.items():
        capabilities[name] = all(label in found for label in group)
        if not capabilities[name]:
            for label in group:
                found.pop(label, None)
    if not timescale:
        raise EvidenceError('missing VCD timescale')
    return {label: matches[0] for label, matches in found.items()}, ''.join(timescale), capabilities


def rising_edges(stream, selected):
    """Batch each timestamp: delta ordering cannot affect the pre-edge snapshot."""
    labels = {}
    for label, (code, _) in selected.items():
        labels.setdefault(code, []).append(label)
    values, updates = {}, {}
    timestamp, cycle = 0, 0
    clock_seen = False

    def finish():
        nonlocal clock_seen
        old_clock = values.get('clock')
        new_clock = updates.get('clock', old_clock)
        if 'clock' in updates:
            if new_clock is None and clock_seen:
                raise EvidenceError('unknown BE clock after clock sampling began')
            clock_seen |= new_clock is not None
        sample = dict(values) if old_clock == 0 and new_clock == 1 else None
        values.update(updates)
        updates.clear()
        return sample

    for line in stream:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            next_timestamp = int(line[1:])
            if next_timestamp < timestamp:
                raise EvidenceError('VCD timestamps are not monotonic')
            if next_timestamp == timestamp:
                continue
            sample = finish()
            if sample is not None:
                yield cycle, timestamp, sample
                cycle += 1
            timestamp = next_timestamp
        else:
            if line[0] in 'bB':
                parts = line.split()
                if len(parts) != 2:
                    continue
                raw, code = parts[0][1:], parts[1]
            elif line[0] in '01xXzZ':
                raw, code = line[0], line[1:]
            else:
                continue
            if code in labels:
                value = int(raw, 2) if re.fullmatch('[01]+', raw) else None
                for label in labels[code]:
                    updates[label] = value
    sample = finish()
    if sample is not None:
        yield cycle, timestamp, sample


def analyze(stream, address, target_pc, target_thread=1, line_bytes=64, span_lines=1):
    if address < 0 or target_pc < 0 or target_thread < 0:
        raise EvidenceError('addresses and target thread must be nonnegative')
    if line_bytes <= 0 or line_bytes & (line_bytes - 1):
        raise EvidenceError('line-bytes must be a positive power of two')
    if span_lines <= 0:
        raise EvidenceError('span-lines must be positive')
    first_line = address // line_bytes
    selected, timescale, capabilities = header(stream)
    report = {
        'address': address, 'line_bytes': line_bytes, 'span_lines': span_lines,
        'address_range': [first_line * line_bytes, (first_line + span_lines) * line_bytes],
        'target_pc': target_pc,
        'target_thread': target_thread, 'timescale': timescale,
        'sampling': 'pre-edge stable values at be.clk_i rising edge; cycle zero is first observed edge',
        'signals': {k: v[1] for k, v in selected.items()},
        'capabilities': capabilities, 'requests': [], 'events': [],
        'dispatch_overlap': False, 'retirement_overlap': False,
        'integer_divider_overlap': False, 'full_refill_retirement_overlap': False, 'issues': [],
    }
    pending = None
    blocking_pending = False

    def event(kind, cycle, timestamp, **fields):
        item = dict(kind=kind, cycle=cycle, timestamp=timestamp, **fields)
        report['events'].append(item)
        return item

    for cycle, timestamp, v in rising_edges(stream, selected):
        if v.get('reset') != 0:
            if pending is not None:
                pending['issues'].append('reset or unknown reset before completion')
                pending = None
            blocking_pending = False
            continue
        accepted = v.get('request_v') == 1 and v.get('request_yumi') == 1
        matching = accepted and v.get('address') is not None and first_line <= v['address'] // line_bytes < first_line + span_lines
        if matching:
            event('address_request', cycle, timestamp, address=v['address'],
                  msg_type=v.get('msg_type'), blocking_sent=v.get('blocking_sent'))
        # Dcache supports one outstanding blocking transaction. Tracking all
        # blocking requests prevents an unrelated refill being credited to ours.
        if accepted and v.get('blocking_sent') == 1:
            conflict = blocking_pending
            if conflict:
                report['issues'].append('second blocking request before completion')
            if pending is not None:
                pending['issues'].append('second blocking request before completion')
            pending = None
            blocking_pending = True
            if matching and v.get('msg_type') == 0:  # e_miss_load
                pending = {'accept': event('cold_load_accepted', cycle, timestamp, address=v['address']),
                           'critical': None, 'complete': None,
                           'issues': ['second blocking request before completion'] if conflict else [],
                           'dispatch': [], 'retirement': [], 'integer_divider': []}
                report['requests'].append(pending)
        for kind, prefix in (('dispatch', 'dispatch'), ('retirement', 'commit')):
            if v.get(prefix + '_v') == 1 and v.get(prefix + '_pc') == target_pc and v.get(prefix + '_thread') == target_thread:
                work = event(kind, cycle, timestamp, pc=target_pc, thread=target_thread)
                if pending is not None:
                    pending[kind].append(work)
        if (capabilities['integer_divider'] and v.get('long_v') == 1
                and v.get('long_ready') == 1 and v.get('long_reset') == 0
                and v.get('long_pc') == target_pc and v.get('long_thread') == target_thread):
            work = event('integer_divider_accepted', cycle, timestamp, pc=target_pc, thread=target_thread)
            if pending is not None:
                pending['integer_divider'].append(work)
        if pending is not None and capabilities['late_writeback'] and v.get('late_v') == 1 and v.get('late_yumi') == 1:
            event('late_writeback', cycle, timestamp, thread=v.get('late_thread'), rd=v.get('late_rd'))
        if blocking_pending and v.get('complete_recv') is None:
            issue = 'unknown complete_recv while blocking transaction pending'
            if issue not in report['issues']:
                report['issues'].append(issue)
        if v.get('complete_recv') == 1:
            blocking_pending = False
        if pending is None:
            continue
        for field in ('critical_recv', 'complete_recv', 'blocking_sent', 'request_v', 'request_yumi'):
            if v.get(field) is None:
                issue = 'unknown ' + field + ' while request pending'
                if issue not in pending['issues']:
                    pending['issues'].append(issue)
        if v.get('critical_recv') == 1 and pending['critical'] is None:
            pending['critical'] = event('critical_refill', cycle, timestamp)
        if v.get('complete_recv') == 1:
            pending['complete'] = event('complete_refill', cycle, timestamp)
        if pending['complete'] is not None:
            pending = None
    for request in report['requests']:
        if request['critical'] is None or request['complete'] is None:
            request['issues'].append('trace ended without both refill boundaries')
        elif request['complete']['cycle'] < request['critical']['cycle']:
            request['issues'].append('complete refill precedes critical refill')
        request['full_refill_retirement_overlap'] = bool(not request['issues'] and any(
            request['accept']['cycle'] < work['cycle'] < request['complete']['cycle']
            for work in request['retirement']))
        report['full_refill_retirement_overlap'] |= request['full_refill_retirement_overlap']
        for kind in ('dispatch', 'retirement', 'integer_divider'):
            request[kind + '_overlap'] = bool(not request['issues'] and any(
                request['accept']['cycle'] < work['cycle'] < request['critical']['cycle']
                and work['cycle'] < request['complete']['cycle'] for work in request[kind]))
            report[kind + '_overlap'] |= request[kind + '_overlap']
    if not report['requests']:
        report['issues'].append('no accepted blocking load miss for requested cache line')
    report['verdict'] = ('architectural_retirement_overlap' if report['retirement_overlap'] else
                         'full_refill_retirement_overlap_only' if report['full_refill_retirement_overlap'] else
                         'integer_divider_acceptance_only' if report['integer_divider_overlap'] else
                         'dispatch_only' if report['dispatch_overlap'] else 'no_proven_overlap')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    numeric = lambda value: int(value, 0)
    parser.add_argument('--address', required=True, type=numeric)
    parser.add_argument('--target-pc', required=True, type=numeric)
    parser.add_argument('--target-thread', default=1, type=numeric)
    parser.add_argument('--line-bytes', default=64, type=numeric)
    parser.add_argument('--span-lines', default=1, type=numeric,
                        help='match this many contiguous cache lines starting at address')
    parser.add_argument('--require-overlap', action='store_true',
                        help='exit 1 unless target-PC architectural retirement precedes critical refill')
    parser.add_argument('--require-full-refill-overlap', action='store_true',
                        help='exit 1 unless target-PC architectural retirement precedes complete refill')
    args = parser.parse_args()
    try:
        report = analyze(sys.stdin, args.address, args.target_pc, args.target_thread, args.line_bytes, args.span_lines)
    except (EvidenceError, ValueError) as error:
        print(json.dumps({'verdict': 'invalid_trace', 'error': str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return int((args.require_overlap and not report['retirement_overlap'])
               or (args.require_full_refill_overlap and not report['full_refill_retirement_overlap']))


if __name__ == '__main__':
    raise SystemExit(main())
