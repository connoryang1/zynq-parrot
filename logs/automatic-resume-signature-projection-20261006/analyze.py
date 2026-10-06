#!/usr/bin/env python3
import hashlib, json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
footprint_path = root / 'logs/context-resume-footprint-20261002/model-results.json'
physical_path = root / 'logs/linux-prefetch-precision-sweep-rotate-20261003/results.json'
footprints = json.loads(footprint_path.read_text())
physical = json.loads(physical_path.read_text())

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def med(condition, metric, direction):
    return physical['results'][condition][metric][direction]['median']

directions = ('to_main', 'to_worker')
# Translation-primed work isolates the data warming opportunity. The explicit
# sweep always issued eight hints; use application work only, excluding its
# software issue/action and Linux scheduler time.
physical_savings = {}
for k in (2, 4, 6, 8):
    physical_savings[k] = {
        d: med('prime_h0', 'work', d) - med(f'correct{k}', 'work', d)
        for d in directions
    }
    physical_savings[k]['direction_average'] = sum(physical_savings[k][d] for d in directions) / 2

rows = []
for trace in ('scan', 'trie-stream', 'pointer-compute', 'k10-hardware'):
    sector = footprints[trace]['sector_16b']
    for k in (2, 4):
        predictor = sector['totals']['previous_first'][str(k)]
        precision = predictor['precision']
        cap = physical_savings[k]['direction_average'] * precision
        timely = sector['timeliness_previous_first'][str(k)]['5']['timely_fraction_of_hits']
        if timely is None:
            timely = 0.0
        ready_only_floor = cap * timely
        prime_work_avg = sum(med('prime_h0', 'work', d) for d in directions) / 2
        rows.append({
            'trace': trace,
            'depth': k,
            'predictions': predictor['predictions'],
            'ordered_hits': predictor['hits'],
            'ordered_precision': precision,
            'fully_ready_fraction_of_hits_at_5_cycle_lead': timely,
            'physical_exact_depth_work_saving_cycles_direction_average': physical_savings[k]['direction_average'],
            'projected_saving_cycles_ready_only_floor': ready_only_floor,
            'projected_saving_cycles_full_hit_value_cap': cap,
            'projected_phase_reduction_percent_floor': 100 * ready_only_floor / prime_work_avg,
            'projected_phase_reduction_percent_cap': 100 * cap / prime_work_avg,
        })

prime_avg = sum(med('prime_h0', 'work', d) for d in directions) / 2
correct8_avg = sum(med('correct8', 'work', d) for d in directions) / 2
out = {
    'method': 'Scale measured translation-primed physical application-work savings at exact depths 2/4 by ordered previous-first precision. The ready-only floor additionally credits only hits fully ready with five cycles of launch lead; the cap credits every ordered hit at its physical fully-warmed value. Partial responses make the floor conservative, while different issue timing and workloads make the cap non-guaranteed.',
    'inputs': {
        str(footprint_path.relative_to(root)): sha256(footprint_path),
        str(physical_path.relative_to(root)): sha256(physical_path),
    },
    'physical_application_work': {
        'translation_primed_direction_average_cycles': prime_avg,
        'eight_correct_direction_average_cycles': correct8_avg,
        'eight_correct_saving_cycles': prime_avg - correct8_avg,
        'eight_correct_phase_reduction_percent': 100 * (prime_avg - correct8_avg) / prime_avg,
        'eight_correct_phase_speedup': prime_avg / correct8_avg,
        'savings_by_exact_correct_depth': physical_savings,
    },
    'automatic_signature_projection': rows,
    'limits': [
        'This is a cross-experiment projection, not a measured automatic predictor result.',
        'The warm trace model estimates ordering and readiness; the physical sweep uses an 80-node dependent phase with long Linux resume lead.',
        'The ready-only floor ignores useful partial prefetch progress and delay of later accesses by the first miss.',
        'The full-hit cap assumes each ordered prediction realizes the same average value as the controlled exact-depth physical condition.',
        'Hardware training, lookup, issue, backpressure, cache pollution, and confidence-gate costs are not included.',
    ],
}
path = Path(__file__).with_name('results.json')
path.write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
