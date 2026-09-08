#!/usr/bin/env python3
"""Report independent-request admission separately from peer-load dispatch.

Stream fst2vcd output on stdin. The existing cache analyzer supplies clocked
acceptance and refill boundaries; this reducer compares consecutive selected
load misses. It assumes the current single blocking transaction interface and
rejects incomplete or conflicting evidence. A dispatched peer instruction is
not proof that its memory request was admitted. Address ranges and target PCs
must come from the exact traced ELF, and requests outside the range are not
included in the reported workload.
"""

import argparse
import json
import sys

from cache_overlap_vcd import EvidenceError, analyze as cache_analyze


def summarize(cache_report, expected_requests=None):
    """Reduce validated per-load records without inventing PC/address ownership."""
    if expected_requests is not None and expected_requests <= 0:
        raise EvidenceError('expected-requests must be positive')
    issues = list(cache_report['issues'])
    for index, request in enumerate(cache_report['requests']):
        issues.extend('request %d: %s' % (index, issue) for issue in request['issues'])
    if expected_requests is not None and len(cache_report['requests']) != expected_requests:
        issues.append('expected %d accepted load misses, observed %d' % (
            expected_requests, len(cache_report['requests'])))
    if issues:
        raise EvidenceError('; '.join(issues))

    report = {key: cache_report[key] for key in (
        'address_range', 'line_bytes', 'timescale', 'sampling', 'signals',
        'target_pc', 'target_thread')}
    report.update(
        model='single outstanding blocking transaction; no refill transaction IDs',
        dispatch_attribution='target PC/thread only; no inferred address ownership',
        peer_dispatch_events=[event for event in cache_report['events']
                              if event['kind'] == 'dispatch'],
        requests=[], request_admission_before_previous_critical=False,
        request_admission_before_previous_complete=False,
        peer_dispatch_before_critical=False, peer_dispatch_before_complete=False)
    for index, request in enumerate(cache_report['requests']):
        accept, critical, complete = (request[name]['cycle'] for name in ('accept', 'critical', 'complete'))
        if not accept <= critical <= complete:
            raise EvidenceError('request %d: invalid acceptance/refill ordering' % index)
        dispatch = request['dispatch']
        entry = dict(
            address=request['accept']['address'], accept=request['accept'],
            critical=request['critical'], complete=request['complete'],
            critical_cycles=critical - accept, complete_cycles=complete - accept,
            peer_dispatch=dispatch,
            peer_dispatch_before_critical=any(accept < event['cycle'] < critical for event in dispatch),
            peer_dispatch_before_complete=any(accept < event['cycle'] < complete for event in dispatch),
            next_request=None)
        if index + 1 < len(cache_report['requests']):
            following = cache_report['requests'][index + 1]['accept']
            delta_critical = following['cycle'] - critical
            delta_complete = following['cycle'] - complete
            # A conflict normally reaches us as an issue from cache_analyze.
            # Keep this guard so even externally supplied reports fail closed.
            if delta_complete < 0:
                raise EvidenceError('overlapping requests cannot be associated with untagged refills')
            entry['next_request'] = dict(
                address=following['address'], accept_cycle=following['cycle'],
                cycles_after_critical=delta_critical, cycles_after_complete=delta_complete)
        for kind in ('critical', 'complete'):
            report['peer_dispatch_before_' + kind] |= entry['peer_dispatch_before_' + kind]
        report['requests'].append(entry)
    report['accepted_load_misses'] = len(report['requests'])
    report['adjacent_request_pairs'] = max(0, len(report['requests']) - 1)
    # This verdict reports the admission boundary, even if a peer dispatches
    # while the line is still filling. A one-request trace cannot establish it.
    report['verdict'] = ('serialized_request_admission' if report['adjacent_request_pairs']
                         else 'insufficient_request_pairs')
    return report


def analyze(stream, address, target_pc, target_thread=1, line_bytes=64,
            span_lines=1, expected_requests=None):
    return summarize(cache_analyze(stream, address, target_pc, target_thread,
                                   line_bytes, span_lines), expected_requests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    numeric = lambda value: int(value, 0)
    parser.add_argument('--address', required=True, type=numeric)
    parser.add_argument('--span-lines', default=1, type=numeric)
    parser.add_argument('--line-bytes', default=64, type=numeric)
    parser.add_argument('--target-pc', required=True, type=numeric,
                        help='exact peer prefetch/load instruction PC')
    parser.add_argument('--target-thread', default=1, type=numeric)
    parser.add_argument('--expected-requests', type=numeric,
                        help='fail unless exactly this many selected load misses completed')
    parser.add_argument('--require-serialized', action='store_true',
                        help='exit 1 unless at least one pair demonstrates serialized admission')
    args = parser.parse_args()
    try:
        report = analyze(sys.stdin, args.address, args.target_pc, args.target_thread,
                         args.line_bytes, args.span_lines, args.expected_requests)
    except (EvidenceError, ValueError) as error:
        print(json.dumps({'verdict': 'invalid_trace', 'error': str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return int(args.require_serialized and report['verdict'] != 'serialized_request_admission')


if __name__ == '__main__':
    sys.exit(main())
