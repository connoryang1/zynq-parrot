#!/usr/bin/env python3
"""Freeze source/build/reference identities; never invokes a model."""
import argparse
import json
from pathlib import Path
from common import *
from build_clone import members


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    require(not a.output.exists(), 'preserve existing admission')
    p = proposal(); build = json.loads(a.build.read_text())
    require(build['state'] == 'BUILT-NOT-TARGET-QUALIFIED' and
            build['proposal'] == bind(PROPOSAL) and
            build['baseline_relink']['sha256'] == MODEL_SHA and
            build['original_inventory_unchanged'], 'build gates incomplete')
    verify(build['binary'])
    require(identities(tree(Path(build['binary']['path']).parent)) == identities(build['final_files']),
            'copied build changed')
    cohort_path = NATURAL / 'cohort-v3-01/cohort.json'
    cohort = json.loads(cohort_path.read_text())
    require(cohort['model']['sha256'] == MODEL_SHA and cohort['elf']['sha256'] ==
            '8c83ca26bb44b3d1eb294e568a65323fa75820c6aefa049baa4e6da4002525f4', 'wrong reference pair')
    comparison = json.loads(Path(p['comparison']['path']).read_text())
    require(comparison['state'] == 'CLOSED-complete-audited-single-pair', 'closed full audit required')
    references = {}
    records = [bind(PROPOSAL), bind(a.build), p['comparison'], p['service_closure'],
               bind(cohort_path), cohort['elf'], build['binary']]
    for row in cohort['runs']:
        require(row['mode'] in (0,15) and row['state'] ==
                'COMPLETE-checks-PASS-awaiting-full-trace-audit', 'invalid original arm')
        require(str(row['mode']) not in references, 'duplicate original arm')
        references[str(row['mode'])] = row
        records += [row[k] for k in ('nbf','trace','log','guest','trace_metadata')]
        records += row['linked_libraries']
    require(set(references) == {'0','15'}, 'missing original arm')
    reader = ROOT / 'research/retained-system-geometry-20261121/reader/fst_events'
    require(bind(reader)['sha256'] == 'a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541',
            'wrong existing reader')
    records += [bind(reader), bind(NATURAL/'protocol.py'), bind(ROOT/'testing/check_run.py'),
                bind(NATURAL/'verify_finalized_trace.py')]
    records += [bind(f) for f in sorted(HERE.glob('*.py'))]
    frozen = {r['path']: r for r in records}
    for r in frozen.values(): verify(r)
    save(a.output, dict(state='FROZEN-awaiting-root-checkpoint-review-no-target-run',
          purpose='Host observation-only equivalence, never an additional effect sample.',
          proposal=bind(PROPOSAL), build=bind(a.build), original_model=p['model'],
          copied_model=build['binary'], source_files=build['final_files'],
          frozen_inputs=frozen, references=references, reader=bind(reader),
          environment=cohort['environment'], leaves=p['filter_leaves'],
          qualification_output=str(HERE/'qualification01'),
          one_shot_claim=str(HERE/'qualification-attempt01.json'),
          mode_order=[0,15], budget=dict(native_seconds=NATIVE_SECONDS,host_seconds=HOST_SECONDS,
          FST_bytes_per_arm=CAP,max_pair_FST_bytes=2*CAP,attempts_per_mode=1),
          qualification='Mode15 only after complete mode0 AND literal complete252-leaf stream equivalence. Stop any failure; no retry/extension. No new workload modes/latencies admitted.'))
    print(a.output, bind(a.output)['sha256'])


if __name__ == '__main__': main()
