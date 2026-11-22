"""Real small Python children exercise adapter receipts, never component tools."""
import importlib.util,tempfile,unittest
from pathlib import Path
from unittest import mock
H=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('packing_owned_flow',H/'run_host.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Adapter(unittest.TestCase):
 def attempt(self,code,seconds=2,guard=None):
  f.state={'commands':[]}
  with tempfile.TemporaryDirectory(prefix='cell36-owned-adapter-',dir='/tmp') as tmp:
   p=Path(tmp)
   with mock.patch.object(f,'guard',guard or (lambda:None)),mock.patch.object(f,'checkpoint',lambda:None):
    try:result=f.run(['/usr/bin/python3','-c',code],p,p/'log',seconds);error=None
    except BaseException as e:result=None;error=e
   return result,error,f.state['commands'][0]
 def test_success_receipt(self):
  result,error,row=self.attempt('print("ok")');self.assertIsNone(error);self.assertEqual(result['returncode'],0);self.assertFalse(row['owned_receipt']['owned_group_remaining']);self.assertEqual(row['owned_receipt']['group_states'][-1]['members'],[])
 def test_nonzero_keeps_actual_lifecycle(self):
  _,error,row=self.attempt('raise SystemExit(7)');self.assertIsInstance(error,ValueError);self.assertEqual(row['owned_receipt']['returncode'],7);self.assertFalse(row['owned_group_remaining'])
 def test_timeout_receipt_reaped(self):
  _,error,row=self.attempt('import time;time.sleep(10)',.05);self.assertIsInstance(error,TimeoutError);self.assertIn('TimeoutError',row['owned_receipt']['failure']);self.assertFalse(row['owned_group_remaining']);self.assertEqual(row['owned_receipt']['group_states'][-1]['members'],[])
 def test_prelaunch_failure_has_no_spawn_receipt(self):
  def refused():raise RuntimeError('synthetic prelaunch guard')
  _,error,row=self.attempt('print("must not run")',guard=refused);self.assertIsInstance(error,RuntimeError);self.assertIsNone(row['owned_receipt']['owned_pgid']);self.assertIsNone(row['returncode']);self.assertFalse(row['owned_group_remaining'])
if __name__=='__main__':unittest.main()
