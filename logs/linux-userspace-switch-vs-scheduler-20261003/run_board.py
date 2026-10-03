#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import pexpect

root = Path('/home/coyang/zynq-parrot')
evidence = Path(__file__).resolve().parent
binary = evidence / 'ctxtsw_user_benchmark'
expected = hashlib.sha256(binary.read_bytes()).hexdigest()
env = os.environ.copy()
env['PYNQ_CONTROL_PROGRAM_SHA256'] = 'be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e'
env['PYNQ_CONTROL_PROGRAM_TIMEOUT_MS'] = '600000'
status = {'status': 'running'}
with (evidence / 'board.log').open('w') as log:
    child = pexpect.spawn(
        str(root / 'codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh'),
        ['xilinx@192.168.4.35', str(root / 'linux-tests/out/linux-shell.nbf')],
        env=env, encoding='utf-8', timeout=240)
    child.logfile_read = log
    child.setwinsize(50, 180)
    try:
        child.expect('Run /bin/sh as init process')
        child.expect(r'~ # ')
        print('Guest shell ready; transferring direct-switch probe.', flush=True)
        for line in (evidence / 'transfer.txt').read_text().splitlines():
            child.sendline(line)
            child.expect(r'~ # ', timeout=30)
        child.sendline('sha256sum /tmp/ctxtsw_user_benchmark')
        child.expect(expected + r'\s+/tmp/ctxtsw_user_benchmark')
        child.expect(r'~ # ')
        print('Guest ELF verified; executing direct-switch probe.', flush=True)
        child.sendline('/tmp/ctxtsw_user_benchmark')
        outcome = child.expect_exact(
            ['[BP-LINUX-BENCH] PASS:', '[BP-LINUX-BENCH] FAIL'], timeout=240)
        child.expect(r'~ # ')
        child.sendline('echo PROBE_EXIT=$?')
        child.expect(r'PROBE_EXIT=([0-9]+)[\r\n]')
        probe_exit = int(child.match.group(1))
        child.expect(r'~ # ')
        child.sendline('poweroff -f')
        child.expect_exact('CORE[0] PASS')
        child.expect(pexpect.EOF, timeout=90)
        child.close()
        assert child.exitstatus == 0 and child.signalstatus is None
        if outcome != 0 or probe_exit != 0:
            raise RuntimeError(f'probe failed: outcome={outcome} exit={probe_exit}')
        status = {'status': 'PASS', 'runner_exit': 0,
                  'binary_sha256': expected,
                  'checks': ['guest ELF SHA', 'probe PASS', 'exit 0', 'poweroff CORE PASS']}
        print('Direct-switch probe PASS; guest powered off.', flush=True)
    except Exception as exc:
        status = {'status': 'FAIL', 'error': repr(exc),
                  'recovery': 'Power-cycle and reload the accepted overlay before another run.'}
        raise
    finally:
        (evidence / 'board-status.json').write_text(json.dumps(status, indent=2) + '\n')
        if child.isalive():
            child.close(force=True)
