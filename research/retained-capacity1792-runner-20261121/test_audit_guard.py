"""No FST reader/target runs: bounded disposable host processes exercise cleanup."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import audit1792

SCRIPT=r'''
import json,os,signal,subprocess,sys
from pathlib import Path
from contextlib import closing
sys.path.insert(0,sys.argv[1]);import audit1792,run1792
root=Path(sys.argv[2]);mode=sys.argv[3];calls=0
sentinel=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True)
(root/'sentinel.json').write_text(json.dumps(dict(pid=sentinel.pid)))
def guard():
 global calls
 calls+=1
 if calls==2:
  if mode in ('interrupt','native-interrupt'):os.kill(os.getpid(),signal.SIGTERM)
  else:raise ValueError('fixture resource breach')
try:
 try:
  command=[sys.executable,'-c','import time; print("host-only",flush=True); time.sleep(30)']
  if mode=='native-interrupt':run1792.owned_run(command,root,os.environ.copy(),root/'reader.stderr',3,lambda:None,guard,lambda:1024)
  else:
   with closing(audit1792.guarded_reader(command,root/'reader.stderr',guard,timeout=3)) as lines:list(lines)
  raise AssertionError('guard failure accepted')
 except (audit1792.AuditInterrupted,run1792.NativeInterrupted,ValueError) as e:
  if mode=='interrupt':assert isinstance(e,audit1792.AuditInterrupted)
  elif mode=='native-interrupt':assert isinstance(e,run1792.NativeInterrupted)
  else:assert 'fixture resource breach' in str(e)
 receipt=json.loads((root/'reader.owned.json').read_text());assert not receipt['owned_group_remaining']
 try:os.killpg(receipt['owned_pgid'],0)
 except ProcessLookupError:pass
 else:raise AssertionError('reader remains')
 assert sentinel.poll() is None,'unrelated host sentinel killed'
 print('HOST_AUDIT_GUARD_PASS '+mode)
finally:
 os.killpg(sentinel.pid,signal.SIGKILL);sentinel.wait(timeout=2)
'''

class AuditGuardTests(unittest.TestCase):
 def host_case(self,mode):
  with TemporaryDirectory() as d:
   root=Path(d);proc=subprocess.Popen([sys.executable,'-B','-c',SCRIPT,str(Path(__file__).parent.resolve()),d,mode],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,text=True)
   try:
    text,_=proc.communicate(timeout=8)
    self.assertEqual(proc.returncode,0,text);self.assertIn('HOST_AUDIT_GUARD_PASS '+mode,text)
   finally:
    if proc.poll() is None:os.killpg(proc.pid,9);proc.wait(timeout=2)
    # A failing fixture still tears down only its explicitly recorded children.
    for name,key in [('sentinel.json','pid'),('reader.owned.json','owned_pgid')]:
     p=root/name
     if p.exists():
      try:os.killpg(json.loads(p.read_text())[key],9)
      except ProcessLookupError:pass
 def test_SIGTERM_reaps_reader_and_preserves_unrelated_host_process(self):
  self.host_case('interrupt');self.host_case('native-interrupt')
 def test_resource_breach_reaps_reader_and_preserves_unrelated_host_process(self):self.host_case('resource')
 def test_reader_hash_mismatch_never_launches(self):
  with TemporaryDirectory() as d:
   p=Path(d)/'reader';p.write_bytes(b'nonexecuted fixture');row=audit1792.bind(p);p.write_bytes(b'changed fixture')
   with patch.object(audit1792.subprocess,'Popen',side_effect=AssertionError('must not launch')) as run:
    with self.assertRaisesRegex(ValueError,'exact admitted FST reader'):audit1792.check_admitted_reader(p,dict(reader=row),dict(reader=row))
    run.assert_not_called()
 def test_failure_cannot_leave_admissible_PASS_file(self):
  with TemporaryDirectory() as d:
   root=Path(d);case=root/'d-enabled';case.mkdir();out=root/'d-enabled-audit';prep=root/'prep.json';prep.write_text('{}')
   (case/'verification.json').write_text('{}');(case/'admission.json').write_text(json.dumps(dict(preparation=audit1792.bind(prep))))
   def failed(args,*unused):
    out.mkdir();args.owned_output=True;(out/'verification.json').write_text('{"state":"PASS"}')
    raise ValueError('fixture late resource breach')
   with patch('sys.argv',['audit1792.py','--case',str(case),'--reader',str(root/'never-executed'),'--out',str(out)]),patch.object(audit1792,'audit_case',side_effect=failed),patch.object(audit1792,'check_budget'),patch.object(audit1792.subprocess,'Popen',side_effect=AssertionError('no reader')):
    with self.assertRaisesRegex(ValueError,'fixture late resource breach'):audit1792.main()
   self.assertFalse((out/'verification.json').exists());self.assertTrue((out/'FAILED-verification.json').exists())

if __name__=='__main__':unittest.main()
