#!/usr/bin/env python3
"""One ABI29 functional boot, under the unchanged common physical reservation.

Validation is offline unless --execute is explicitly supplied. This client does
not install helpers, change the board runner, retry a guest, or infer performance.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess

import pexpect

import retained29_protocol as protocol
from run_scheduler_tagged_replay import expect_shell_prompt, SHELL_PROMPT


def now(): return datetime.now(timezone.utc).isoformat()


def verify_sources(admission):
    protocol.require(protocol.source_hashes()==admission['sources'], 'host/guest source changed during session')


def verify_artifacts(admission):
    for value in admission['artifacts'].values():protocol.verify_binding(value)
    if 'capability_gate' in admission:protocol.verify_binding(admission['capability_gate'])


def environment(admission):
    env=os.environ.copy()
    if not env.get('PYNQ_POWER_STATE_URL'):
        # Existing maintained fallback. Never save the environment or credential.
        match=re.search(r'https?://[^\s\x27\x22]+',Path('/home/coyang/power_cycle.sh').read_text())
        protocol.require(match is not None,'power controller not configured')
        env['PYNQ_POWER_STATE_URL']=match[0]
    env.update(PYNQ_POWER_OFF_SECONDS='15',PYNQ_CONTROL_PROGRAM_SHA256=protocol.RUNNER_SHA,
               PYNQ_CONTROL_PROGRAM_TIMEOUT_MS=str(admission['runtime_ms']),
               PYNQ_BITSTREAM_SHA256=admission['artifacts']['bit']['sha256'])
    return env


class Operations:
    """Only maintained scripts perform board operations; all calls are reserved."""
    def __init__(self, admission, output, env):
        self.admission,self.output,self.env=admission,output,env
        self.scripts=output/'host-sources/codex-skills/bp-fpga-synthesis/scripts'

    def step(self,name,argv,timeout=600):
        # Use the immutable session copies even for failure recovery. Original
        # source drift invalidates the result but must not block safe recovery.
        for relative,expected in self.admission['sources'].items():
            protocol.require(protocol.binding(self.output/'host-sources'/relative)['sha256']==expected,'session source snapshot changed')
        with (self.output/(name+'.log')).open('w') as log:
            process=subprocess.Popen(argv,env=self.env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            try:
                code=process.wait(timeout=timeout)
                protocol.require(code==0,name+' failed rc='+str(code))
            except BaseException:
                # Reap only our local helper process group before recovery.
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise
        return (self.output/(name+'.log')).read_text(errors='replace')

    def stage(self):
        a=self.admission['artifacts']
        text=self.step('stage',[str(self.scripts/'stage_pynq_artifacts.sh'),a['package']['path'],self.admission['host'],a['nbf']['path']])
        protocol.require('STAGE_OK=1' in text and 'STAGE_DURABLE_SYNC_OK=1' in text,'durable stage missing')

    def recover(self,label):
        for name in ('power_cycle_pynq','wait_pynq_ready','load_pynq_overlay'):
            text=self.step(label+'-'+name,[str(self.scripts/(name+'.sh')),self.admission['host']])
        wanted='LOADING_BIT_SHA256='+self.admission['artifacts']['bit']['sha256']
        protocol.require(wanted in text and 'REMOTE_FPGA_STATE_OK=1' in text and 'REMOTE_OVERLAY_LOAD_OK=1' in text,'recovered overlay identity/state')

    def remote_identity(self):
        # Read only, after fresh recovery and before invoking the fixed helper.
        text=self.step('remote-identity',['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',self.admission['host'],
            'cd /home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq && sha256sum control-program run-blackparrot-interactive'],30)
        protocol.require(text.splitlines()==[protocol.RUNNER_SHA+'  control-program',protocol.HELPER_SHA+'  run-blackparrot-interactive'],'actual remote runner/helper identity')

    def guest(self):
        verify_sources(self.admission)
        return run_guest(self.admission,self.output/'console.log',self.env,
                         runner=self.scripts/'run_pynq_interactive.sh')


def guarded(child,pattern,timeout,stage):
    outcome=child.expect([pattern,protocol.KERNEL_FAILURE_MARKER,
                         re.compile(re.escape(protocol.TIMER_GUARD_MARKER)+r'[^\r\n]*'),
                         re.compile(r'(?:RETAINED_STORE_PROBE|RESUME_RETAINED29)_FAIL[^\r\n]*'),SHELL_PROMPT],timeout=timeout)
    protocol.require(outcome==0,stage+' failed or returned before required reply')


def run_guest(admission,log_path,env,spawn=pexpect.spawn,runner=None):
    """Hash-before-execution, then strict normal-return/terminal protocol."""
    role=admission['role'];guest=protocol.GUEST[role];child=None
    try:
        child=spawn(str(runner or protocol.SCRIPTS/'run_pynq_interactive.sh'),
            [admission['host'],admission['artifacts']['nbf']['path']],env=env,encoding='utf-8',timeout=300)
        child.setwinsize(50,180)
        with log_path.open('w') as log:
            child.logfile_read=log
            expect_shell_prompt(child,300,'ABI29 Linux boot')
            log.flush();protocol.boot_bound(log_path.read_text(errors='replace'),admission)
            for command in protocol.transfer_commands(admission):
                child.sendline(command);expect_shell_prompt(child,180,'ABI29 ELF transfer')
            child.sendline('/bin/busybox sha256sum '+guest)
            guarded(child,re.compile(r'(?:^|\r*\n)([0-9a-f]{64})  '+re.escape(guest)+r'\r*\n'),180,'guest hash')
            protocol.require(child.match.group(1)==admission['artifacts']['elf']['sha256'],'actual guest ELF hash mismatch')
            expect_shell_prompt(child,180,'ABI29 verified guest ELF')
            child.sendline(protocol.guest_command(role))
            guarded(child,re.compile(r'(?:^|\r*\n)RETAINED29_EXIT rc=([0-9]+)\r*\n'),1800,'ABI29 guest execution')
            protocol.require(child.match.group(1)=='0','actual guest exit nonzero')
            expect_shell_prompt(child,300,'ABI29 normal guest return')
            log.flush();protocol.parse_guest(log_path.read_text(errors='replace'),admission)
            child.sendline('poweroff -f')
            # Failure-aware terminal gate; EOF before CORE is never accepted.
            outcome=child.expect([re.compile(r'CORE(?:\[0\])? PASS'),protocol.KERNEL_FAILURE_MARKER,
                                  re.compile(re.escape(protocol.TIMER_GUARD_MARKER))],timeout=180)
            protocol.require(outcome==0,'poweroff terminal failure')
            child.expect(pexpect.EOF,timeout=180)
        child.close()
        protocol.require(child.exitstatus==0 and child.signalstatus is None,'interactive runner abnormal exit')
        result=protocol.complete_console(log_path.read_text(errors='replace'),admission)
        return dict(result,runner_exit=0,runner_signal=None,guest_exit=0,shell_return=True,console=protocol.binding(log_path))
    finally:
        if child is not None and child.isalive():child.close(force=True)


def execute(admission,output,operations=Operations):
    protocol.validate_admission(admission)
    protocol.require(not output.exists(),'output must be new')
    # The existing inode is opened read-only and locked NB, before output or any
    # upload/power/SSH. A busy refusal has no board side effect.
    with protocol.maintained_session.reservation():
        output.mkdir(parents=True)
        for relative in protocol.SOURCE_FILES:
            target=output/'host-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((protocol.ROOT/relative).read_bytes())
            target.chmod((protocol.ROOT/relative).stat().st_mode & 0o777)
        state=dict(schema='bp-retained29-functional-session-v1',state='reserved',started_utc=now(),
                   role=admission['role'],hardware=admission['hardware'],artifacts=admission['artifacts'],
                   admission=admission,sources=admission['sources'],reservation=str(protocol.maintained_session.SESSION_LOCK),
                   performance_inference=False,guest_boots=0)
        path=output/'session.json'
        def save():path.write_text(json.dumps(state,indent=2)+'\n')
        save();ops=None;failure=None
        def interrupted(sig,frame):raise KeyboardInterrupt('interrupted signal '+str(sig))
        handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
        try:
            ops=operations(admission,output,environment(admission))
            verify_sources(admission);verify_artifacts(admission)
            ops.stage();ops.recover('initial');ops.remote_identity()
            verify_artifacts(admission)
            state['guest_boots']=1;save()
            state['guest']=ops.guest()
            verify_sources(admission);verify_artifacts(admission)
        except BaseException as error:
            failure=error;state.update(state='FAIL',error=repr(error))
        finally:
            # Defer repeat termination while owned recovery completes. SIGKILL
            # cannot be handled: an interrupted session is never reusable proof.
            for sig in handlers:signal.signal(sig,signal.SIG_IGN)
            try:
                if ops is not None:
                    ops.recover('final');state['recovery']='complete before reservation release'
                else:state['recovery']='no board operation began'
                verify_sources(admission)
            except BaseException as error:
                state.update(state='FAIL',recovery='FAILED',recovery_error=repr(error))
                if failure is None:failure=error
            if failure is None:state['state']='PASS-complete-recovered-functional-session'
            state['release_after_recovery_utc']=now()
            try:save()
            finally:
                for sig,handler in handlers.items():signal.signal(sig,handler)
        if failure is not None:raise failure
    return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('admission',type=Path)
    parser.add_argument('--execute',type=Path,metavar='NEW_OUTPUT',help='explicitly perform one physical functional session')
    args=parser.parse_args(argv)
    admission=json.loads(args.admission.read_text())
    if args.execute is None:
        protocol.validate_admission(admission)
        print('RETAINED29_OFFLINE_ADMISSION_OK=1')
    else:execute(admission,args.execute)
    return 0


if __name__=='__main__':raise SystemExit(main())
