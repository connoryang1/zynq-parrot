"""Proof-sensitivity fixtures only; no native/reader/vendor or process launch."""
import copy,importlib.util,json,tarfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('review',HERE/'review.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
class Tests(unittest.TestCase):
 def case(self,role):
  with tarfile.open(HERE/'proofs.tar.gz') as t:return json.load(t.extractfile('archive/stage/'+role+'-audit-ro04/verification.json'))
 def test_all_actual_winning_bits_and_word_corruption(self):
  v=self.case('d-enabled');self.assertEqual(r.target_check(v,'d-enabled')['winning_64bit_L1_writes'],2048)
  bad=copy.deepcopy(v);next(iter(bad['retained_bursts'].values()))['words'][0]['data']^=1
  with self.assertRaisesRegex(ValueError,'all512'):r.target_check(bad,'d-enabled')
 def test_all_slots_and_Iretirement_required(self):
  v=self.case('i-enabled');self.assertEqual(r.target_check(v,'i-enabled')['I_target_instruction_PCs'],4096)
  next(iter(v['retired_instruction_pcs'].values())).pop()
  with self.assertRaisesRegex(ValueError,'all16'):r.target_check(v,'i-enabled')
 def test_off_cannot_impersonate_retention(self):
  v=self.case('d-off');self.assertEqual(r.target_check(v,'d-off')['ordinary_L1_bursts'],256);v['hits']['unexpected']={}
  with self.assertRaisesRegex(ValueError,'publications/hits'):r.target_check(v,'d-off')
if __name__=='__main__':unittest.main()
