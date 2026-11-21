#!/usr/bin/env python3
"""Prepare a resource-only proposal from closed failures; NO target execution."""
import json
import math
import shutil
from prepare import bind, HERE


def verify(record):
    if bind(record['path']) != record:
        raise ValueError('bound input changed: '+record['path'])


def main():
    previous = HERE/'admission-v2.json'
    cohort_path = HERE/'cohort-v2-01/cohort.json'
    cohort = json.loads(cohort_path.read_text())
    if cohort['state'] != 'STOPPED-failure-preserved-no-retry' or len(cohort['runs']) != 1:
        raise ValueError('expected one preserved failed arm, no joint attempt')
    run = cohort['runs'][0]
    if run['mode'] != 0 or run['returncode'] != -25 or run['trace']['bytes'] != 2**30:
        raise ValueError('unexpected failure/resource identity')
    for record in cohort['frozen_inputs'].values():
        verify(record)
    for name in ('model','elf','base_nbf'):
        verify(cohort[name])
    verify(run['trace'])
    verify(run['log'])
    checks = json.loads((HERE/'remaining-check-estimate-v2.json').read_text())
    resource = json.loads((HERE/'failed-resource-v2-01/diagnostic.json').read_text())
    reporting = json.loads((HERE/'reporting-tail-estimate-v2.json').read_text())
    if resource['reader_returncode'] or not resource['reader_end_marker'] or resource['error']:
        raise ValueError('incomplete selected recovery')
    if resource['exceptions_or_interrupts_after_visible_whole_begin']:
        raise ValueError('exception requires diagnosis before a resource proposal')
    if resource['last_retired'] != {'cycle':1151357,'pc':'0x80000576'}:
        raise ValueError('unexpected final recovered check position')
    remaining = checks['checksum_queries_remaining_including_inflight']
    done = checks['total_checksum_queries']-remaining
    sample_cycles = checks['last_visible_retire_cycle']-checks['actor_progress'][0]['cycle']
    extrapolated = math.ceil(remaining*sample_cycles/done)
    remaining_cycle_envelope = dict(independent_checksum=200000,
                                    chronology_free_clear_and_idle_poll=50000,
                                    deferred_reporting_and_terminal=100000)
    cycles = sum(remaining_cycle_envelope.values())
    density = resource['peak_section_bytes_per_cycle']
    # A planning reserve, not a statement about the library's worst-case flush.
    finalization_reserve = 32*2**20
    additional = math.ceil(cycles*density)+finalization_reserve
    budget = 2*2**30
    free = shutil.disk_usage(HERE).free
    if additional >= 2**30 or free < 6*2**30:
        raise ValueError('proposed fixed pair resource margin unsupported')
    proposal = json.loads(previous.read_text())
    proposal.update(state='PROPOSED-RESOURCE-V3-NOT-AUTHORIZED-NO-EXECUTION',
                    previous_admission=bind(previous), failed_corrected_cohort=bind(cohort_path),
                    resource_proposal_source=bind(__file__))
    proposal['execution_budget'].update(fst_limit_bytes=budget,
                                        maximum_pair_fst_bytes=2*budget)
    proposal['run_template']['preexec']='RLIMIT_CORE=0; RLIMIT_FSIZE=2147483648; native1800s and host1980s unchanged; fresh one-attempt0→15 only after complete0; any error stops without retry.'
    proposal['limits']=[
        'Proposal only. No fresh target execution is authorized by this file.',
        'Both earlier cohorts remain failed/unfinalized. Neither yields accepted request, WHOLE, ring, cache, capacity or performance results. Mode15 was never executed.',
        'This proposes a fresh resource-feasibility cohort, not extension of an effect sample. No accepted cohort effect exists.',
        'Same corrected ELF/NBF, target source, layout, workload, checks, model, libraries, RTL and trace scope; only per-file trace resource limit changes.',
        'Empirical remaining-stage envelope is conditional, not a worst-case memory/IO/fault bound; mode15 feasibility is unproven. Any failure stops the pair.',
        'Native1800/host1980 budgets unchanged. One attempt per arm, no adaptive retry, no automatic larger cap, no unadmitted I/D modes.',
        'Complete guest+CORE+host checks and actual complete normal-cache/retained audits remain mandatory before interpretation. No Linux/FPGA or calibrated-memory performance projection.'
    ]
    proposal['resource_basis']={
        'purpose':'Resolve trace logging feasibility after all64 work requests visibly completed, without changing the measured target work or observing any accepted arm effect.',
        'failed_corrected_elapsed_host_seconds':run['elapsed_seconds'],
        'failed_corrected_prefix_cycles':resource['last_retired']['cycle'],
        'visible_requests':{'total_begin':64,'total_end':64,'each_actor_begin':16,'each_actor_end':16},
        'checks_certified':False,
        'recovered_prefix_status':'UNFINALIZED: SIGXFSZ interrupted writer. Reader0/#END proves only recoverable container bytes, never program completion or last actual target cycle.',
        'no_visible_exception_or_interrupt_after_whole_begin':True,
        'inferred_check_position':{'actor':0,'epoch':1,'query':3,'completed_queries':done,'remaining_including_inflight':remaining},
        'observed_first_check_sample_cycles':sample_cycles,
        'extrapolated_remaining_checksum_cycles':extrapolated,
        'checksum_extrapolation_limit':'Retired loop-control inference from exact ELF, not RF-register proof or a cycle guarantee; first sample includes actor metadata checks.',
        'observed_complete_fst_sections':resource['complete_vc_sections'],
        'observed_maximum_compressed_bytes_per_core_cycle':density,
        'observed_last_section_compressed_bytes_per_core_cycle':resource['last_complete_section']['bytes_per_clock_period'],
        'observed_be_clock_period_ticks':50000,
        'report_characters':reporting['new_successful_guest_characters'],
        'same_model_prior_maximum_consecutive_character_gap_cycles':reporting['maximum_consecutive_cprint_gap_cycles'],
        'report_cycles_at_that_observed_maximum':reporting['new_tail_cycles_at_old_maximum_character_gap'],
        'conditional_remaining_cycle_envelope':remaining_cycle_envelope,
        'conditional_remaining_cycles':cycles,
        'reserved_finalization_bytes':finalization_reserve,
        'conditional_additional_trace_bytes':additional,
        'conditional_total_trace_bytes':2**30+additional,
        'margin_to_proposed_per_arm_limit_bytes':budget-(2**30+additional),
        'conditional_host_seconds_at_whole_prefix_average':run['elapsed_seconds']*(1+cycles/resource['last_retired']['cycle']),
        'host_time_estimate_limit':'Elapsed includes load/initialization. Target complexity, host load and compression vary; unchanged hard native/host limits govern.',
        'free_home_bytes_at_preparation':free,
        'maximum_new_pair_trace_bytes':2*budget,
        'fixed_pair_scope':'Mode0 then15 only, fresh dirs, one attempt/arm;15 requires complete0 checker PASS. Does not require a positive benefit.'
    }
    proposal['resource_evidence']={name:bind(HERE/name) for name in (
        'failed-progress-v2-01/progress.json','remaining-check-estimate-v2.json',
        'failed-resource-v2-01/diagnostic.json','reporting-tail-estimate-v2.json',
        'diagnose_failed_progress_v2.py','estimate_remaining_checks_v2.py',
        'diagnose_v2_resource_tail.py','estimate_reporting_tail_v2.py',
        'prepared01/program/disassembly.log')}
    proposal['preserved_failure_frozen_inputs_verified']=len(cohort['frozen_inputs'])
    target = HERE/'admission-v3.json'
    if target.exists():
        raise ValueError('preserve existing proposal')
    target.write_text(json.dumps(proposal,indent=2)+'\n')
    print(json.dumps(dict(proposal=bind(target),resource_basis=proposal['resource_basis']),indent=2))


if __name__ == '__main__':
    main()
