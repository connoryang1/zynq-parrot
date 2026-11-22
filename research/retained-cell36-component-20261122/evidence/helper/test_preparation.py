"""Source/admission checks only; no Verilator, reader or component invocation."""
import copy,importlib.util,json,unittest
from pathlib import Path
H=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('packing_flow',H/'run_host.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f)
A=json.loads(f.A.read_text())
class Checks(unittest.TestCase):
 def test_source_preflight(self):self.assertEqual(f.preflight(A)['expected_runtimes'],12)
 def test_fixed_complete_cases(self):
  a=copy.deepcopy(A);a['cases']=a['cases'][:-1]
  with self.assertRaisesRegex(ValueError,'family/budgets'):f.preflight(a)
 def test_fixed_budgets(self):
  a=copy.deepcopy(A);a['limits']['family_FST_bytes']=8*1024**2
  with self.assertRaisesRegex(ValueError,'family/budgets'):f.preflight(a)
 def test_changed_input_rejected(self):
  a=copy.deepcopy(A);a['inputs'][0]['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'input drift'):f.preflight(a)
 def test_controller_equivalence_and_negative(self):
  old=(H/'baseline-8df.sv.txt').read_bytes();new=(f.WORKTREE/f.REL).read_bytes();self.assertTrue(f.unchanged_controller(old,new))
  changed=new.replace(b'&& !lookup_v_i[lane]',b'&& lookup_v_i[lane]')
  self.assertNotEqual(new,changed)
  with self.assertRaisesRegex(ValueError,'FSM/epochs/RR/handshake'):f.unchanged_controller(old,changed)
 def test_prospective_cell_footprint(self):
  # Count addressable36b cells, not an inferred or fitted BRAM result.
  self.assertEqual((512+(34-6-8)+8+35)//36,15)
  self.assertEqual((512+(34-6)+2+35)//36,16)
  self.assertEqual((28*1024)//15,1911)
if __name__=='__main__':unittest.main()
