#!/usr/bin/env python3
"""Offline-only fixed-retention completion gate; never launches a process."""
import argparse
import json
from pathlib import Path
import re

import retention_admission as frozen

HERE=Path(__file__).resolve().parent
TABLE=HERE/'retention-operations-argv.json'
TEMPLATE=HERE/'retention-acquisition.template.json'
TEMPLATE_SHA='9aeb748526c6bfb7b8cd970c797047b4718890333fcf1e9dd68e9f3464099f5d'
VALIDATOR_SHA='5e435679136d9c47e4f22391c4fcaccfb35cd072c2012387f1d1ff6cd54a4671'
require=frozen.require


def fixed_table(a,p,t):
    slots=[dict(label='pilot',pilot=True,session_manifest=t['pilot_session_manifest'],
        cells=[[policy,'scan'] for policy in a['pilot']['policy_order']])]
    for visit,row in zip(a['reservation_plan'],t['primary']):
        require(visit['label']==row['label'],'template order differs')
        slots.append(dict(label=visit['label'],pilot=False,session_manifest=row['session_manifest'],
            cells=[[visit['policy'],w] for w in visit['workloads']]))
    require(len(t['primary'])==8 and t['all_attempts_declared'] is False and not t['failed_attempts'],
            'template is not the frozen unfilled schedule')
    for slot in slots:
        c=a['pilot'] if slot['pilot'] else a['config'];i=a['identity'];out=Path(slot['session_manifest']).parent
        require(out.name==slot['label'] and out.is_absolute(),'template output binding differs')
        argv=['python3','-B',str(frozen.ROOT/'linux-tests/run_resume_workload_session.py'),
            i['nbf']['path'],i['transfer']['path'],i['elf']['sha256'],i['package']['path'],str(out),
            '--bitstream-sha256',i['bitstream_sha256'],'--host',p['host'],
            '--loops',str(c['loops']),'--warmup',str(c['warmup']),'--repeats',str(c['repeats']),
            '--all-three-acknowledged']
        for policy,w in slot['cells']:argv+=['--cell',f'{w}:32:{policy}']
        slot.update(argv=argv,supervisor_receipt=str(out.parent/(slot['label']+'-supervisor.json')))
    return slots


def inputs():
    require(frozen.sha(frozen.ADMISSION)==frozen.ADMISSION_SHA and frozen.sha(frozen.PINS)==frozen.PINS_SHA,
            'frozen retention plan/pins changed')
    require(frozen.sha(Path(frozen.__file__))==VALIDATOR_SHA and frozen.sha(TEMPLATE)==TEMPLATE_SHA,
            'frozen validator/template changed')
    a=json.loads(frozen.ADMISSION.read_text());p=json.loads(frozen.PINS.read_text())
    t=json.loads(TEMPLATE.read_text());slots=fixed_table(a,p,t)
    require(json.loads(TABLE.read_text())==slots,'argv table differs from frozen plan/template')
    records=frozen.verify_fixed_files(a,p)
    records += [frozen.artifact(x) for x in (Path(__file__),TABLE,TEMPLATE,Path(frozen.__file__))]
    return a,p,t,slots,records


def supervisor(slot,path,previous_end):
    """A reviewed root-owned detached supervisor must produce this receipt.

    The receipt is retained acquisition provenance, not independently observed
    process history. Its producer must be frozen/reviewed before any launch.
    PID reuse conservatively refuses continuation rather than guessing.
    """
    require(path.is_file() and not path.is_symlink(),'missing/symlink supervisor receipt')
    receipt=json.loads(path.read_text())
    require(receipt.get('label')==slot['label'] and receipt.get('argv')==slot['argv']
            and receipt.get('session_manifest')==slot['session_manifest'],'supervisor command/path binding differs')
    require(receipt.get('state')=='complete' and receipt.get('runner_exit')==0,'supervisor incomplete/nonzero')
    require(receipt.get('operations_source_sha256')==frozen.sha(Path(__file__))
            and receipt.get('argv_table_sha256')==frozen.sha(TABLE)
            and receipt.get('validator_source_sha256')==VALIDATOR_SHA,'supervisor operations provenance differs')
    pid=receipt.get('pid');ticks=receipt.get('start_ticks')
    require(type(pid) is int and pid>1 and type(ticks) is int and ticks>0,'invalid supervisor identity')
    require(not Path(f'/proc/{pid}').exists(),'supervisor still present or PID reused; stop')
    start,end=frozen.timestamp(receipt['started_utc']),frozen.timestamp(receipt['finished_utc'])
    require(previous_end<=start<end,'supervisor chronology differs')
    return receipt,start,end


def check_session(slot,a,p,seen,previous_end):
    """Mirror frozen per-session admission; use its unchanged parser/helpers.

    Only counts, hashes and protocol facts leave this function. The final
    frozen whole-cohort audit still supplies independent complete admission.
    """
    path=Path(slot['session_manifest']);records=[frozen.unique_file(path,seen,'session',content=True)]
    s=json.loads(path.read_text())
    require(s.get('state')=='complete','session incomplete')
    require(s.get('host')==p['host'] and s.get('reservation')==p['reservation_lock']
            and s.get('all_three_acknowledged') is True,'session lock/host/ack differs')
    start,end=frozen.timestamp(s['started_utc']),frozen.timestamp(s['released_utc'])
    require(previous_end<=start<end,'sessions overlap/reverse/precede freeze')
    require(s.get('host_source_sha256')==p['host_sources'],'session source8 differs')
    for rel,digest in p['host_sources'].items():
        source=path.parent/'host-sources'/rel
        require(source.is_file() and not source.is_symlink() and frozen.sha(source)==digest,'source8 snapshot changed')
        records.append(frozen.artifact(source))
    cells=s.get('plan',[]);require(len(cells)==len(slot['cells'])==2,'two fresh-boot cells required')
    identity={k:a['identity'][k] for k in ('bitstream_sha256','control_program_sha256')}
    identity.update({k+'_sha256':a['identity'][k]['sha256'] for k in ('nbf','elf','transfer')})
    for index,(cell,(policy,w)) in enumerate(zip(cells,slot['cells'])):
        limits=a['pilot'] if slot['pilot'] else a['config']
        config={k:limits[k] for k in ('loops','warmup','repeats','sync','profile','working_set_kib')}
        config.update(policy=policy,workload=w,terminal_handshake=1,configured_entries=32,complete_policy_scope=1,resource_stats=1)
        for k,v in config.items():
            if k not in ('terminal_handshake','configured_entries','complete_policy_scope','resource_stats'):
                require(cell.get(k)==v,'planned configuration/order differs: '+k)
        require(cell.get('host')==p['host'],'planned host differs')
        for k in ('nbf','transfer'):require(cell.get(k)==a['identity'][k]['path'],'planned artifact path differs: '+k)
        for k,expected in (('elf_sha256',identity['elf_sha256']),('bitstream_sha256',identity['bitstream_sha256']),
                           ('control_sha256',identity['control_program_sha256'])):
            require(cell.get(k)==expected,'planned identity differs: '+k)
        require(cell.get('zlib_library') is None and cell.get('embedded_zlib_library') is False
            and cell.get('retention_probe') is None and cell.get('legacy_four_arg_cli') is False
            and cell.get('legacy_no_terminal_handshake') is False and cell.get('runtime_ms')==p['runtime_ms'],
            'delivery/probe/terminal shape differs')
        log=path.parent/f'{index}-{w}32-{policy}.log'
        require(cell.get('log')==str(log),'planned log path/order differs')
        status_path=log.with_suffix('.log.status.json')
        records.extend([frozen.unique_file(log,seen,'transcript',content=True),frozen.unique_file(status_path,seen,'status')])
        status=json.loads(status_path.read_text())
        require(status.get('status')=='PASS' and status.get('runner_exit')==0,'runner incomplete/nonzero')
        for k,v in identity.items():require(status.get(k)==v,'status identity differs: '+k)
        for k,v in config.items():
            if k not in ('configured_entries','complete_policy_scope','resource_stats'):require(status.get(k)==v,'status config differs: '+k)
        require(status.get('command')==frozen.guest_command(policy,w,config['loops'],config['warmup'],config['repeats']),
                'exact guest command differs')
        require(status.get('legacy_four_arg_cli') is False and not any(k in status for k in
            ('zlib_library_sha256','zlib_transfer_encoding','embedded_elf_source','transfer_encoding','retention_probe_capability')),
            'optional library/probe/delivery forbidden')
        text=log.read_text(errors='replace').replace('\r','').replace('\x00','')
        require(len(frozen.BOOT.findall(text))==1,'one fresh Linux boot required')
        require('ICACHE_RETENTION_PROBE' not in text and 'PIPE_HINT_LIBRARY' not in text,'prior probe/library activity')
        markers=list(re.finditer(r'^BOARD_RUNNER_SOURCE_SHA256=([0-9a-f]{64})$',text,re.M))
        require(text.count('BOARD_RUNNER_SOURCE_SHA256')==len(markers)==1 and markers[0][1]==p['board_helper']['sha256'],
                'executed de54 helper required')
        require('RUNNER_CLEANUP_SYNC_FAILED' not in text,'cleanup sync failed')
        for pattern in (r'^PIPE_HINT_PASS$',r'CORE(?:\[0\])? PASS',r'BSG PASS'):
            matches=list(re.finditer(pattern,text,re.M))
            require(matches and all(m.end()<markers[0].start() for m in matches),'missing/misordered terminal/helper')
        hashes=list(re.finditer(r'^'+re.escape(identity['elf_sha256']+'  '+frozen.GUEST_ELF)+r'$',text,re.M))
        banner=re.search(r'^PIPE_HINT_CONFIG ',text,re.M)
        require(len(hashes)==1 and banner is not None and hashes[0].end()<banner.start(),'actual guest hash missing/misordered')
        passed=re.search(r'^PIPE_HINT_PASS$',text,re.M);core=re.search(r'CORE(?:\[0\])? PASS',text)
        require(passed.end()<core.start(),'completion/CORE order differs')
        gap=text[passed.end():core.start()]
        require(frozen.SHELL_PROMPT.search(gap) is not None and 'poweroff -f' in gap,'normal shell return missing')
        require(all(int(row[3])>0 for row in frozen.parser.ROW.findall(text)),'invalid zero timing')
        parsed=frozen.parser.analyze(log,bootstrap_samples=1)
        require(parsed['config']==config,'parsed config differs')
        require(all(k in parsed for k in ('retention_status','resources','whole_cell')),'CSR/WHOLE/resource rows required')
        for before,after,_,_ in frozen.parser.STATUS.findall(text):
            for value in (before,after):
                decoded=frozen.parser.decode_status(int(value,16))
                require(decoded['ready']==1 and decoded['configured_entries']==32,'prefix table not ready32')
                require(not any(v for k,v in decoded.items() if k not in ('ready','configured_entries')),'nonzero prefix activity')
        frozen._runtime_46_bound(log)
    return dict(label=slot['label'],pilot_excluded=slot['pilot'],boot_count=2,session=frozen.artifact(path),
        source_reset_scope=p['entry_reset_evidence'],printed_csr_is_closing_prereset=True),records,start,end


def complete_prefix(label):
    a,p,t,slots,records=inputs();labels=[s['label'] for s in slots]
    require(label in labels,'unknown fixed slot')
    index=labels.index(label);previous_end=frozen.timestamp(p['created_utc']);seen=set();accepted=[];pids=set()
    for slot in slots[:index+1]:
        receipt_path=Path(slot['supervisor_receipt'])
        receipt,super_start,super_end=supervisor(slot,receipt_path,previous_end)
        require(receipt['pid'] not in pids,'duplicate supervisor PID; stop for review');pids.add(receipt['pid'])
        records.append(frozen.unique_file(receipt_path,seen,'supervisor receipt',content=True))
        summary,bindings,start,end=check_session(slot,a,p,seen,super_start)
        require(end<=super_end,'session release follows supervisor completion')
        summary['supervisor']=frozen.artifact(receipt_path);records+=bindings;accepted.append(summary);previous_end=super_end
    # No future output may already exist: no skipped slots, parallel launch or retries.
    for slot in slots[index+1:]:
        require(not Path(slot['session_manifest']).parent.exists() and not Path(slot['supervisor_receipt']).exists(),
                'future slot already exists; stop for review')
    for b in records:require(frozen.artifact(Path(b['path']))==b,'input changed during completion gate')
    return dict(state='fixed retention prefix complete; no effect calculated',through=label,accepted=accepted,
        next_argv=slots[index+1]['argv'] if index+1<len(slots) else None,bindings=records,
        final_frozen_audit_and_analysis_required=True,matched_lifecycle=frozen.MATCHED,deployment_gain_claim_established=False,
        supervisor_history_limit='Receipt producer and launch must be reviewed/frozen by root; process history is source-bound acquisition provenance, not inferred from /proc after exit.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label',choices=('pilot','R1a','R1b','F1a','F1b','F2a','F2b','R2a','R2b'))
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    try:
        result=complete_prefix(args.label)
        with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as error:
        print('Retention operations refused: '+str(error),file=__import__('sys').stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
