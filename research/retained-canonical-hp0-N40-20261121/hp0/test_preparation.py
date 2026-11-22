#!/usr/bin/env python3
"""Light source/binding guard checks only; never invokes the audit/reader."""
import ast,copy,gzip,hashlib,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('guard',R/'root_guard.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
A=json.loads((R/'admission.DRAFT.json').read_text())
class Checks(unittest.TestCase):
 def test_admission_pin(self):
  self.assertIn(guard.bind(R/'admission.DRAFT.json')['sha256'],(R/'root_guard.py').read_text())
 def test_good_and_wrong_byte_binding(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'tool.py';p.write_bytes(b'real tool\n');b=guard.bind(p);guard.verify(b)
   p.write_bytes(b'changed\n')
   with self.assertRaises(ValueError):guard.verify(b)
 def test_wrong_hash_and_length(self):
  b=guard.bind(R/'review.py');bad=dict(b,sha256='0'*64)
  with self.assertRaises(ValueError):guard.verify(bad)
  with self.assertRaises(ValueError):guard.verify(dict(b,bytes=b['bytes']+1))
 def test107_union(self):
  ss=A['selection107'];self.assertEqual(len(ss),107);self.assertEqual(len({s['key'] for s in ss}),107)
  old=json.loads(Path(A['native_canonical_precedent']['admission']['path']).read_text())['selection99']
  self.assertEqual(set(s['key'] for s in ss)-set(s['key'] for s in old),{'shim.delay','shim.cycle','shim.r.occupancy','shim.r.full','shim.r.full_stalls','shim.b.occupancy','shim.b.full','shim.b.full_stalls'})
 def test_exact_closed_inputs(self):
  for field in ['fst','source_list','source_archive','strict_original','original_fullcore_closure','strict_proof','log','process']:
   guard.verify(A[field])
  p=json.loads(Path(A['strict_proof']['path']).read_text());self.assertTrue(p['accepted']);self.assertEqual(p['bindings']['fst']['sha256'],A['fst']['sha256'])
  self.assertEqual(json.loads(gzip.decompress(Path(A['process']['path']).read_bytes()))['returncode'],-6)
 def test_actual_source_common_and_tools(self):
  src=json.loads(gzip.decompress(Path(A['source_list']['path']).read_bytes()))['sources']
  for b in A['common_path_source_current_exact']:
   self.assertEqual({k:src[b['path']][k] for k in b},b)
  guard.verify(A['implementation']);self.assertTrue(all('/home/coyang/zynq-parrot-linux-capacity/' in b['path'] for b in A['implementation']))
 def test_budgets_and_argv(self):
  self.assertEqual(guard.HC,32*1024**2);self.assertEqual(guard.RC,64*1024**2);self.assertEqual(guard.CC,128*1024**2)
  self.assertLessEqual(guard.size(R.parent)+guard.HC-guard.size(R),guard.CC-65536)
  av=A['argv'];self.assertEqual(av[av.index('--delay')+1],'40');self.assertEqual(av[av.index('--fst')+1],A['fst']['path'])
  self.assertEqual(av[av.index('--out')+1],str(R/'audit01'));self.assertFalse((R/'audit01').exists())
 def test_compile_no_execution(self):
  for name in ['root_guard.py','review.py']:
   ast.parse((R/name).read_text(),filename=name)
if __name__=='__main__':unittest.main()
