import io
import unittest
from audit_retained_case import Ports,consume,selections

PHASES=dict(whole_begin=10,whole_end=100,timed_begin=20,timed_end=60)
DATA=(1<<511)|(0x123456789abcdef0<<256)|0xfedcba9876543210


def vector(**overrides):
 v={k:0 for k in selections()};v['store_state_0']=v['store_state_1']=1
 v.update(overrides);return v


def start(mode=15):
 p=Ports(PHASES,mode)
 for lane in range(2):p.lane(lane,vector(store_reset_i=3))
 return p


def publish(p,lane=0,address=0x80008000,data=DATA):
 bit=1<<lane
 p.lane(lane,vector(global_cycle=21,store_insert_v_i=bit,store_insert_ready_o=bit,
                    **{f'store_insert_addr_i_{lane}':address,f'store_insert_data_i_{lane}':data}))
 p.lane(lane,vector(global_cycle=40,store_insert_done_o=bit,store_insert_published_o=bit))


class Ownership(unittest.TestCase):
 def test_be_startup_reset_epoch_restarts_empty_cycle_count(self):
  p=start();p.be(vector(be_reset=1));p.be(vector(global_cycle=2));p.be(vector(be_reset=1));p.be(vector(global_cycle=0))
  self.assertEqual(p.last_cycle,0)
 def test_be_reset_after_architectural_start_rejected(self):
  p=start();p.be(vector(be_reset=1));p.be(vector(global_cycle=1,instret=1,pc=0x80000000))
  with self.assertRaisesRegex(ValueError,'after program startup'):p.be(vector(be_reset=1))
 def test_preinitial_reset_edge_has_no_ownership(self):
  p=Ports(PHASES,15);p.lane(1,vector());p.lane(1,vector(store_reset_i=2))
  self.assertTrue(p.reset_seen[1])
 def test_preinitial_reset_activity_cannot_be_discarded(self):
  with self.assertRaisesRegex(ValueError,'before observed reset'):Ports(PHASES,15).lane(1,vector(store_lookup_v_i=2,store_lookup_ready_o=2))
 def test_both_lanes_full512b_provenance(self):
  p=start()
  for lane in range(2):
   publish(p,lane);b=1<<lane
   p.lane(lane,vector(global_cycle=41,store_lookup_v_i=b,store_lookup_ready_o=b,**{f'store_lookup_addr_i_{lane}':0x80008038}))
   p.lane(lane,vector(global_cycle=59,store_resp_v_o=b,store_resp_ready_i=b,store_resp_hit_o=b,**{f'store_resp_data_o_{lane}':DATA}))
  r=p.report()
  for lane in ('i','d'):self.assertEqual(r['counts']['timed_ring'][lane]['lookup_hit'],1)
 def test_wrong_high_payload_word(self):
  p=start();publish(p)
  p.lane(0,vector(global_cycle=41,store_lookup_v_i=1,store_lookup_ready_o=1,store_lookup_addr_i_0=0x80008000))
  with self.assertRaisesRegex(ValueError,'512b'):p.lane(0,vector(global_cycle=50,store_resp_v_o=1,store_resp_ready_i=1,store_resp_hit_o=1,store_resp_data_o_0=DATA^(1<<511)))
 def test_same_set_different_tag_invalidates_provenance(self):
  p=start();publish(p,1)
  p.lane(1,vector(global_cycle=41,store_invalidate_v_i=2,store_invalidate_addr_i_1=0x8000c000))
  p.lane(1,vector(global_cycle=42,store_lookup_v_i=2,store_lookup_ready_o=2,store_lookup_addr_i_1=0x80008000))
  with self.assertRaisesRegex(ValueError,'provenance'):p.lane(1,vector(global_cycle=50,store_resp_v_o=2,store_resp_ready_i=2,store_resp_hit_o=2,store_resp_data_o_1=DATA))
 def test_cancel_cannot_publish(self):
  p=start();p.lane(0,vector(global_cycle=20,store_insert_v_i=1,store_insert_ready_o=1,store_insert_addr_i_0=0x80008000))
  p.lane(0,vector(global_cycle=21,store_insert_cancel_i=1))
  with self.assertRaisesRegex(ValueError,'killed'):p.lane(0,vector(global_cycle=22,store_insert_done_o=1,store_insert_published_o=1))
 def test_clear_pending_lookup_still_requires_one_miss(self):
  p=start();p.lane(0,vector(global_cycle=20,store_lookup_v_i=1,store_lookup_ready_o=1))
  p.lane(0,vector(global_cycle=21,store_clear_i=1))
  p.lane(0,vector(global_cycle=22,store_resp_v_o=1,store_resp_ready_i=1))
  self.assertEqual(p.report()['counts']['whole']['i']['lookup_miss'],1)
 def test_undrained_lookup_rejected(self):
  p=start();p.lane(1,vector(global_cycle=20,store_lookup_v_i=2,store_lookup_ready_o=2))
  with self.assertRaisesRegex(ValueError,'undrained'):p.report()
 def test_terminal_without_owner(self):
  with self.assertRaisesRegex(ValueError,'without accepted owner'):start().lane(0,vector(store_insert_done_o=1))
 def test_off_arm_engagement_rejected(self):
  p=start(0);publish(p)
  with self.assertRaisesRegex(ValueError,'off arm'):p.report()
 def test_halfopen_and_accepted_mutation(self):
  p=start()
  for c,state in ((9,1),(10,1),(20,0),(60,1),(100,1)):
   p.lane(1,vector(global_cycle=c,store_invalidate_v_i=2,store_state_1=state))
  r=p.report()['counts']
  self.assertEqual(r['whole']['d']['mutation_invalidate_asserted_cycles'],3)
  self.assertEqual(r['whole']['d']['mutation_invalidate_accepted'],2)
  self.assertEqual(r['timed_ring']['d']['mutation_invalidate_asserted_cycles'],1)
  self.assertEqual(r['timed_ring']['d'].get('mutation_invalidate_accepted',0),0)


def stream():
 fields=selections();rows=['#FST\t0\t1000\t-12'];handles={k:n+1 for n,k in enumerate(fields)}
 for k,v in fields.items():rows.append(f'#SIGNAL\t{k}\t{v["width"]}\t{handles[k]}\t{v["path"]}')
 old={}
 # Different independent periods: Iclock6, Dclock10; BE follows I.
 for t in range(31):
  v=vector(global_cycle=t//6,store_reset_i=3 if t<11 else 0,
           be_reset=1 if t<11 else 0,be_clock=(t//3)&1,
           store_clk_i=((t//3)&1)|(((t//5)&1)<<1))
  for k,value in v.items():
   if old.get(k)!=value:rows.append(f'{t}\t{handles[k]}\t{value:0{fields[k]["width"]}b}')
  old=v
 rows.append('#END');return '\n'.join(rows)+'\n'


class Transport(unittest.TestCase):
 def test_independent_lane_edges(self):
  r=consume(io.StringIO(stream()),selections(),PHASES,0)
  self.assertEqual(r['sampled_lane_edges'],[5,3])
 def test_no_eof(self):
  with self.assertRaisesRegex(ValueError,'EOF'):consume(io.StringIO(stream().replace('#END\n','')),selections(),PHASES,0)
 def test_wrong_width(self):
  text=stream().replace('#SIGNAL\tstore_clk_i\t2\t','#SIGNAL\tstore_clk_i\t1\t')
  with self.assertRaisesRegex(ValueError,'width'):consume(io.StringIO(text),selections(),PHASES,0)


if __name__=='__main__':unittest.main()
