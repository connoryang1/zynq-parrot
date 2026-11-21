import unittest
from hp0_closed_pair import request_mapping,expected_signals


class Mapping(unittest.TestCase):
 def test_actual_zero_base_translation(self):
  r=request_mapping({'BP.araddr':0x80001238,'dram_base':0,'araddr':0x1238},'ar')
  self.assertEqual(r,dict(BP_PA=0x80001238,dram_base=0))
 def test_nonzero_base_and_write(self):
  r=request_mapping({'BP.awaddr':0x80002000,'dram_base':0x10000000,'awaddr':0x10002000},'aw')
  self.assertEqual(r['BP_PA'],0x80002000)
 def test_mismatched_mapping_rejected(self):
  with self.assertRaisesRegex(ValueError,'translation mismatch'):request_mapping({'BP.araddr':0x80001238,'dram_base':0,'araddr':0x80001238},'ar')
 def test_unknown_mapping_not_assumed(self):
  with self.assertRaisesRegex(ValueError,'unknown'):request_mapping({'BP.araddr':0x80001238,'dram_base':None,'araddr':0x1238},'ar')
 def test_watched_bus_and_actual_both_uce_clocks(self):
  fields=expected_signals()
  self.assertLess(len(fields),256)
  for key in ('araddr','awaddr','wdata','ext.rdata','core.rdata','ext.bresp','core.bresp','i.clk','d.clk','i.aborted','be.pc','be.global'):
   self.assertIn(key,fields)


if __name__=='__main__':unittest.main()
