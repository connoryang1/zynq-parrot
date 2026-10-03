#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path

import pexpect

root = Path('/home/coyang/zynq-parrot')
evidence = Path(__file__).resolve().parent
nbf = evidence / 'mt_atomic_resident_selector_benchmark_fpga.nbf'
nbf_sha = hashlib.sha256(nbf.read_bytes()).hexdigest()
env = os.environ.copy()
env['PYNQ_CONTROL_PROGRAM_SHA256'] = (
    'be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e')
env['PYNQ_CONTROL_PROGRAM_TIMEOUT_MS'] = '600000'
status = {'status': 'running', 'nbf_sha256': nbf_sha}

with (evidence / 'resident-physical.log').open('w') as log:
    child = pexpect.spawn(
        str(root / 'codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh'),
        ['xilinx@192.168.4.35', str(nbf)], env=env, encoding='utf-8',
        timeout=600)
    child.logfile_read = log
    child.setwinsize(50, 180)
    try:
        child.expect_exact('[BSG-PASS] atomic resident selector')
        child.expect_exact('CORE[0] PASS')
        child.expect(pexpect.EOF, timeout=90)
        child.close()
        if child.exitstatus != 0 or child.signalstatus is not None:
            raise RuntimeError(
                f'runner exit={child.exitstatus} signal={child.signalstatus}')
        status = {'status': 'PASS', 'nbf_sha256': nbf_sha,
                  'runner_exit': 0}
        print('Physical resident atomic selector PASS.', flush=True)
    except Exception as exc:
        status = {'status': 'FAIL', 'nbf_sha256': nbf_sha,
                  'error': repr(exc),
                  'recovery': 'Power-cycle and reload overlay before retry.'}
        raise
    finally:
        (evidence / 'resident-physical-status.json').write_text(
            json.dumps(status, indent=2) + '\n')
        if child.isalive():
            child.close(force=True)
