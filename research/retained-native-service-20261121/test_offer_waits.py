import io
import unittest
from offer_waits import Offers,edges,run_at,summarize


class OffersTest(unittest.TestCase):
 def test_actual_offer_wait_not_insert_duration(self):
  o=Offers();o.step(0,0,1,True,False,(0x1000,),dict(reason='backend_insert'))
  o.step(10,1,2,True,False,(0x1000,),dict(reason='backend_insert'))
  o.step(20,2,3,True,True,(0x1000,),{})
  self.assertEqual(o.accepted[0]['offer_to_accept_lane_cycles'],2);self.assertEqual(len(o.blocked),2)
 def test_canceled_offer_not_reassigned_to_new_packet(self):
  o=Offers();o.step(0,0,1,True,False,(0x1000,),{})
  o.step(10,1,2,True,True,(0x2000,),{})
  self.assertEqual(o.unaccepted[0]['termination'],'superseded_before_accept')
  self.assertEqual(o.accepted[0]['offer_to_accept_lane_cycles'],0)
 def test_EOF_without_accept_explicit(self):
  o=Offers();o.step(0,0,1,True,False,(0x1000,),{});o.finish()
  self.assertEqual(o.unaccepted[0]['termination'],'unaccepted_at_closed_EOF')
 def test_halfopen_wait_count(self):
  o=Offers();o.step(0,0,1,True,False,(1,),{});o.step(1,1,2,True,False,(1,),{});o.step(2,2,3,True,True,(1,),{})
  r=summarize(o,(1,2));self.assertEqual(r['blocked_valid_sample_cycles'],1);self.assertEqual(r['accepted'],0)
 def test_lane_edge_alignment_required(self):
  runs=[[0,100000,(1,0,0,0,0,'none')]]
  self.assertEqual(run_at(runs,[0],50000)[0],1)
  with self.assertRaisesRegex(ValueError,'edge provenance'):run_at(runs,[0],25000)


class ClockTest(unittest.TestCase):
 def test_packed_opposite_clock_prevalues(self):
  paths={'clk':'TOP.clk','v':'TOP.v'}
  text='#FST\t0\t30\t-12\n#SIGNAL\tclk\t2\t1\tTOP.clk\n#SIGNAL\tv\t1\t2\tTOP.v\n0\t1\t00\n0\t2\t0\n10\t1\t01\n10\t2\t1\n20\t1\t10\n#END\n'
  out=list(edges(io.StringIO(text),paths,set(paths),[('i','clk',0),('d','clk',1)]))
  self.assertEqual([(t,lane,s['v']) for t,lane,s in out],[(10,'i',0),(20,'d',1)])
 def test_missing_EOF_fails(self):
  with self.assertRaisesRegex(ValueError,'EOF'):list(edges(io.StringIO('#FST\t0\t30\t-12\n'),{},set(),[]))


if __name__=='__main__':unittest.main()
