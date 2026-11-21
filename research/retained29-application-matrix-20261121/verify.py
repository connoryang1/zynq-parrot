#!/usr/bin/env python3
"""Recheck the closed offline preparation; never opens a board connection."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'linux-tests'))
import retained29_application_protocol as p

PREPARATION=HERE/'preparation-006'
VERIFICATION=HERE/'verification.json'
STATE='PASS offline host/protocol and fixed accepted ELF bindings; all drafts UNLAUNCHABLE'
OWNED=('linux-tests/retained29_application_protocol.py',
       'linux-tests/run_retained29_application_session.py',
       'linux-tests/test_retained29_application.py')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def external_bindings(value):
    if isinstance(value,dict):
        if {'path','sha256'}<=value.keys():p.verify_binding(value)
        for item in value.values():external_bindings(item)
    elif isinstance(value,list):
        for item in value:external_bindings(item)


def inspect():
    record=json.loads((PREPARATION/'manifest.json').read_text())
    p.require(record['state']==STATE,'closed preparation failed')
    external_bindings(record)
    p.require(record['sources']==p.source_hashes(),'current runtime source drift')
    p.require(len(record['sources'])==21 and len(p.FROZEN)==17,'source scope')
    p.require(record['frozen17_before']==record['frozen17_after']
        =={name:record['sources'][name] for name in p.FROZEN},'frozen runtime change')
    p.require(len(record['unchanged_sources'])==20,'existing input scope')
    for name,expected in record['unchanged_sources'].items():
        raw=subprocess.check_output(['git','-C',str(ROOT),'show',record['unchanged_base_commit']+':'+name])
        p.require(hashlib.sha256(raw).hexdigest()==expected==digest(ROOT/name),'base47 input changed '+name)
    for name,expected in record['sources'].items():
        p.require(digest(PREPARATION/'source'/name)==expected,'runtime snapshot changed '+name)
    p.require(digest(PREPARATION/'source/prepare.py')==record['preparer']['sha256'],'preparer snapshot changed')
    p.require(digest(PREPARATION/'source'/OWNED[2])==digest(ROOT/OWNED[2]),'test snapshot changed')
    p.require(set(record['programs'])==set(p.ELF_SHAS),'fixed three programs')
    for kind,sha in p.ELF_SHAS.items():
        p.require(record['programs'][kind]['elf']['sha256']==sha,'fixed ELF changed '+kind)
        p.transfer_commands(record,kind)
        p.require(record['needed'][kind]==['libc.so.6','ld-linux-riscv64-lp64d.so.1'],'fixed dependencies')
    p.require(all(name+'@GLIBC_2.27' in record['versioned_imports']['regex']
        for name in ('regcomp','regexec','regfree')),'real POSIX library ABI')
    commands={c['label']:c for c in record['commands']}
    p.require(len(commands)==len(record['commands']) and all(c['returncode']==0 for c in commands.values()),'offline command failed/duplicated')
    for label,count in (('application-tests',21),('legacy17-regression',37)):
        log=Path(commands[label]['log']['path']).read_text()
        p.require('\nRan %d tests in '%count in log and '\nOK\n' in log,'host gate incomplete '+label)
    p.require(len(record['drafts'])==6,'six closed drafts')
    rotations=[]
    for index,b in enumerate(record['drafts']):
        draft=json.loads(Path(b['path']).read_text());external_bindings(draft)
        role='pilot-functional' if index==0 else 'performance-acquisition'
        work=None if index==0 else p.WORKLOADS[index-1]
        p.require(draft['state']=='DRAFT-UNLAUNCHABLE' and draft['unlaunchable_reasons'],'draft launch barrier absent')
        p.require(draft['plan']==p.plan_for(role,work,index),'concrete plan changed')
        p.require(draft['sources']==record['sources'] and draft['programs']==record['programs'],'draft source/program binding')
        p.require(all(draft[k] is None for k in ('capability_gate','functional_gate','stage_admission'))
            and all(draft['artifacts'][k] is None for k in ('bit','package','fit')),'draft physical proof invented')
        declared=json.loads(Path(draft['plan_record']['path']).read_text())
        p.require(declared['state']=='DRAFT-UNLAUNCHABLE' and declared['plan']==draft['plan'],'draft plan state')
        try:p.validate_admission(draft)
        except ValueError as error:p.require('UNLAUNCHABLE' in str(error),'draft failed for an unexpected reason')
        else:raise ValueError('draft unexpectedly executable')
        label='pilot-offline' if index==0 else 'performance-'+work+'-offline'
        p.require(Path(commands[label]['log']['path']).read_text()=='RETAINED29_APP_DRAFT_UNLAUNCHABLE=1\n','default not offline')
        rotations.append(index)
    for kind in ('plain','regex'):
        for policy,_ in p.POLICIES:
            stem=PREPARATION/'real-host-fixtures'/(kind+'-'+policy)
            raw=stem.with_suffix('.stdout').read_text()
            p.require('HOST_VERIFY_' in raw and 'HOST_VERIFY_PASS' in raw,'original host marker not retained')
            metadata=json.loads(stem.with_suffix('.json').read_text())
            p.require(metadata['returncode']==0 and metadata['argv']==['8','2',policy,'4','futex','plain','32',
                'regex' if kind=='regex' else 'lookup','none'],'real pilot host command mismatch')
    paths=[ROOT/name for name in OWNED]
    paths += [HERE/'README.md',HERE/'.gitignore',HERE/'prepare.py',Path(__file__).resolve()]
    paths += sorted(path for path in PREPARATION.rglob('*') if path.is_file())
    files={str(path.relative_to(ROOT)):dict(bytes=path.stat().st_size,sha256=digest(path)) for path in paths}
    return dict(state='PASS closed offline application-cohort preparation',preparation=str(PREPARATION.relative_to(ROOT)),
        files=files,sources=record['sources'],unchanged_base_commit=record['unchanged_base_commit'],
        application_tests=21,unchanged_regression_tests=37,draft_rotations=rotations,
        physical_execution=False,performance_evidence=False,
        recovery_scope='live owner holds reservation until explicit fixed recovery attempt verifies overlay/operating and runner/helper; crash/SIGKILL not survivable')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal',action='store_true',help='write a new closure once, after rechecking every input')
    args=parser.parse_args();actual=inspect()
    if args.seal:
        p.require(not VERIFICATION.exists(),'closure already exists')
        actual['verified_utc']=datetime.now(timezone.utc).isoformat()
        VERIFICATION.write_text(json.dumps(actual,indent=2)+'\n')
    else:
        expected=json.loads(VERIFICATION.read_text());p.utc(expected.pop('verified_utc'))
        p.require(expected==actual,'closed file/evidence binding changed')
    print(actual['state']+'; 21 + 37 host tests; six drafts UNLAUNCHABLE; no board execution')


if __name__=='__main__':main()
