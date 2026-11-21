#!/usr/bin/env python3
"""Cross-check the completed frozen audit and summarize observed counts only."""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE.parent


def binding(p):
    return dict(path=str(p.resolve()), bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def main():
    global HERE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, default=HERE)
    HERE = parser.parse_args().audit_dir.resolve()
    report = json.loads((HERE/'analysis.json').read_text())
    manifest = json.loads((HERE/'manifest.json').read_text())
    guest = json.loads((CASE/'guest-observations.json').read_text())
    assert report['validation'] == manifest['state'] == 'passed'
    assert len(report['signals']) == 105 and report['reset_observed']
    assert len(report['requests']) == 64
    expected = report['metadata']['expected_target_loads_by_context']
    assert len({(r['context'], r['epoch']) for r in report['requests']}) == 64
    phases = {name: Counter() for name in ('warm', 'timed')}
    context_requests = Counter()
    for request in report['requests']:
        context_requests[request['context']] += 1
        assert request['stats']['target_loads'] == expected[str(request['context'])][request['epoch']]
        assert request['end_global_cycle'] > request['begin_global_cycle']
        phases[request['phase']].update(request['stats'])
        phases[request['phase']]['requests'] += 1
    assert context_requests == {i: 16 for i in range(4)}
    intervals = dict(warm=(guest['warm_begin'], guest['timed_begin']),
                     timed=(guest['timed_begin'], guest['timed_end']))
    assert guest['timed_end']-guest['timed_begin'] == guest['complete_ring_cycles'] == 431132
    counts = Counter()
    interval_counts = {p: Counter() for p in intervals}
    unique = set()
    slot_counts = Counter()
    capacities = ('0', '4', '16', '32', '64', '128')
    covers = {c: Counter() for c in capacities}
    covered_lines = {c: defaultdict(set) for c in capacities}
    for line in (HERE/'events.jsonl').open():
        event = json.loads(line)
        name = event['event']
        counts[name] += 1
        windows = [p for p, (a, z) in intervals.items() if a <= event['global_cycle'] < z]
        if name == 'eviction':
            for phase in windows:
                interval_counts[phase]['actual_replacement_evictions'] += 1
        if name != 'reference':
            continue
        unique.add(event['line'])
        for phase in windows:
            interval_counts[phase]['references'] += 1
            interval_counts[phase][event['operation']] += 1
            interval_counts[phase][event['outcome']] += 1
        if event['target']:
            slot_counts[(event['context'], event['thread'])] += 1
        for capacity, hit in event['victim_coverage'].items():
            if not hit:
                continue
            assert event['outcome'] == 'miss' and not event['l1_resident']
            covers[capacity]['full_references'] += 1
            covered_lines[capacity]['full_references'].add(event['line'])
            for phase in windows:
                covers[capacity][phase+'_interval_all_references'] += 1
                covered_lines[capacity][phase+'_interval_all_references'].add(event['line'])
            if event['target']:
                key = event['phase']+'_target'
                covers[capacity][key] += 1
                covered_lines[capacity][key].add(event['line'])
    stats = report['stats']
    assert counts['reference'] == stats['accepted_cached_references']
    assert counts['eviction'] == stats.get('actual_replacement_evictions', 0)
    assert counts['fill_beat'] == stats['matched_normal_fill_beats']
    assert counts['fill_complete'] == stats['matched_complete_normal_refills'] == stats['ordinary_misses']
    assert stats['matched_normal_tag_publications'] == stats['ordinary_misses']
    curves = {}
    for capacity in capacities:
        row = report['coverage'][capacity]
        assert covers[capacity]['full_references'] == row.get('covered_ordinary_misses', 0)
        for phase in phases:
            assert covers[capacity][phase+'_target'] == row.get(phase+'_target_misses_covered', 0)
            assert len(covered_lines[capacity][phase+'_target']) == row[phase+'_target_unique_lines_covered']
        curves[capacity] = dict(nominal_bytes=int(capacity)*64,
            covered_ordinary_misses={key: covers[capacity][key] for key in
                ('full_references', 'warm_interval_all_references', 'timed_interval_all_references', 'warm_target', 'timed_target')},
            unique_covered_lines={key: len(covered_lines[capacity][key]) for key in
                ('full_references', 'warm_interval_all_references', 'timed_interval_all_references', 'warm_target', 'timed_target')},
            actual_ledger_accounting=row)
    baseline = CASE.parent/'compact-one-kib-900/dcache-audit/summary.json'
    one = json.loads(baseline.read_text())
    assert one['complete_ring_cycles'] == 324256
    output = dict(state='complete-execution-and-full-access-audit-passed',
        scope='One synthetic bare-metal lookup32KiB-per-actor case; fixed-execution conditional coverage only',
        exclusions=report['exclusions'],
        geometry=dict(sets=64, ways=8, line_bytes=64, normal_l1_d_bytes=32768),
        complete_ring_cycles=guest['complete_ring_cycles'], timed_requests=32, timed_context_switches=32,
        program_requests=64, request_counts_by_context=dict(context_requests),
        all64_independent_target_load_counts_match=True, phases={p: dict(v) for p, v in phases.items()},
        full_program_stats=stats, event_counts=dict(counts),
        full_program_unique_normal_reference_lines=len(unique),
        all_normal_refs_by_printed_interval={p: dict(v) for p, v in interval_counts.items()},
        target_request_observed_unique_lines=report['target_unique_lines'],
        observed_target_loads_by_logical_context_and_physical_slot=[dict(context=c, slot=t, loads=n)
            for (c, t), n in sorted(slot_counts.items())],
        all_four_logical_actors_observed_on_both_resident_slots=len(slot_counts) == 8,
        conditional_exclusive_victim_curves=curves,
        fit_control=dict(binding=binding(baseline), complete_ring_cycles=one['complete_ring_cycles'],
            all_timed_normal_hits=one['all_normal_refs_in_printed_timed_interval']['l1_hit'],
            timed_target_loads=one['phases']['timed']['target_loads'], actual_replacement_evictions=0,
            comparison_limit='431132 versus324256 is not an isolated capacity effect: query/probe counts and compute differ. Coverage is not saved cycles or measured speedup.'),
        acceptance=dict(clean_converter_eof=manifest['complete_converter_eof'],
                        checker_returncode=manifest['maintained_checker_returncode'],
                        host_tests_returncode=manifest['host_tests_returncode'],
                        inputs_unchanged_after_analysis=manifest['inputs_unchanged_after_analysis']),
        bindings={name: binding(HERE/name) for name in ('manifest.json', 'analysis.json', 'events.jsonl')})
    (HERE/'summary.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps({k: output[k] for k in ('phases', 'full_program_stats', 'all_normal_refs_by_printed_interval', 'conditional_exclusive_victim_curves')}, indent=2))


if __name__ == '__main__':
    main()
