#!/usr/bin/env python3
"""Host-only protocol checks; no component build/run or RAM writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('host',HERE/'run_host.py')
host=importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)

class Preparation(unittest.TestCase):
 def test_sealed_normalization(self):
  admission=json.loads(host.ADMISSION.read_text())
  actual=Path(admission['candidate']).read_bytes()
  expected=host.normalize(Path(admission['sealed_backend']).read_bytes(),Path(admission['sealed_module']).read_bytes())
  self.assertEqual(actual,expected)
  self.assertEqual(actual.count(b'module bp_retained_epoch_ram\n'),1)
  self.assertLess(actual.index(b'wire [epoch_width_p-1:0] line_epoch, inv_epoch;'),actual.index(b'wire wrap ='))
  self.assertLess(actual.index(b'wire last_slot;'),actual.index(b'assign last_slot ='))
 def test_reference_only_module_rename(self):
  admission=json.loads(host.ADMISSION.read_text())
  original=Path(admission['original']).read_bytes()
  self.assertEqual((HERE/'bp_retained_line_store_reference.sv').read_bytes(),original.replace(b'module bp_retained_line_store\n',b'module bp_retained_line_store_reference\n'))
 def test_six_normal_clock_cases(self):
  normal=[c for c in host.CASES if not c[-1]]
  self.assertEqual([(c[1],c[2],c[3],c[4]) for c in normal],[(0,3,1,2)])
  self.assertEqual(len(normal)*2+4,6)
 def test_negative_mutation_localized(self):
  raw=Path(json.loads(host.ADMISSION.read_text())['candidate']).read_bytes()
  changed=host.negative_source(raw)
  self.assertNotEqual(raw,changed)
  self.assertEqual(changed.replace(b"if (write_v_i && write_addr_i != '0)",b'if (write_v_i)'),raw)
  with self.assertRaises(ValueError):host.negative_source(b'wrong input')
 def test_negative_rejects_at_allcell(self):
  text='EPOCH_NEGATIVE_WITNESS tick=70 total=2 epochI=0 epochD=1 protocol=0\nRETAINED_TEST_FAIL: cycle/payload/RAM-port miter mismatch at tick70\n'
  self.assertEqual(host.negative_gate(text)['epochD'],1)
  for changed in [text.replace('epochD=1','epochD=0'),text.replace('protocol=0','protocol=1'),text+text,text+'RETAINED_METADATA_MITER_PASS ']:
   with self.assertRaises(ValueError):host.negative_gate(changed)
 def test_namespace_refuses_without_write(self):
  with tempfile.TemporaryDirectory() as directory:
   absent=Path(directory)/'absent'
   stage=Path(directory)/'stage'
   with patch.object(host,'SENTINEL',absent),patch.object(host,'STAGE',stage):
    with self.assertRaises(FileNotFoundError):host.namespace_check()
    self.assertFalse(stage.exists())
   sentinel=Path(directory)/'sentinel'
   sentinel.mkdir()
   with patch.object(host,'SENTINEL',sentinel),patch.object(host,'STAGE',stage):
    with self.assertRaises(ValueError):host.namespace_check()
    self.assertFalse(stage.exists())
 def test_hash_drift_rejected_before_git(self):
  admission=json.loads(host.ADMISSION.read_text())
  admission['inputs'][0]['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'frozen input drift'):host.preflight(admission)
 def test_budget_change_rejected(self):
  admission=json.loads(host.ADMISSION.read_text())
  admission['limits']['stage_bytes']+=1
  with self.assertRaisesRegex(ValueError,'fixed budgets'):host.preflight(admission)
 def test_explicit_diagnostics_only(self):
  admission=json.loads(host.ADMISSION.read_text())
  host.diagnostic_only_gate(admission)
  self.assertNotIn('rootp',(HERE/'driver.cpp').read_text())
 def test_corrected_or_still_present(self):
  text=(HERE/'retained_metadata_wrapper.sv').read_text()
  self.assertIn('mismatch_o[l] = epoch_mismatch;',text)
  self.assertIn('mismatch_o[l] |= ({lookup_ready',text)
  self.assertIn('epoch_mismatch |= dut.lane_fsm[l].distributed_epochs.epoch_ram.mem[q]',text)
  self.assertNotIn('        mismatch_o[l] = ({lookup_ready',text)

if __name__=='__main__':unittest.main()
