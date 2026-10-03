#!/usr/bin/env python3
import hashlib,json,os
from pathlib import Path
import pexpect
root=Path('/home/coyang/zynq-parrot'); evidence=Path(__file__).resolve().parent
binary=evidence/'prefetch_switch_register_probe'; digest=hashlib.sha256(binary.read_bytes()).hexdigest()
nbf=root/'linux-tests/out/linux-shell.nbf'; nbf_digest=hashlib.sha256(nbf.read_bytes()).hexdigest()
assert nbf_digest=='af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3'
status={'status':'running','stage':'boot','binary_sha256':digest,'linux_nbf_sha256':nbf_digest,'recovery_required':True}
env=os.environ.copy(); env['PYNQ_CONTROL_PROGRAM_SHA256']='be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e'; env['PYNQ_CONTROL_PROGRAM_TIMEOUT_MS']='300000'
child=None
try:
  with (evidence/'register-probe-board.log').open('w') as log:
    child=pexpect.spawn(str(root/'codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh'),['xilinx@192.168.4.35',str(nbf)],env=env,encoding='utf-8',timeout=300)
    child.logfile_read=log; child.setwinsize(50,180); child.delaybeforesend=.005
    child.expect_exact('Run /bin/sh as init process'); child.expect(r'~ # ')
    status['stage']='transfer'
    for cmd in (evidence/'register-probe-transfer.txt').read_text().splitlines(): child.sendline(cmd); child.expect(r'~ # ',timeout=60)
    child.sendline('sha256sum /tmp/prefetch_switch_register_probe'); child.expect(digest+r'\s+/tmp/prefetch_switch_register_probe[\r\n]'); child.expect(r'~ # ')
    status['stage']='measurement'; child.sendline('/tmp/prefetch_switch_register_probe')
    outcome=child.expect_exact(['[PREFETCH-SWITCH-REG] PASS','[PREFETCH-SWITCH-REG] FAIL'],timeout=120)
    child.expect(r'~ # '); child.sendline('echo PROBE_EXIT=$?'); child.expect(r'PROBE_EXIT=([0-9]+)[\r\n]'); probe_exit=int(child.match.group(1)); child.expect(r'~ # ')
    status.update(stage='poweroff',probe_exit=probe_exit,probe_outcome='PASS' if outcome==0 else 'FAIL')
    child.sendline('poweroff -f'); child.expect_exact('CORE[0] PASS'); child.expect(pexpect.EOF,timeout=120); child.close()
    if child.exitstatus!=0 or child.signalstatus is not None: raise RuntimeError(f'runner exit={child.exitstatus} signal={child.signalstatus}')
    status.update(status='PASS' if outcome==0 and probe_exit==0 else 'MEASURED_FAIL',stage='complete',runner_exit=0,core_pass=True,recovery_required=False)
    print(f'Register probe outcome={status["status"]}.',flush=True)
except Exception as exc:
  status.update(status='INFRA_FAIL',error=repr(exc)); raise
finally:
  if child is not None and child.isalive(): child.close(force=True)
  (evidence/'register-probe-status.json').write_text(json.dumps(status,indent=2)+'\n')
