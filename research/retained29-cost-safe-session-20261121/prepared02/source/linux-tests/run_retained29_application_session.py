#!/usr/bin/env python3
"""Explicit ABI29 application cohort; offline by default, no automatic retries."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import tempfile
import time

import pexpect

import retained29_application_protocol as p
import run_retained29_session as maintained
import run_retained29_session_v2 as stage_client
from run_scheduler_tagged_replay import expect_shell_prompt, SHELL_PROMPT


def now():return datetime.now(timezone.utc).isoformat()


def journal(path,value):
    """Atomic durable journal/request publication; never touches the flock inode."""
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name+'-',delete=False) as stream:
        temporary=Path(stream.name);json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    try:os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()
    descriptor=os.open(str(path.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def request_recovery(output):
    """Queue exactly one fixed recovery-only action for the existing live owner."""
    output=output.resolve();state=json.loads((output/'session.json').read_text())
    p.require(state.get('schema')==p.SCHEMA and state.get('state')=='recovery-required-reservation-held',
              'existing application supervisor must be holding for recovery')
    request=dict(schema='bp-retained29-recovery-request-v1',action='recover-only',
                 token=state['recovery_token'],attempt=state['recovery_attempts']+1)
    target=output/'recovery-request.json'
    # Link publishes atomically and refuses to overwrite another pending intent.
    with tempfile.NamedTemporaryFile(mode='w',dir=output,prefix='.recovery-request-',delete=False) as stream:
        temporary=Path(stream.name);json.dump(request,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    try:os.link(temporary,target)
    finally:temporary.unlink()
    descriptor=os.open(str(output),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    return request


def verify_sources(a):p.require(p.source_hashes()==a['sources'],'application/frozen source changed')


def verify_artifacts(a):
    for b in a['artifacts'].values():p.verify_binding(b)
    for program in a['programs'].values():
        for b in program.values():p.verify_binding(b)
    for key in ('capability_gate','functional_gate','stage_admission','plan_record'):p.verify_binding(a[key])


class Operations:
    """Compose the genuine present-probe stage/recovery, never its guest role."""
    def __init__(self,a,output,env):
        self.a,self.output,self.env=a,output,env
        _,stage_base=p.prior_capability(a)
        self.stage_operations=stage_client.Operations(stage_base,output,env)
        self.scripts=output/'host-sources/codex-skills/bp-fpga-synthesis/scripts'
        self.phase='prepared';self.recoveries={};self.identities=0
        self.original_step=self.stage_operations.step
        self.stage_operations.step=self.step

    def step(self,label,*args):return self.original_step(self.phase+'-'+label,*args)
    def stage(self):
        self.phase='stage';return self.stage_operations.stage()
    def requires_recovery(self):
        return bool(self.stage_operations.stage_complete or self.stage_operations.mutation_started
                    or self.stage_operations.original is not None)
    def recover(self,label):
        self.recoveries[label]=self.recoveries.get(label,0)+1
        self.phase=label+'-attempt-%04d'%self.recoveries[label]
        try:return self.stage_operations.recover(label)
        finally:self.receipt()
    def remote_identity(self):
        self.identities+=1;self.phase='initial-identity-%04d'%self.identities
        try:return self.stage_operations.remote_identity()
        finally:self.receipt()
    def final_identity(self):
        self.identities+=1;self.phase='final-identity-%04d'%self.identities
        # V2 recover has already verified either the requested overlay or its
        # exact saved prior-state rollback. Hash the fixed runner/helper after
        # recovery; do not demand the new stage bundle after a valid rollback.
        try:return maintained.Operations.remote_identity(self.stage_operations)
        finally:self.receipt()
    def receipt(self):
        path=self.output/'stage-v2-receipt.json'
        if path.exists():
            target=self.output/'recovery-receipts'/(self.phase+'.json');target.parent.mkdir(exist_ok=True)
            target.write_bytes(path.read_bytes())
    def guest(self):return run_guest(self.a,self.output/'console.log',self.env,runner=self.scripts/'run_pynq_interactive.sh')


def run_guest(a,log_path,env,spawn=pexpect.spawn,runner=None,clock=time.monotonic):
    child=None;plan=a['plan'];deadline=clock()+3600

    def remaining(maximum):
        left=deadline-clock();p.require(left>0,'fixed3600s session budget exhausted')
        return min(maximum,left)

    def guarded(pattern,maximum,stage):
        result=child.expect([pattern,p.base.KERNEL_FAILURE_MARKER,
            re.compile(re.escape(p.base.TIMER_GUARD_MARKER)+r'[^\r\n]*'),
            re.compile(r'(?:RETAINED_STORE_PROBE|RESUME_RETAINED29(?:_REGEX)?)_FAIL[^\r\n]*'),SHELL_PROMPT],
            timeout=remaining(maximum))
        p.require(result==0,stage+' failed/early shell return')

    def echo(marker):
        remaining(1)
        child.sendline('echo '+marker)
        guarded(re.compile(r'(?:^|\r*\n)'+re.escape(marker)+r'\r*\n'),180,'session marker')
        expect_shell_prompt(child,remaining(180),'session marker shell')

    def execute_case(command,case_id):
        remaining(1)
        child.sendline(command)
        guarded(re.compile(r'(?:^|\r*\n)RETAINED29_APP_EXIT case='+re.escape(case_id)+r' rc=([0-9]+)\r*\n'),
                1800,'application '+case_id)
        p.require(child.match.group(1)=='0','actual command exit nonzero '+case_id)
        expect_shell_prompt(child,remaining(300),'normal return '+case_id)
        # Emitted only after the actual exit and observed shell prompt.
        echo('RETAINED29_APP_RETURN case='+case_id)

    try:
        verify_sources(a);verify_artifacts(a)
        child=spawn(str(runner or p.base.SCRIPTS/'run_pynq_interactive.sh'),
            [a['host'],a['artifacts']['nbf']['path']],env=env,encoding='utf-8',timeout=300)
        child.setwinsize(50,180)
        with log_path.open('w') as log:
            child.logfile_read=log
            expect_shell_prompt(child,remaining(300),'ABI29 application Linux boot')
            log.flush();p.base.boot_bound(log_path.read_text(errors='replace'),a)
            echo(p.session_begin(plan))
            for kind in ('probe','plain','regex'):
                for command in p.transfer_commands(a,kind):
                    remaining(1)
                    child.sendline(command);expect_shell_prompt(child,remaining(180),'application transfer '+kind)
            # Both workload ELFs and the probe must all hash correctly before
            # any program is executed. Wrong last hash cannot run the first case.
            for kind in ('probe','plain','regex'):
                remaining(1)
                guest=p.GUEST[kind];child.sendline('/bin/busybox sha256sum '+guest)
                guarded(re.compile(r'(?:^|\r*\n)([0-9a-f]{64})  '+re.escape(guest)+r'\r*\n'),180,'actual '+kind+' hash')
                p.require(child.match.group(1)==a['programs'][kind]['elf']['sha256'],'actual guest ELF hash mismatch '+kind)
                expect_shell_prompt(child,remaining(180),'verified '+kind+' ELF')
            execute_case(p.probe_command(),'probe')
            log.flush();lines=p.base.clean_lines(log_path.read_text(errors='replace'))
            first=lines.index('RETAINED29_APP_PROBE_BEGIN')+1;last=lines.index('RETAINED29_APP_EXIT case=probe rc=0')
            p.base.parse_guest('\n'.join(lines[first:last]),dict(role='probe-present',hardware=a['hardware']))
            for case in plan['cases']:
                verify_sources(a);verify_artifacts(a)
                execute_case(p.command(plan,case),case['id'])
                log.flush();text=log_path.read_text(errors='replace');lines=p.base.clean_lines(text)
                first=lines.index(p.begin(case))+1;last=lines.index('RETAINED29_APP_EXIT case='+case['id']+' rc=0')
                p.parse_benchmark('\n'.join(lines[first:last]),case,plan,a['hardware'])
            echo('RETAINED29_APP_SESSION_END commands=6 exits=7')
            log.flush();p.parse_commands(log_path.read_text(errors='replace'),a)
            remaining(1)
            child.sendline('poweroff -f')
            result=child.expect([re.compile(r'CORE(?:\[0\])? PASS'),p.base.KERNEL_FAILURE_MARKER,
                re.compile(re.escape(p.base.TIMER_GUARD_MARKER))],timeout=remaining(180))
            p.require(result==0,'poweroff terminal failure')
            child.expect(pexpect.EOF,timeout=remaining(180))
        child.close()
        p.require(child.exitstatus==0 and child.signalstatus is None,'interactive runner abnormal exit')
        parsed=p.complete_console(log_path.read_text(errors='replace'),a)
        return dict(parsed,runner_exit=0,runner_signal=None,guest_exit=0,shell_return=True,
                    console=p.binding(log_path),executed_case_ids=[c['id'] for c in plan['cases']])
    finally:
        if child is not None and child.isalive():child.close(force=True)


def execute(a,output,operations=Operations,recovery_wait=time.sleep):
    p.validate_admission(a);p.require(not output.exists(),'new session output required')
    gate,_=p.prior_capability(a)
    p.require(p.utc(gate['release_after_recovery_utc'])<=p.utc(now()),'present probe must already be closed')
    fixed=json.loads(Path(a['functional_gate']['path']).read_text())
    p.require(p.utc(fixed['release_after_recovery_utc'])<=p.utc(now()),'fixed functional gate must already be closed')
    declared=json.loads(Path(a['plan_record']['path']).read_text())
    p.require(p.utc(declared['declared_utc'])<=p.utc(now()),'plan must precede acquisition')
    with p.base.maintained_session.reservation():
        output.mkdir(parents=True)
        for relative in p.SOURCE_FILES:
            src=p.base.ROOT/relative;target=output/'host-sources'/relative
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(src.read_bytes());target.chmod(src.stat().st_mode&0o777)
        state=dict(schema=p.SCHEMA,state='reserved',started_utc=now(),supervisor_pid=os.getpid(),role=a['role'],plan=a['plan'],admission=a,
            sources=a['sources'],legacy_sources=a['legacy_sources'],hardware=a['hardware'],artifacts=a['artifacts'],
            programs=a['programs'],reservation=str(p.base.maintained_session.SESSION_LOCK),guest_boots=0,
            primary='WHOLE',secondary='steady',effect_selection='none',performance_accepted=False,
            recovery_attempts=0,recovery_history=[],recovery_token=hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest())
        path=output/'session.json'
        def save():journal(path,state)
        save();ops=None;failure=None
        def interrupted(sig,frame):raise KeyboardInterrupt('interrupted signal '+str(sig))
        handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
        try:
            ops=operations(a,output,maintained.environment(a))
            verify_sources(a);verify_artifacts(a)
            ops.stage();ops.recover('initial');ops.remote_identity()
            verify_artifacts(a);state['guest_boots']=1;save()
            state['guest']=ops.guest();verify_sources(a);verify_artifacts(a)
        except BaseException as error:
            failure=error;state.update(state='FAIL',error=repr(error))
        finally:
            for sig in handlers:signal.signal(sig,signal.SIG_IGN)
            if ops is not None and ops.requires_recovery():
                while True:
                    state['recovery_attempts']+=1
                    state['state']='recovery-in-progress-reservation-held';save()
                    try:
                        ops.recover('final');ops.final_identity()
                    except BaseException as error:
                        if failure is None:failure=error
                        state.update(state='recovery-required-reservation-held',recovery='unconfirmed',recovery_error=repr(error))
                        state['recovery_history'].append(dict(attempt=state['recovery_attempts'],error=repr(error),utc=now()))
                        save()
                        # No target retry, no timer-driven recovery retry. Only
                        # a fixed explicit operator request admits another try.
                        request=output/'recovery-request.json'
                        while True:
                            if not request.exists():recovery_wait(10);continue
                            try:
                                intent=json.loads(request.read_text())
                                p.require(set(intent)=={'schema','action','token','attempt'}
                                    and intent['schema']=='bp-retained29-recovery-request-v1'
                                    and intent['action']=='recover-only' and intent['token']==state['recovery_token']
                                    and type(intent['attempt']) is int and intent['attempt']==state['recovery_attempts']+1,
                                    'invalid recovery-only request')
                            except (ValueError,TypeError,KeyError) as error:
                                count=len(state.setdefault('rejected_recovery_requests',[]))+1
                                retained=output/('recovery-request-rejected-%04d.json'%count);request.replace(retained)
                                state['rejected_recovery_requests'].append(dict(request=p.binding(retained),error=repr(error)));save()
                                continue
                            request.replace(output/('recovery-request-attempt-%04d.json'%intent['attempt']))
                            state['state']='recovery-in-progress-reservation-held';save();break
                        continue
                    state['recovery_history'].append(dict(attempt=state['recovery_attempts'],state='verified overlay/operating and runner/helper identity',utc=now()))
                    state['recovery']='complete before reservation release'
                    break
            else:state['recovery']='no board mutation or guest began'
            try:verify_sources(a)
            except BaseException as error:
                if failure is None:failure=error
                state.update(state='FAIL',error=repr(error))
            if failure is None:state['state']='PASS-complete-recovered-application-session'
            else:state['state']='FAIL'
            state['reservation_release_utc']=now()
            if state['recovery']=='complete before reservation release':
                state['release_after_recovery_utc']=state['reservation_release_utc']
            try:save()
            finally:
                for sig,handler in handlers.items():signal.signal(sig,handler)
        if failure is not None:raise failure
    return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('admission',type=Path,nargs='?')
    parser.add_argument('--execute',type=Path,metavar='NEW_OUTPUT',help='explicit one-boot application acquisition')
    parser.add_argument('--request-recovery',type=Path,metavar='HELD_OUTPUT',help='queue fixed recovery-only action; never starts a guest')
    args=parser.parse_args(argv)
    if args.request_recovery is not None:
        p.require(args.admission is None and args.execute is None,'recovery-only request has no admission/execute arguments')
        request_recovery(args.request_recovery);print('RETAINED29_APP_RECOVERY_ONLY_REQUESTED=1');return 0
    p.require(args.admission is not None,'admission path required')
    a=json.loads(args.admission.read_text())
    if args.execute is not None:execute(a,args.execute)
    elif a.get('schema')==p.SCHEMA and a.get('state')=='DRAFT-UNLAUNCHABLE':
        p.validate_plan(a['plan']);print('RETAINED29_APP_DRAFT_UNLAUNCHABLE=1')
    else:p.validate_admission(a);print('RETAINED29_APP_OFFLINE_ADMISSION_OK=1')
    return 0


if __name__=='__main__':raise SystemExit(main())
