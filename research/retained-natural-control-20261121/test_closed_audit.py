import copy
import io
import json
import unittest
from audit_closed_case import admission,summarize,MODEL_SHA,ELF_SHA,CAP
from protocol import parse
from prepare import HERE
from test_preparation import fixture


class CompletionAdmission(unittest.TestCase):
 def setUp(self):
  self.text=fixture(0);self.guest=parse(self.text,0,0)
  self.meta=json.loads((HERE/'admission-v3.json').read_text())['dcache_metadata_template']
  self.meta['regions']=[dict(context=v['context'],base=hex(v['base']),bytes=v['bytes']) for v in self.guest['regions']]
  for k in ('whole_begin','whole_end'):self.meta[k+'_cycle']=self.guest['phases'][k]
  self.row=dict(mode=0,state='COMPLETE-checks-PASS-awaiting-full-trace-audit',returncode=0,trace={'bytes':100})
  self.cohort=dict(state='COMPLETE-both-arms-awaiting-full-trace-audit-no-performance-inference',model={'sha256':MODEL_SHA},elf={'sha256':ELF_SHA},runs=[self.row])
 def admit(self):return admission(self.cohort,0,self.text,self.guest,self.meta)
 def test_complete_case(self):self.assertEqual(self.admit(),self.row)
 def test_active_cohort_rejected(self):
  self.cohort['state']='running'
  with self.assertRaisesRegex(ValueError,'still active'):self.admit()
 def test_partial_arm_even_recoverable_eof_rejected(self):
  self.row['state']='FAIL-preserved-no-result'
  with self.assertRaisesRegex(ValueError,'failed/partial'):self.admit()
 def test_at_cap_not_complete(self):
  self.row['trace']['bytes']=CAP
  with self.assertRaisesRegex(ValueError,'at-limit'):self.admit()
 def test_missing_host_completion(self):
  self.text=self.text.replace('BSG PASS','')
  with self.assertRaises(ValueError):self.admit()
 def test_wrong_expected_counts(self):
  self.meta['expected_target_loads_by_context']['0'][0]+=1
  with self.assertRaisesRegex(ValueError,'independent request expectation'):self.admit()
 def test_different_allocation_bounds(self):
  self.meta['regions'][0]['base']='0x80000000'
  with self.assertRaisesRegex(ValueError,'allocations'):self.admit()
 def test_wrong_whole_bounds(self):
  self.meta['whole_end_cycle']+=1
  with self.assertRaisesRegex(ValueError,'WHOLE bounds'):self.admit()
 def test_closed_zero_stays_auditable_after_joint_failure(self):
  self.cohort['state']='STOPPED-failure-preserved-no-retry'
  self.cohort['runs'].append(dict(mode=15,state='FAIL-preserved-no-result'))
  self.admit()


class Windows(unittest.TestCase):
 def test_half_open_boundaries(self):
  events=[]
  for cycle in (9,10,19,20,29,30):events.append(json.dumps(dict(event='reference',global_cycle=cycle,operation='load',outcome='hit',target=True))+'\n')
  r=summarize(events,dict(whole_begin=10,whole_end=30,timed_begin=20,timed_end=30))
  self.assertEqual(r['program']['reference'],6);self.assertEqual(r['whole']['reference'],4);self.assertEqual(r['timed_ring']['reference'],2)
 def test_cycle_reversal(self):
  events=[json.dumps(dict(event='fill_beat',global_cycle=c)) for c in (10,9)]
  with self.assertRaisesRegex(ValueError,'cycle reversal'):summarize(events,dict(whole_begin=0,whole_end=30,timed_begin=10,timed_end=20))


if __name__=='__main__':unittest.main()
