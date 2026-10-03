#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import pexpect

parser=argparse.ArgumentParser()
parser.add_argument('--mask',type=int,required=True)
parser.add_argument('--samples',type=int,default=7)
parser.add_argument('--requests',type=int,default=4096)
args=parser.parse_args()
if args.mask < 1 or args.mask > 15: raise SystemExit('mask must be 1..15')
root=Path('/home/coyang/zynq-parrot')
evidence=Path(__file__).resolve().parent
binary=evidence/'request_benchmark_dynamic_diagnostic'
transfer=evidence/'diagnostic-transfer.txt'
expected=hashlib.sha256(binary.read_bytes()).hexdigest()
linux_nbf=root/'linux-tests/out/linux-shell.nbf'
expected_nbf='af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3'
assert hashlib.sha256(linux_nbf.read_bytes()).hexdigest()==expected_nbf
prefix=f'diagnostic-mask{args.mask}'
status={'status':'running','stage':'boot','mode_mask':args.mask,'samples':args.samples,
        'requests_per_worker':args.requests,'binary_sha256':expected,
        'linux_nbf_sha256':expected_nbf,'recovery_required':True}
env=os.environ.copy()
env['PYNQ_CONTROL_PROGRAM_SHA256']='be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e'
env['PYNQ_CONTROL_PROGRAM_TIMEOUT_MS']='420000'
child=None
try:
  with (evidence/f'{prefix}-board.log').open('w') as log:
    child=pexpect.spawn(str(root/'codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh'),
      ['xilinx@192.168.4.35',str(linux_nbf)],env=env,encoding='utf-8',timeout=420)
    child.logfile_read=log; child.setwinsize(50,180); child.delaybeforesend=0.005
    child.expect_exact('Run /bin/sh as init process'); child.expect(r'~ # ')
    status['stage']='transfer'
    commands=transfer.read_text().splitlines()
    for i,cmd in enumerate(commands):
      child.sendline(cmd); child.expect(r'~ # ',timeout=60)
      if i%100==0: print(f'Transfer {i+1}/{len(commands)} commands',flush=True)
    child.sendline('sha256sum /tmp/request_benchmark_dynamic')
    child.expect(expected+r'\s+/tmp/request_benchmark_dynamic[\r\n]'); child.expect(r'~ # ')
    status['stage']='measurement'
    cmd=(f'/tmp/request_benchmark_dynamic --workers 2 --hardware --requests {args.requests} '
         f'--samples {args.samples} --data-kib 2048 --mode-mask {args.mask}')
    child.sendline(cmd); child.expect(r'\[REQUEST-BENCH\] PASS[\r\n]',timeout=420)
    output=(child.before+child.after).replace('\r\n','\n').replace('\r','')
    (evidence/f'{prefix}-stdout.txt').write_text(output)
    rows=re.findall(r'^RESULT sample=(\d+) order=(\d+) mode=([^ ]+) ns=(\d+) requests=(\d+) checksum=(\d+) cycles=(\d+)$',output,re.M)
    expected_rows=args.samples*args.mask.bit_count()
    if len(rows)!=expected_rows: raise RuntimeError(f'expected {expected_rows} rows, got {len(rows)}')
    if len({int(r[5]) for r in rows})!=1: raise RuntimeError('checksum mismatch')
    if any(int(r[4])!=2*args.requests for r in rows): raise RuntimeError('request count mismatch')
    child.expect(r'~ # '); child.sendline('echo REQUEST_EXIT=$?'); child.expect(r'REQUEST_EXIT=0[\r\n]'); child.expect(r'~ # ')
    status.update(stage='poweroff',request_exit=0,result_rows=len(rows))
    child.sendline('poweroff -f'); child.expect_exact('CORE[0] PASS'); child.expect(pexpect.EOF,timeout=120); child.close()
    if child.exitstatus!=0 or child.signalstatus is not None: raise RuntimeError(f'runner exit={child.exitstatus} signal={child.signalstatus}')
    status.update(status='PASS',stage='complete',runner_exit=0,core_pass=True,recovery_required=False)
    print(f'Diagnostic mask {args.mask} PASS.',flush=True)
except Exception as exc:
  status.update(status='FAIL',error=repr(exc)); raise
finally:
  if child is not None and child.isalive(): child.close(force=True)
  (evidence/f'{prefix}-status.json').write_text(json.dumps(status,indent=2)+'\n')
