#!/usr/bin/env python3
"""Strict offline admission/analysis for the frozen natural-retention study."""
import argparse
import json
from pathlib import Path
import random
import re
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import analyze_scheduler_pipe_hint as parser
from analyze_scheduler_tagged_replay import percentile
from analyze_admitted_matrix import reverify_bindings
from audit_admitted_matrix import artifact,require,sha,timestamp,unique_file
from compare_scheduler_pipe_hint_mode14 import BOOT,_runtime_46_bound,_strata,_median,_draw,_boot
from run_scheduler_pipe_hint import GUEST_ELF,validate_transfer
from run_scheduler_tagged_replay import SHELL_PROMPT

ADMISSION=HERE/'admission.json'
ADMISSION_SHA='2b516262d5e36e81b93ad375910da89a452a43f46d5a2d156064f3fd2bf76f02'
PINS=HERE/'retention-validator-pins.json'
PINS_SHA='c0b2cb81b4a1f2d161f6a7fe82b95996436930395ebb794c2eb3fd54e395c370'
MATCHED='Matched instrumented per-cell control/fence/status/observer lifecycle; mode0 is not unmodified Linux deployment.'


def guest_command(policy,workload,loops,warmup,repeats):
    return f'{GUEST_ELF} {loops} {repeats} {policy} {warmup} futex plain 32'+(' '+workload if workload!='scan' else '')


def verify_fixed_files(admission,pins):
    records=[artifact(ADMISSION),artifact(PINS)]
    bindings=list(pins['files'].values())+list(pins['source_proof'].values())+list(pins['analysis_sources'].values())+[pins['capability_gate'],pins['board_helper']]
    for b in bindings:
        require(artifact(Path(b['path']))==b,'fixed retention input changed: '+b['path'])
        records.append(b)
    for relative,digest in pins['host_sources'].items():
        require(sha(ROOT/relative)==digest,'current source8 changed: '+relative)
    require(validate_transfer(Path(admission['identity']['transfer']['path']),admission['identity']['elf']['sha256']) is None,
            'retention ELF must use its fixed gzip transfer')
    return records


def audit(acquisition_path):
    require(sha(ADMISSION)==ADMISSION_SHA and sha(PINS)==PINS_SHA,'frozen retention plan/pins changed')
    a=json.loads(ADMISSION.read_text());pins=json.loads(PINS.read_text())
    acquisition_path=acquisition_path.resolve();acq=json.loads(acquisition_path.read_text())
    require(acq.get('admission_sha256')==ADMISSION_SHA and acq.get('validator_pins_sha256')==PINS_SHA,'acquisition has wrong retention plan/pins')
    require(acq.get('all_attempts_declared') is True,'complete attempt declaration required')
    require(not acq.get('failed_attempts'),'replacement attempts require prospective coordinator amendment')
    visits=acq.get('primary',[])
    require(len(visits)==len(a['reservation_plan'])==8,'retention requires eight primary reservations')
    require('pilot_session_manifest' in acq,'both excluded policy pilots required')
    scheduled=[dict(label='pilot',pilot=True,cells=[(p,a['pilot']['workload']) for p in a['pilot']['policy_order']],session_manifest=acq['pilot_session_manifest'])]
    for visit,expected in zip(visits,a['reservation_plan']):
        require(visit.get('label')==expected['label'],'retention policy/workload wave order differs')
        scheduled.append(dict(expected,pilot=False,cells=[(expected['policy'],w) for w in expected['workloads']],session_manifest=visit['session_manifest']))
    records=verify_fixed_files(a,pins)+[artifact(acquisition_path)]
    previous_end=timestamp(pins['created_utc']);seen=set();rows=[];sessions=[]
    identity={k:a['identity'][k] for k in ('bitstream_sha256','control_program_sha256')}
    identity.update({k+'_sha256':a['identity'][k]['sha256'] for k in ('nbf','elf','transfer')})
    # Check the entire cohort's provenance before opening guest transcripts.
    for visit in scheduled:
        path=Path(visit['session_manifest']);require(path.is_absolute(),'session path must be absolute')
        records.append(unique_file(path,seen,'session',content=True));session=json.loads(path.read_text())
        require(session.get('state')=='complete','retention session incomplete')
        require(session.get('reservation')==pins['reservation_lock'] and session.get('all_three_acknowledged') is True,'retention lock/ack mismatch')
        require(session.get('host')==pins['host'],'retention host differs')
        start,end=timestamp(session['started_utc']),timestamp(session['released_utc'])
        require(previous_end<=start<end,'retention sessions overlap/reverse/precede pin freeze');previous_end=end
        require(session.get('host_source_sha256')==pins['host_sources'],'retention source8 differs')
        for relative,digest in pins['host_sources'].items():
            source=path.parent/'host-sources'/relative
            require(source.is_file() and not source.is_symlink() and sha(source)==digest,'source8 snapshot changed: '+relative)
            records.append(artifact(source))
        cells=session.get('plan',[])
        require(len(cells)==len(visit['cells'])==2,'retention requires two planned independent fresh boots/reservation')
        sessions.append(dict(label=visit['label'],pilot=visit['pilot'],manifest=artifact(path),started_utc=session['started_utc'],released_utc=session['released_utc']))
        for index,(cell,(policy,workload)) in enumerate(zip(cells,visit['cells'])):
            limits=a['pilot'] if visit['pilot'] else a['config']
            config={k:limits[k] for k in ('loops','warmup','repeats','sync','profile','working_set_kib')}
            config.update(policy=policy,workload=workload,terminal_handshake=1,configured_entries=32,complete_policy_scope=1,resource_stats=1)
            for k,v in config.items():
                if k not in ('terminal_handshake','configured_entries','complete_policy_scope','resource_stats'):
                    require(cell.get(k)==v,'retention planned config/order differs: '+k)
            require(cell.get('host')==pins['host'],'retention planned host differs')
            for k,b in ((k,a['identity'][k]) for k in ('nbf','transfer')):
                require(cell.get(k)==b['path'],'retention planned artifact path differs: '+k)
            require(cell.get('elf_sha256')==identity['elf_sha256'] and cell.get('bitstream_sha256')==identity['bitstream_sha256']
                    and cell.get('control_sha256')==identity['control_program_sha256'],'retention planned identity differs')
            require(cell.get('zlib_library') is None and cell.get('embedded_zlib_library') is False and cell.get('retention_probe') is None
                    and cell.get('legacy_four_arg_cli') is False and cell.get('legacy_no_terminal_handshake') is False
                    and cell.get('runtime_ms')==pins['runtime_ms'],'retention delivery/probe/terminal shape differs')
            log=path.parent/f'{index}-{workload}32-{policy}.log';require(cell.get('log')==str(log),'retention planned log/order differs')
            records.append(unique_file(log,seen,'transcript',content=True))
            status_path=log.with_suffix('.log.status.json');records.append(unique_file(status_path,seen,'status'))
            status=json.loads(status_path.read_text())
            require(status.get('status')=='PASS' and status.get('runner_exit')==0,'retention runner incomplete/nonzero')
            for k,v in identity.items():require(status.get(k)==v,'retention fixed identity differs: '+k)
            for k,v in config.items():
                if k not in ('configured_entries','complete_policy_scope','resource_stats'):require(status.get(k)==v,'retention runner config differs: '+k)
            require(status.get('command')==guest_command(policy,workload,config['loops'],config['warmup'],config['repeats']),'retention exact command differs')
            require(status.get('legacy_four_arg_cli') is False and not any(k in status for k in
                    ('zlib_library_sha256','zlib_transfer_encoding','embedded_elf_source','transfer_encoding','retention_probe_capability')),'retention optional library/probe/delivery is forbidden')
            rows.append(dict(label=visit['label'],pilot=visit['pilot'],policy=policy,workload=workload,path=log,config=config))
    boots=[]
    for row in rows:
        text=row['path'].read_text(errors='replace').replace('\r','').replace('\x00','')
        require(len(BOOT.findall(text))==1,'retention requires one fresh Linux boot/transcript')
        require('ICACHE_RETENTION_PROBE' not in text and 'PIPE_HINT_LIBRARY' not in text,'retention boot contains prior probe/library activity')
        markers=list(re.finditer(r'^BOARD_RUNNER_SOURCE_SHA256=([0-9a-f]{64})$',text,re.M))
        require(text.count('BOARD_RUNNER_SOURCE_SHA256')==len(markers)==1 and markers[0][1]==pins['board_helper']['sha256'],'retention requires executed de54 helper')
        require('RUNNER_CLEANUP_SYNC_FAILED' not in text,'retention cleanup sync failed')
        for pattern in (r'^PIPE_HINT_PASS$',r'CORE(?:\[0\])? PASS',r'BSG PASS'):
            matches=list(re.finditer(pattern,text,re.M));require(matches and all(m.end()<markers[0].start() for m in matches),'retention missing/misordered terminal/helper')
        hashes=list(re.finditer(r'^'+re.escape(identity['elf_sha256']+'  '+GUEST_ELF)+r'$',text,re.M))
        config_line=re.search(r'^PIPE_HINT_CONFIG ',text,re.M)
        require(len(hashes)==1 and config_line is not None and hashes[0].end()<config_line.start(),'retention actual guest ELF hash missing/misordered')
        passed=re.search(r'^PIPE_HINT_PASS$',text,re.M);core=re.search(r'CORE(?:\[0\])? PASS',text)
        require(passed is not None and core is not None and passed.end()<core.start(),'retention completion/CORE order differs')
        gap=text[passed.end():core.start()]
        require(SHELL_PROMPT.search(gap) is not None and 'poweroff -f' in gap,'retention normal shell return missing')
        require(all(int(match[3])>0 for match in parser.ROW.findall(text)),'retention invalid zero timing')
        parsed=parser.analyze(row['path'],bootstrap_samples=1)
        require(parsed['config']==row['config'],'retention parsed fixed config differs')
        require('retention_status' in parsed and 'resources' in parsed and 'whole_cell' in parsed,'retention requires CSR/WHOLE/resource rows')
        for before,after,_,_ in parser.STATUS.findall(text):
            for value in (before,after):
                decoded=parser.decode_status(int(value,16));require(decoded['ready']==1 and decoded['configured_entries']==32,'retention prefix table is not ready32')
                require(not any(v for k,v in decoded.items() if k not in ('ready','configured_entries')),'retention contains nonzero I-prefix activity')
        memory=_runtime_46_bound(row['path']);raw=_boot(parsed)
        raw.update(label=row['label'],pilot=row['pilot'],policy=row['policy'],workload=row['workload'],config=parsed['config'],
            memory_bound=memory,retention_status=parsed['retention_status'],
            whole_cells=[dict(zip(('repeat','order','enabled','cycles','loops'),map(int,v))) for v in parser.WHOLE.findall(text)],
            steady_cells=[dict(zip(('repeat','order','enabled','cycles','loops'),map(int,v))) for v in parser.ROW.findall(text)],
            global_reset_evidence='Source+normal PASS imply reset0/readback; raw CSR rows are closing pre-reset snapshots, not printed post-reset samples.')
        boots.append(raw)
    require(len(boots)==18 and sum(not b['pilot'] for b in boots)==16,'retention boot count differs')
    for binding in records:require(artifact(Path(binding['path']))==binding,'retention input changed during admission')
    return dict(state='retention-protocol-accepted; policy contrasts not calculated',admission=artifact(ADMISSION),validator_pins=artifact(PINS),
        acquisition=artifact(acquisition_path),validator_source=artifact(Path(__file__)),bindings=records,sessions=sessions,
        pilot_boots_excluded=boots[:2],primary_boots=boots[2:],reset_telemetry_limit=pins['entry_reset_evidence'],matched_lifecycle=MATCHED,
        deployment_gain_claim_established=False)


def strata(boots):
    result=_strata([dict(whole_cell=b['whole_cell'],pairs=b['steady_pairs']) for b in boots])
    for boot,records in zip(boots,result):
        for pair,row in zip(boot['whole_cell']['pairs'],records):
            row.update(absolute_enabled_cycles_per_cell=pair['enabled_cycles_per_cell'],
                absolute_disabled_cycles_per_cell=pair['disabled_cycles_per_cell'],
                absolute_total_cycles_per_pair=pair['enabled_cycles_per_cell']+pair['disabled_cycles_per_cell'])
    return result


def uncertainty(groups,samples,contrast=False):
    rng=random.Random(0x4d313443)
    points=[_median(s) for s in groups]
    point={k:points[1][k]-points[0][k] for k in points[0]} if contrast else points[0]
    draws={k:[] for k in point}
    for _ in range(samples):
        sampled=[_draw(rng,s) for s in groups]
        for k in draws:draws[k].append(sampled[1][k]-sampled[0][k] if contrast else sampled[0][k])
    return {k:dict(point=v,hierarchical_95pct_ci=[percentile(draws[k],.025),percentile(draws[k],.975)]) for k,v in point.items()}


def absolute_boot(boot):
    enabled=[r['cycles'] for r in boot['whole_cells'] if r['enabled']]
    disabled=[r['cycles'] for r in boot['whole_cells'] if not r['enabled']]
    return dict(transcript=boot['transcript'],enabled_sum_cycles=sum(enabled),disabled_sum_cycles=sum(disabled),
                eight_cell_sum_cycles=sum(enabled)+sum(disabled),whole_cells_in_acquisition_order=boot['whole_cells'])


def analyze(acquisition_path):
    accepted=audit(acquisition_path);a=json.loads(ADMISSION.read_text());pins=json.loads(PINS.read_text());cases={};groups={}
    for policy in a['policies']:
        cases[policy]={}
        for workload in a['workloads']:
            boots=[b for b in accepted['primary_boots'] if b['policy']==policy and b['workload']==workload]
            require(len(boots)==2,'retention requires two independent boots/policy/workload')
            group=strata(boots);groups[(policy,workload)]=group
            cases[policy][workload]=dict(metrics=uncertainty([group],pins['bootstrap_samples']),boots=boots,
                absolute_boot_costs=[absolute_boot(b) for b in boots],scope=MATCHED,
                positive_whole_benefit_is_unmodified_deployment_gain=False)
    contrasts={w:dict(direction='first-minus-RR paired benefit; absolute cost negative favors first',
        metrics=uncertainty([groups[('retention-rr',w)],groups[('retention-first',w)]],pins['bootstrap_samples'],contrast=True)) for w in a['workloads']}
    reverify_bindings(accepted)
    return dict(state='retention-matched-lifecycle-analysis; no automatic deployment claim',audit=accepted,
        policy_workload_results=cases,first_minus_rr_by_workload=contrasts,
        metric_units=dict(whole_cycles='paired saved cycles per complete cell: disabled minus enabled',
            whole_percent='median paired saved percent; policy contrast is percentage points',
            steady_cycles='paired saved cycles per complete roundtrip',steady_percent='median paired steady saved percent',
            absolute_enabled_cycles_per_cell='observed enabled WHOLE cost cycles per cell',
            absolute_disabled_cycles_per_cell='observed disabled WHOLE cost cycles per cell',
            absolute_total_cycles_per_pair='observed enabled-plus-disabled WHOLE cost cycles per pair'),
        bootstrap=dict(samples=pins['bootstrap_samples'],seed='0x4d313443',unit='independent boots then intact paired records',
            whole_and_absolute_jointly_resampled=True,policy_contrast_independent_boot_draws=True),
        matched_lifecycle=MATCHED,unmodified_deployment_baseline_measured=False,deployment_gain_claim_established=False,
        limits=['All negative/null cases retained; no cross-workload pooling or automatic winner.',
            'Mode0 is instrumented and fenced; a future deployment claim requires actual separately preregistered unmatched execution, not syscall subtraction.',
            'All arms use the same32physical I advisory lines; admission/use changes, not guaranteed unique extra capacity or prefetch effectiveness.',
            'No numerical Linux/FPGA projection from the one-bank FFC D-capacity model.',
            'Two boots/policy/workload limit precision; raw resources and CSR rows are not cache occupancy or saved-cycle attribution.',
            'Reset-to-zero is source/recovery/PASS evidence; no independent entry/postreset CSR telemetry was printed.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('acquisition',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--analyze',action='store_true');args=p.parse_args()
    if args.output.exists():p.error('output must be new')
    try:result=analyze(args.acquisition) if args.analyze else audit(args.acquisition)
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as error:
        print('Retention admission rejected: '+str(error),file=sys.stderr);return 1
    args.output.write_text(json.dumps(result,indent=2)+'\n');return 0


if __name__=='__main__':sys.exit(main())
