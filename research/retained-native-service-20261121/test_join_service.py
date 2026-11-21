import copy
import unittest
from join_service import distribution,read_line,matching_reads,union_length
from index_hp0_times import transaction_times


class Join(unittest.TestCase):
 def setUp(self):
  self.read=dict(BP_PA=0x80001000,len=7,size=3,burst=1,request_time=60,beats=[dict(time=90)])
  self.miss=dict(reference=dict(line='0x80001000',global_cycle=5),accepted_beats=[dict(tick=100)])
  self.clock=dict(period_FST_ticks=10,global_cycle_to_Dposedge_tick_offset=0)
 def test_actual_physical_line_window(self):
  self.assertEqual(matching_reads(self.miss,{0x80001000:[self.read]},self.clock),[self.read])
 def test_no_read_does_not_invent_L2_class(self):self.assertEqual(matching_reads(self.miss,{},self.clock),[])
 def test_duplicate_read_ambiguity_fails(self):
  with self.assertRaisesRegex(ValueError,'ambiguous'):matching_reads(self.miss,{0x80001000:[self.read,self.read]},self.clock)
 def test_RLAST_must_precede_full_L1_write(self):
  self.read['beats'][0]['time']=101
  with self.assertRaisesRegex(ValueError,'not complete'):matching_reads(self.miss,{0x80001000:[self.read]},self.clock)
 def test_burst_address_semantics(self):
  self.assertEqual(read_line(self.read),0x80001000)
  self.read['BP_PA']+=8
  with self.assertRaisesRegex(ValueError,'crosses'):read_line(self.read)
  self.read['burst']=2;self.assertEqual(read_line(self.read),0x80001000)
 def test_union_is_not_sum(self):self.assertEqual(union_length([(0,10),(5,15)],(4,12)),8)
 def test_negative_deltas_retained(self):
  r=distribution([-3,0,0,5]);self.assertEqual(r['minimum'],-3);self.assertEqual(r['lower_median'],0)
 def test_axi_timestamp_cycle_affinity_checked(self):
  r=dict(request_time=100,request_cycle=5,complete=7,beats=[dict(time=120,cycle=7)],wbeats=[])
  points,offset=transaction_times(dict(BP_reads=[r],BP_writes=[]),10)
  self.assertEqual(offset,50);self.assertEqual(points,{100,120})
  r['beats'][0]['cycle']=6
  with self.assertRaisesRegex(ValueError,'mismatch'):transaction_times(dict(BP_reads=[r],BP_writes=[]),10)


if __name__=='__main__':unittest.main()
