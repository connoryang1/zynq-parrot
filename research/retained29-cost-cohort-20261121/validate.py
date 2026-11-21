"""Offline draft checks only. No acquisition, result selection or board operations."""
import hashlib
import importlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'linux-tests'))
protocol = importlib.import_module('retained29_cost_protocol')
ORDERS = [('scan', 'lookup', 'parse', 'chase', 'regex'),
          ('regex', 'chase', 'parse', 'lookup', 'scan'),
          ('lookup', 'chase', 'scan', 'regex', 'parse')]
PRIMARY = dict(policy_mask=15, endpoint='WHOLE', ratio='on/off',
               pairing=['boot', 'workload', 'kib', 'repeat'],
               hierarchy=[dict(level='repeat', count=4, operation='geometric-mean'),
                          dict(level='independent-boot-per-configuration', count=3, operation='geometric-mean'),
                          dict(level='workload-times-size', count=10, operation='equal-weight-geometric-mean')],
               incomplete_cohort_aggregate='forbidden', pvalues=False,
               cell_independence_assumption=False, timing_based_exclusions=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_record(record):
    p = Path(record['path'])
    data = p.read_bytes()
    require(len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'],
            'binding drift: ' + str(p))


def validate(draft, verify_files=True):
    require(draft['schema'] == 'bp-retained29-cost-cohort-draft-v1', 'draft schema only')
    require(draft['state'] == 'DRAFT-UNLAUNCHABLE' and draft['launchable'] is False, 'no launch admission')
    require(draft['declared_utc'] is None, 'reviewed declaration time remains unset')
    require(draft['hardware'] is None and draft['artifacts'] == dict.fromkeys(
        ('nbf', 'package', 'bit', 'fit', 'kernel_verification')), 'unresolved actual hardware')
    require(all(v is None for v in draft['physical_prerequisites'].values()), 'no invented physical proof')
    require(draft['primary'] == PRIMARY, 'fixed complete-WHOLE hierarchy')
    require(draft['actual_sessions'] == [], 'no observations in preparation')
    require(draft['source_checkpoint'] == '52652c6ef13100bad00747fa5bde1ec498582bb1', 'fixed COST checkpoint')
    require(draft['safe_framework_checkpoint'] == '08d8ea43fd1b22e0129a9ba25b5d37dcc8bc82d4', 'corrected framework checkpoint')
    require(draft['bindings']['safe_handoff02']['sha256'] ==
        '1a76709cd20adcf425c202c01e86f1a89c0d5b38e680f5a0e4e67dc3d028db93', 'corrected handoff02')
    require(draft['bindings']['safe_host_gate']['sha256'] ==
        '9392c561a3cc3f4d37be2065625320b218e73dc416fa989e8f3307b1af8f95d8', 'prepared02 host checks')
    require(draft['rules'] == dict(attempts_per_slot=1, performance_boots=15, boots_per_workload=3,
        pilot_boots=1, busy_deferral='same-slot-no-target-attempt',
        any_attempt_failure='stop-preserve-no-retry', reservation='one-boot-release-after-verified-recovery',
        acquisition_boot_ids='16-distinct-actual-PS-UUIDs-in-consecutive-identity-guard-logs',
        per_application_retained_hit_occupancy='UNOBSERVED-old2dd',
        gp0_requirement='separate-per-image-hardware-functional-prerequisite'), 'fixed safety/scope rules')
    visits = draft['visits']
    require(len(visits) == 16, 'one pilot and fifteen performance boots')
    expected = [('pilot', None, None, 0)]
    expected += [(f'r{r}-{w}', r, w, 2*r) for r, order in enumerate(ORDERS) for w in order]
    for n, (visit, (identity, round_id, workload, rotation)) in enumerate(zip(visits, expected)):
        role = 'cost-pilot-functional' if n == 0 else 'cost-performance-acquisition'
        plan = protocol.plan_for(role, workload, rotation)
        require(visit == dict(id=identity, order=n, round=round_id, independent_boot=True,
            plan=plan, argv=[protocol.argv_for(plan, c) for c in plan['cases']],
            performance_acquisition=n != 0, actual_acquisition_boot_id=None), 'canonical visit/order: ' + identity)
        protocol.validate_plan(visit['plan'])
    require(draft['planned_counts'] == dict(performance_commands=90, performance_whole_cells=720,
        performance_paired_ratios=360, primary_joint_repeat_pairs=120, independent_performance_boots=15),
        'counts do not imply cell independence')
    handoff_record = draft['bindings']['safe_handoff02']
    if verify_files:
        for record in draft['bindings'].values():
            verify_record(record)
        handoff = json.loads(Path(handoff_record['path']).read_text())
        require(draft['sources'] == handoff['sources'] == protocol.source_hashes(), 'complete corrected source map')
        require(draft['sources']['linux-tests/retained29_safe_functional_protocol.py'] ==
            'd6ef6b464eec12e8283f70e583a8f49bdd2fe3697e9e8598204febaa71c63d74', 'transitive source fix')
        require(draft['bindings']['safe_host_gate']['sha256'] == handoff['host_gate']['sha256'], 'prepared02 host gate')
        require(draft['bindings']['cost_program_preparation']['sha256'] == protocol.PREPARATION_SHA,
                'fixed accepted-runtime preparation')
        require(draft['program_sha256'] == protocol.ELF_SHAS, 'fixed COST and probe programs')
        require(all(draft['checkpoint_sources'][name] == draft['sources'][name]
                    for name in draft['checkpoint_sources']), 'checkpoint sources equal current fixed sources')
        require(all(draft['bindings'][kind + '_elf']['sha256'] == protocol.ELF_SHAS[kind]
                    for kind in ('plain', 'regex')), 'actual ELF bindings equal fixed programs')
    return dict(state='PASS-offline-draft-only-UNLAUNCHABLE', visits=16, performance_boots=15,
                canonical_commands=96, actual_target_executions=0)


if __name__ == '__main__':
    print(json.dumps(validate(json.loads((HERE / 'cohort-draft.json').read_text())), indent=2))
