import copy
import json
import unittest
from prepare import HERE
from run_cohort_v3 import validate_resource_admission,ADMISSION_SHA


class ResourceAdmission(unittest.TestCase):
 def setUp(self):
  self.admission=json.loads((HERE/'admission-v3.json').read_text())
  self.authorization=json.loads((HERE/'authorization-v3.json').read_text())
 def accept(self,sha=ADMISSION_SHA):
  validate_resource_admission(self.admission,self.authorization,sha)
 def test_exact_approved_proposal(self):self.accept()
 def test_stale_proposal(self):
  with self.assertRaises(ValueError):self.accept('0'*64)
 def test_old_cap(self):
  self.admission['execution_budget']['fst_limit_bytes']=2**30
  with self.assertRaises(ValueError):self.accept()
 def test_no_runtime_extension(self):
  self.admission['execution_budget']['native_seconds']=2400
  with self.assertRaises(ValueError):self.accept()
 def test_no_adaptive_extra_mode(self):
  self.admission['allowed_initial_modes']=[0,9,6,15]
  with self.assertRaises(ValueError):self.accept()
 def test_receipt_mismatch(self):
  self.authorization['budget']['attempts_per_arm']=2
  with self.assertRaises(ValueError):self.accept()
 def test_changed_model(self):
  self.admission['model']['sha256']='0'*64
  with self.assertRaises(ValueError):self.accept()


if __name__=='__main__':unittest.main()
