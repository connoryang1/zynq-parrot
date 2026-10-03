#!/usr/bin/env python3
import base64
import hashlib
import json
import os
from pathlib import Path

import pexpect

root = Path('/home/coyang/zynq-parrot')
evidence = Path(__file__).resolve().parent
binary = evidence / 'amo_ctz_spacing'
expected = hashlib.sha256(binary.read_bytes()).hexdigest()
payload = base64.b64encode(binary.read_bytes()).decode()
env = os.environ.copy()
env['PYNQ_CONTROL_PROGRAM_SHA256'] = \
    'be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e'
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
        child.sendline(': > /tmp/amo_ctz_spacing.b64')
        child.expect(r'~ # ')
        for offset in range(0, len(payload), 768):
            chunk = payload[offset:offset + 768]
            child.sendline("echo '%s' >> /tmp/amo_ctz_spacing.b64" % chunk)
            child.expect(r'~ # ', timeout=30)
        child.sendline('base64 -d /tmp/amo_ctz_spacing.b64 > '
                       '/tmp/amo_ctz_spacing; chmod 755 /tmp/amo_ctz_spacing')
        child.expect(r'~ # ', timeout=30)
        child.sendline('sha256sum /tmp/amo_ctz_spacing')
        child.expect(expected + r'\s+/tmp/amo_ctz_spacing')
        child.expect(r'~ # ')
        print('Guest ELF verified; executing recoverable spacing probe.',
              flush=True)
        child.sendline('/tmp/amo_ctz_spacing')
        child.expect_exact('[AMO-CTZ-SPACING] PASS', timeout=90)
        child.expect(r'~ # ')
        child.sendline('echo PROBE_EXIT=$?')
        child.expect(r'PROBE_EXIT=0[\r\n]')
        child.expect(r'~ # ')
        child.sendline('poweroff -f')
        child.expect_exact('CORE[0] PASS')
        child.expect(pexpect.EOF, timeout=90)
        child.close()
        assert child.exitstatus == 0 and child.signalstatus is None
        status = {
            'status': 'PASS',
            'runner_exit': 0,
            'binary_sha256': expected,
            'checks': ['guest ELF SHA', 'recoverable probe PASS', 'exit 0',
                       'poweroff CORE PASS'],
        }
        print('Recoverable AMO/CTZ spacing probe PASS; guest powered off.',
              flush=True)
    except Exception as exc:
        status = {
            'status': 'FAIL',
            'error': repr(exc),
            'recovery': ('Power-cycle and reload the accepted overlay before '
                         'another run.'),
        }
        raise
    finally:
        (evidence / 'board-status.json').write_text(
            json.dumps(status, indent=2) + '\n')
        if child.isalive():
            child.close(force=True)
