#!/usr/bin/env python3
"""Analyze only a revalidated fixed matrix, preserving primary and absolute costs."""
import argparse
import json
from pathlib import Path
import random
import statistics

import audit_admitted_matrix as admission_audit
from audit_admitted_matrix import artifact, require, sha
from analyze_scheduler_tagged_replay import percentile
from compare_scheduler_pipe_hint_mode14 import compare, _draw, _median, _strata

BOOTSTRAP_SAMPLES = 20000
WORKLOADS = ('scan', 'lookup', 'parse', 'chase')
ADDENDUM = admission_audit.ROOT / 'research/complete-policy-scope-20261120/ANALYSIS_LIMITS_ADDENDUM.md'
ADDENDUM_SHA = '501901af3a15442c743afac451b73717048521c6215efddc29b5612845e95902'
COST_FIELDS = ('absolute_enabled_cycles_per_cell', 'absolute_disabled_cycles_per_cell',
               'absolute_total_cycles_per_pair')


def reverify_bindings(record):
    """Hash every nested file identity, including validators and source snapshots."""
    known = {}

    def visit(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                path = Path(value['path'])
                require(path.is_absolute(), 'audit binding path must be absolute')
                previous = known.get(str(path))
                identity = (value['sha256'], value.get('bytes'))
                require(previous is None or previous[0] == identity[0], 'audit has conflicting file bindings')
                if previous is None:
                    require(path.is_file() and sha(path) == value['sha256'], 'audit binding changed: ' + str(path))
                    known[str(path)] = identity
                if 'bytes' in value:
                    require(path.stat().st_size == value['bytes'], 'audit binding size changed: ' + str(path))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(record)


def absolute_strata(boots):
    """Extend the existing paired rows; every draw keeps all outcomes together."""
    compatible = [dict(whole_cell=boot['whole_cell'], pairs=boot['steady_pairs']) for boot in boots]
    strata = _strata(compatible)
    for boot, rows in zip(boots, strata):
        for pair, row in zip(boot['whole_cell']['pairs'], rows):
            enabled, disabled = pair['enabled_cycles_per_cell'], pair['disabled_cycles_per_cell']
            row.update(absolute_enabled_cycles_per_cell=enabled,
                       absolute_disabled_cycles_per_cell=disabled,
                       absolute_total_cycles_per_pair=enabled + disabled)
    return strata


def absolute_boot(boot):
    """Retain all eight measured cells, separate arms, sums, order and resources."""
    rows = []
    for pair in boot['whole_cell']['pairs']:
        for order in (0, 1):
            enabled = int(order == pair['enabled_order'])
            rows.append(dict(repeat=pair['repeat'], order=order, enabled=enabled,
                             cycles=pair['enabled_cycles_per_cell' if enabled else 'disabled_cycles_per_cell']))
    require(len(rows) == 8, 'absolute report requires all eight WHOLE cells')
    enabled = [row['cycles'] for row in rows if row['enabled']]
    disabled = [row['cycles'] for row in rows if not row['enabled']]
    enabled_sum, disabled_sum = sum(enabled), sum(disabled)
    return dict(transcript=boot['transcript'], transcript_sha256=boot['transcript_sha256'],
                status=boot['status'], status_sha256=boot['status_sha256'],
                identity=boot['identity'], whole_cells_in_acquisition_order=rows,
                enabled_cycles=enabled, disabled_cycles=disabled,
                enabled_median_cycles=statistics.median(enabled),
                disabled_median_cycles=statistics.median(disabled),
                enabled_sum_cycles=enabled_sum, disabled_sum_cycles=disabled_sum,
                eight_cell_sum_cycles=enabled_sum + disabled_sum,
                enabled_order_by_repeat=boot['enabled_order_by_repeat'],
                paired_benefits=boot['whole_cell']['pairs'], resources=boot['resources'],
                trigger_accounting=boot.get('trigger_accounting'), memory_bound=boot.get('memory_bound'))


def absolute_crosschecks(primary):
    baseline, control = primary['baseline']['boots'], primary['control']['boots']
    a, b = absolute_strata(baseline), absolute_strata(control)
    point_a, point_b = _median(a), _median(b)
    # Same seed/boot choices/paired-row choices as the unchanged comparator.
    # Extra fields do not consume random choices, preserving the primary draw.
    rng = random.Random(0x4d313443)
    draws = {key: [] for key in (*COST_FIELDS, 'whole_cycles')}
    for _ in range(BOOTSTRAP_SAMPLES):
        draw_a, draw_b = _draw(rng, a), _draw(rng, b)
        for key in draws:
            draws[key].append(draw_b[key] - draw_a[key])
    primary_metrics = primary['primary_whole_cell_control_minus_baseline']
    require(primary_metrics['saved_cycles_per_cell'] == point_b['whole_cycles'] - point_a['whole_cycles'],
            'absolute strata changed the primary estimator')
    require(primary_metrics['hierarchical_95pct_ci_saved_cycles_per_cell'] ==
            [percentile(draws['whole_cycles'], 0.025), percentile(draws['whole_cycles'], 0.975)],
            'joint resampling differs from unchanged primary bootstrap')
    contrasts = {key: dict(control_minus_baseline=point_b[key] - point_a[key],
                           hierarchical_95pct_ci=[percentile(draws[key], 0.025), percentile(draws[key], 0.975)])
                 for key in COST_FIELDS}
    enabled = contrasts['absolute_enabled_cycles_per_cell']
    if enabled['control_minus_baseline'] < 0 and enabled['hierarchical_95pct_ci'][1] < 0:
        check = 'absolute-enabled-reduction-under-crossover-scope'
    elif enabled['control_minus_baseline'] > 0:
        check = 'absolute-enabled-regression-or-uncertainty'
    elif enabled['hierarchical_95pct_ci'] == [0, 0]:
        check = 'no-absolute-enabled-reduction'
    else:
        check = 'absolute-enabled-uncertain'
    primary_positive = (primary_metrics['saved_cycles_per_cell'] > 0
                        and primary_metrics['hierarchical_95pct_ci_saved_cycles_per_cell'][0] > 0)
    return dict(
        purpose='Descriptive and decision crosschecks; the registered paired-benefit primary is unchanged.',
        cost_direction='B-minus-A absolute cost: negative favors the early-only control; positive is a cost regression.',
        baseline_points={key: point_a[key] for key in COST_FIELDS},
        control_points={key: point_b[key] for key in COST_FIELDS},
        absolute_cost_control_minus_baseline=contrasts,
        baseline_boots=[absolute_boot(boot) for boot in baseline],
        control_boots=[absolute_boot(boot) for boot in control],
        decision_crosschecks=dict(
            primary_paired_benefit_ci_above_zero=primary_positive,
            absolute_enabled_check=check,
            positive_primary_with_absolute_enabled_regression_or_uncertainty=(
                primary_positive and check in ('absolute-enabled-regression-or-uncertainty', 'absolute-enabled-uncertain')),
            positive_primary_without_supported_absolute_enabled_reduction=(
                primary_positive and check != 'absolute-enabled-reduction-under-crossover-scope'),
            eligible_for_carryover_and_drift_review=(
                primary_positive and check == 'absolute-enabled-reduction-under-crossover-scope'),
            carryover_and_drift_review_required=True,
            kernel_optimization_claim_established=False),
        scope=('Costs are medians across paired-repeat rows with independent boot strata. '
               'The pair-total median is not a median of eight-cell boot sums. '
               'Exact eight-cell sums are reported separately for every boot and exclude startup/printed intervals.'))


def analyze_admitted(audit_path):
    audit_path = Path(audit_path).resolve()
    audit_record = artifact(audit_path)
    accepted = json.loads(audit_path.read_text())
    require(accepted.get('state') == 'protocol-accepted; image contrasts not calculated', 'input is not a strict accepted audit')
    inputs = accepted.get('comparator_inputs', {})
    require(set(inputs) == set(WORKLOADS), 'accepted audit must contain exactly four fixed workloads')
    require(all(set(inputs[workload]) == {'baseline', 'control'}
                and all(len(inputs[workload][arm]) == 2 for arm in ('baseline', 'control'))
                for workload in WORKLOADS), 'accepted audit requires two boots per image and workload')
    require(sha(ADDENDUM) == ADDENDUM_SHA, 'analysis limits addendum hash mismatch')
    reverify_bindings(accepted)
    regenerated = admission_audit.audit(Path(accepted['acquisition']['path']))
    require(regenerated == accepted, 'audit content differs from regenerated strict admission')
    workloads = {}
    for workload in WORKLOADS:
        paths = inputs[workload]
        primary = compare(paths['baseline'], paths['control'],
                          bootstrap_samples=BOOTSTRAP_SAMPLES, image_pair='embedded46')
        workloads[workload] = dict(unchanged_primary_comparison=primary,
                                  absolute_whole_crosschecks=absolute_crosschecks(primary))
    reverify_bindings(accepted)
    require(sha(audit_path) == audit_record['sha256'], 'accepted audit changed during analysis')
    return dict(
        state='four-workload admitted analysis; no automatic optimization claim',
        audit=audit_record, admission=accepted['admission'], acquisition=accepted['acquisition'],
        analysis_source=artifact(Path(__file__)), analysis_limits_addendum=artifact(ADDENDUM),
        bootstrap_samples=BOOTSTRAP_SAMPLES, image_pair='embedded46',
        workload_order=list(WORKLOADS), workloads=workloads,
        interpretation_limits=[
            'No across-workload pooling, replacement primary, result-dependent stopping or new measurements.',
            'The primary remains B-minus-A difference in paired off-on WHOLE benefit. Absolute cost contrasts use the opposite favorable sign: negative favors B.',
            'Repeated crossover can retain completed instruction lines into reporting/next initial setup; this is not isolated cold-cell or pure prefetch-versus-capacity evidence.',
            'Scope v1 drains reported prefix-controller bits only, not all UCE/memory responses.',
            '388 known parent early-wake opportunities saturate the eight-bit trigger counter at 255 in each valid run. Saturated counters cannot quantify removed late-selection triggers or locate admissions by phase.',
            'Positive paired benefit does not support an optimization claim if absolute enabled costs regress or remain uncertain, or carryover/drift remains unresolved.',
            'Two boots per image/workload provide limited between-boot evidence. All raw WHOLE cells, paired order and resource diagnostics remain required context.',
            'No general application throughput claim or automatically resolved carryover/drift follows from this helper.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise SystemExit('refusing to replace analysis output')
    try:
        result = analyze_admitted(args.audit)
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from error
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print('Wrote fixed four-workload analysis with absolute-cost crosschecks.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
