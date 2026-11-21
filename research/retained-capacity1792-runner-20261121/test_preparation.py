"""Offline-only profile/refusal tests; never execute a model or FST reader."""
from collections import Counter
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import os
import sys

import frozen
import audit1792
import run1792

def program():
 names='retained_capacity_i_populate_begin retained_capacity_i_verify_begin retained_capacity_i_verified retained_capacity_d_populate_begin retained_capacity_d_verify_begin retained_capacity_d_verified'.split()
 return dict(max_lines=1792,max_sets=256,code_base=0x80008000,data_base=0x80070000,symbols={n:dict(address=0x80000000+4*i) for i,n in enumerate(names)})
def budgets(home):
 return dict(per_trace_cap_bytes=128*1024**2,raw_cohort_cap_bytes=384*1024**2,audit_cohort_cap_bytes=96*1024**2,per_audit_cap_bytes=32*1024**2,other_stage_cap_bytes=32*1024**2,native_runtime_ms=1800000,outer_timeout_s=1980,
 preparation_cap_bytes=16*1024**2,HOME_reserve_bytes=3*1024**3,RAM_stage_cap_bytes=512*1024**2,RAM_reserve_bytes=1024**3,HOME_preparation_path=str(home),storage='HOME')

class PreparationTests(unittest.TestCase):
 def test_all_seven_ways_full_unique_payloads(self):
  for role in ('d-enabled','i-enabled'):
   v=audit1792.Validator(program(),role)
   self.assertEqual(len(v.targets),1792)
   self.assertEqual(Counter((a>>6)&255 for a in v.targets),Counter({s:7 for s in range(256)}))
   self.assertEqual(len({tuple(r['words']) for r in v.targets.values()}),1792)
   self.assertTrue(all(len(r['words'])==8 for r in v.targets.values()))
 def test_wrong_capacity_and_incomplete_execution_refused(self):
  for key in ('max_lines','max_sets'):
   p=program();p[key]=64
   with self.assertRaises(ValueError):audit1792.Validator(p,'d-enabled')
  with self.assertRaises(ValueError):audit1792.Validator(program(),'i-enabled').finish()
  with self.assertRaises(ValueError):run1792.primary_counts('d',1792,(0,1280,0,1280,0,10240))
  run1792.primary_counts('d',1792,(0,1792,0,1792,0,14336))
  run1792.primary_counts('i',1792,(1792,0,1792,0,14336,0))
 def test_common_validator_unchanged_and_exact167_schema(self):
  import audit
  self.assertIs(audit1792.Validator.__mro__[1],audit.Validator)
  s=json.loads((Path(__file__).parent/'schema167.json').read_text())
  self.assertEqual({r['key']:(r['suffix'],r['width']) for r in s['leaves']},audit.selection())
  self.assertEqual(len(s['leaves']),167)
  self.assertEqual(audit.Validator(program(),'d-enabled').lines,64)
 def test_prior_case_and_resource_refusals(self):
  with TemporaryDirectory() as d:
   p=Path(d);run1792.previous_gate(p,'d-enabled')
   with self.assertRaises(FileNotFoundError):run1792.previous_gate(p,'d-off')
   b=budgets(p)
   with patch.object(run1792.shutil,'disk_usage',return_value=SimpleNamespace(free=3*1024**3+400*1024**2)):
    with self.assertRaises(ValueError):run1792.check_budget(p,b)
   with patch.object(run1792.shutil,'disk_usage',return_value=SimpleNamespace(free=5*1024**3)):
    run1792.check_budget(p,b);b['per_trace_cap_bytes']+=1
    with self.assertRaises(ValueError):run1792.check_budget(p,b)
 def test_DRAFT_cannot_execute_model(self):
  with TemporaryDirectory() as d:
   p=Path(d)/'draft.json';p.write_text(json.dumps(dict(schema='retained-capacity1792-preparation-v1',schedule=list(run1792.ORDER),state='DRAFT UNLAUNCHABLE')))
   with patch('sys.argv',['run1792.py','--preparation',str(p),'--role','d-enabled']),patch.object(run1792.subprocess,'run',side_effect=AssertionError('model may not execute')) as run:
    with self.assertRaisesRegex(ValueError,'DRAFT UNLAUNCHABLE'):run1792.main()
    run.assert_not_called()
 def test_no_guest_or_trace_read_in_geometry_test(self):
  with patch.object(run1792.subprocess,'run',side_effect=AssertionError('no target')),patch.object(audit1792.subprocess,'Popen',side_effect=AssertionError('no reader')):
   self.assertEqual(len(audit1792.Validator(program(),'d-off').targets),1792)
 def test_gzip_text_compressed_counter_interface(self):
  with TemporaryDirectory() as d:
   with gzip.open(Path(d)/'events.gz','wt') as stream:
    stream.write('host-only fixture\n');self.assertGreaterEqual(stream.buffer.fileobj.tell(),0)
 def test_owned_timeout_reaps_only_temporary_host_process(self):
  with TemporaryDirectory() as d:
   p=Path(d)/'run.log'
   with self.assertRaises(TimeoutError):
    run1792.owned_run([sys.executable,'-c','import time; time.sleep(30)'],d,os.environ.copy(),p,.05,lambda:None,lambda:None,lambda:1024)
   receipt=json.loads(p.with_suffix('.owned.json').read_text());self.assertFalse(receipt['owned_group_remaining'])
   with self.assertRaises(ProcessLookupError):os.killpg(receipt['owned_pgid'],0)
 def test_owned_log_cap_failure_and_normal_return(self):
  with TemporaryDirectory() as d:
   p=Path(d)/'run.log'
   with self.assertRaises(ValueError):run1792.owned_run([sys.executable,'-c','print("exceeds")'],d,os.environ.copy(),p,2,lambda:None,lambda:None,lambda:1)
   self.assertEqual(p.stat().st_size,0)
   r=run1792.owned_run([sys.executable,'-c','print("host-only")'],d,os.environ.copy(),p,2,lambda:None,lambda:None,lambda:1024)
   self.assertEqual(r.returncode,0);self.assertIn('host-only',p.read_text())

if __name__=='__main__':unittest.main()
