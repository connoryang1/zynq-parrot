import copy
import json
import unittest
from compare_closed_audits import load_sequence,compare_guests,join_d_lookup_refills


def rows(*events):return [json.dumps(e)+'\n' for e in events]
def ref(address='0x1008',**kw):
 e=dict(event='reference',target=True,context=0,epoch=0,phase='timed',address=address,operation='load',outcome='hit');e.update(kw);return e


class Sequence(unittest.TestCase):
 def test_outcomes_and_timing_do_not_change_checked_work(self):
  a=load_sequence(rows(ref(global_cycle=1)),{0:(0x1000,32)})
  b=load_sequence(rows(ref(global_cycle=100,outcome='miss')),{0:(0x1000,32)})
  self.assertEqual(a,b)
 def test_offset_change_changes_identity(self):
  a=load_sequence(rows(ref()),{0:(0x1000,32)})
  b=load_sequence(rows(ref('0x1010')),{0:(0x1000,32)})
  self.assertNotEqual(a['normalized_sha256'],b['normalized_sha256'])
 def test_wrong_actor_region_rejected(self):
  with self.assertRaisesRegex(ValueError,'another actor'):load_sequence(rows(ref('0x2000')),{0:(0x1000,32)})
 def test_target_request_store_rejected(self):
  with self.assertRaisesRegex(ValueError,'mutation'):load_sequence(rows(ref(operation='store')),{0:(0x1000,32)})
 def test_setup_target_stores_excluded_from_query_sequence(self):
  self.assertEqual(load_sequence(rows(ref(epoch=None,operation='store')),{0:(0x1000,32)})['load_count'],0)


class Joined(unittest.TestCase):
 def setUp(self):
  self.normal=rows(dict(event='reference',global_cycle=10,outcome='miss',operation='load',line='0x1000'),dict(event='fill_complete',global_cycle=30,line='0x1000'))
  self.side=rows(dict(event='lookup_accept',lane='d',global_cycle=11,address='0x1000'),dict(event='lookup_response',lane='d',global_cycle=20,address='0x1000',hit=True))
  self.phases=dict(whole_begin=10,whole_end=40,timed_begin=20,timed_end=30)
 def test_side_hit_services_real_ordinary_miss(self):
  r=join_d_lookup_refills(self.normal,self.side,self.phases)
  self.assertEqual(r['timed_ring'],dict(lookups=1,hits=1,misses=0))
 def test_wrong_physical_line_rejected(self):
  self.side=[line.replace('0x1000','0x2000') for line in self.side]
  with self.assertRaisesRegex(ValueError,'matching accepted'):join_d_lookup_refills(self.normal,self.side,self.phases)
 def test_lookup_without_ordinary_miss_rejected(self):
  with self.assertRaises(ValueError):join_d_lookup_refills([],self.side,self.phases)
 def test_no_refill_is_not_complete(self):
  with self.assertRaisesRegex(ValueError,'fully refilled'):join_d_lookup_refills(self.normal[:1],self.side,self.phases)
 def test_unretained_store_miss_is_allowed(self):
  normal=[line.replace('"load"','"store"') for line in self.normal]
  self.assertEqual(join_d_lookup_refills(normal,[],self.phases)['whole']['lookups'],0)


if __name__=='__main__':unittest.main()
