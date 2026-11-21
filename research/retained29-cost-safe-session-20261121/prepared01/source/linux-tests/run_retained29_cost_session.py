#!/usr/bin/env python3
"""Default-offline explicit COST session; old2dd and safe full recovery only."""
import argparse
import json
from pathlib import Path
import re
import time

import pexpect
import retained29_cost_protocol as p
import retained29_safe_session as safe
from run_scheduler_tagged_replay import expect_shell_prompt,SHELL_PROMPT

verify_sources=p.verify_sources
verify_artifacts=p.verify_artifacts

def run_guest(a,log_path,env,spawn=pexpect.spawn,runner=None,clock=time.monotonic):
    child=None;plan=a['plan'];deadline=clock()+3600

    def remaining(maximum):
        left=deadline-clock();p.require(left>0,'fixed3600s session budget exhausted')
        return min(maximum,left)

    def guarded(pattern,maximum,stage):
        result=child.expect([pattern,p.base.KERNEL_FAILURE_MARKER,
            re.compile(re.escape(p.base.TIMER_GUARD_MARKER)+r'[^\r\n]*'),
            re.compile(r'(?:RETAINED_STORE_PROBE|RESUME_RETAINED29(?:_REGEX)?_COST)_FAIL[^\r\n]*'),SHELL_PROMPT],
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
        guarded(re.compile(r'(?:^|\r*\n)RETAINED29_COST_APP_EXIT case='+re.escape(case_id)+r' rc=([0-9]+)\r*\n'),
                1800,'application '+case_id)
        p.require(child.match.group(1)=='0','actual command exit nonzero '+case_id)
        expect_shell_prompt(child,remaining(300),'normal return '+case_id)
        # Emitted only after the actual exit and observed shell prompt.
        echo('RETAINED29_COST_APP_RETURN case='+case_id)

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
            first=lines.index('RETAINED29_COST_APP_PROBE_BEGIN')+1;last=lines.index('RETAINED29_COST_APP_EXIT case=probe rc=0')
            p.base.parse_guest('\n'.join(lines[first:last]),dict(role='probe-present',hardware=a['hardware']))
            for case in plan['cases']:
                verify_sources(a);verify_artifacts(a)
                execute_case(p.command(plan,case),case['id'])
                log.flush();text=log_path.read_text(errors='replace');lines=p.base.clean_lines(text)
                first=lines.index(p.begin(case))+1;last=lines.index('RETAINED29_COST_APP_EXIT case='+case['id']+' rc=0')
                p.parse_benchmark('\n'.join(lines[first:last]),case,plan,a['hardware'])
            echo('RETAINED29_COST_APP_SESSION_END commands=6 exits=7')
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


def guest(a,core,path,env,runner):return run_guest(a,path,env,runner=runner)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('admission',type=Path,nargs='?')
    parser.add_argument('--execute',type=Path);parser.add_argument('--request-recovery',type=Path);args=parser.parse_args(argv)
    if args.request_recovery is not None:
        p.require(args.admission is None and args.execute is None,'recovery-only request has no guest arguments')
        safe.request_recovery(args.request_recovery);return
    p.require(args.admission is not None,'COST admission required');a=json.loads(args.admission.read_text())
    if args.execute is not None:safe.execute(a,args.execute,p,guest,admission_record=p.binding(args.admission))
    elif a.get('state')=='DRAFT-UNLAUNCHABLE':print('RETAINED29_COST_DRAFT_UNLAUNCHABLE=1')
    else:p.validate_admission(a);print('RETAINED29_COST_OFFLINE_ADMISSION_OK=1')


if __name__=='__main__':main()
