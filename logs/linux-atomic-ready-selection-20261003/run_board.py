#!/usr/bin/env python3
import base64, hashlib, json, os, sys
from pathlib import Path
import pexpect
root = Path('/home/coyang/zynq-parrot')
evidence = Path(__file__).resolve().parent
variant = 'atomic-ready-selection'
outdir = evidence
binary = outdir / 'atomic_ready_selection'
expected = hashlib.sha256(binary.read_bytes()).hexdigest()
payload = base64.b64encode(binary.read_bytes()).decode()
env = os.environ.copy()
env['PYNQ_CONTROL_PROGRAM_SHA256']='be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e'
env['PYNQ_CONTROL_PROGRAM_TIMEOUT_MS']='600000'
status={'status':'running','variant':variant}
with (outdir/'board.log').open('w') as log:
 child=pexpect.spawn(str(root/'codex-skills/bp-fpga-synthesis/scripts/run_pynq_interactive.sh'), ['xilinx@192.168.4.35',str(root/'linux-tests/out/linux-shell.nbf')], env=env,encoding='utf-8',timeout=240)
 child.logfile_read=log; child.setwinsize(50,180)
 try:
  child.expect('Run /bin/sh as init process'); child.expect(r'~ # ')
  child.sendline(': > /tmp/probe.b64'); child.expect(r'~ # ')
  for off in range(0,len(payload),768):
   child.sendline("echo '%s' >> /tmp/probe.b64" % payload[off:off+768]); child.expect(r'~ # ',timeout=30)
  child.sendline('base64 -d /tmp/probe.b64 > /tmp/probe; chmod 755 /tmp/probe'); child.expect(r'~ # ',timeout=30)
  child.sendline('sha256sum /tmp/probe'); child.expect(expected+r'\s+/tmp/probe'); child.expect(r'~ # ')
  print('Guest ELF verified; executing atomic-ready-selection.',flush=True)
  child.sendline('/tmp/probe')
  outcome=child.expect_exact(['[READY-SELECTION] PASS:','[READY-SELECTION] FAIL'],timeout=240)
  child.expect(r'~ # '); child.sendline('echo PROBE_EXIT=$?'); child.expect(r'PROBE_EXIT=([0-9]+)[\r\n]'); exitcode=int(child.match.group(1)); child.expect(r'~ # ')
  child.sendline('poweroff -f'); child.expect_exact('CORE[0] PASS'); child.expect(pexpect.EOF,timeout=90); child.close()
  assert child.exitstatus==0 and child.signalstatus is None and outcome==0 and exitcode==0
  status={'status':'PASS','variant':variant,'binary_sha256':expected,'runner_exit':0}
  print('Atomic-ready-selection PASS; guest powered off.',flush=True)
 except Exception as exc:
  status={'status':'FAIL','variant':variant,'error':repr(exc),'recovery':'Power-cycle and reload overlay before retry.'}; raise
 finally:
  (outdir/'board-status.json').write_text(json.dumps(status,indent=2)+'\n')
  if child.isalive(): child.close(force=True)
