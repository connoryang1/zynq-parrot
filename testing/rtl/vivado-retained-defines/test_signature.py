import importlib.util
from pathlib import Path
import unittest
s=importlib.util.spec_from_file_location('signature',Path(__file__).with_name('check_signature.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def fixture(values):
 value=0
 for field in values:value=(value<<32)|field
 return 'GND g (.G(\\<const0> ));\nVCC v (.P(\\<const1> ));\n'+''.join(f'OBUF \\out[{b}] \n (.I(\\<const{(value>>b)&1}> ), .O(signature[{b}]));\n' for b in range(192))

class Check(unittest.TestCase):
 def test_all_fields(self):
  v=[1,1280,1280,256,1,200];self.assertEqual(m.signature(fixture(v)),v)
 def test_defaults(self):
  v=[0,64,64,64,0,0];self.assertEqual(m.signature(fixture(v)),v)
 def test_missing(self):
  with self.assertRaises(ValueError):m.signature(fixture([0]*6).rsplit('OBUF',1)[0])
 def test_duplicate(self):
  t=fixture([0]*6)
  with self.assertRaises(ValueError):m.signature(t+t[t.index('OBUF'):])
 def test_wrong_driver(self):
  with self.assertRaises(ValueError):m.signature(fixture([0]*6).replace('GND','NOT_GND'))
 def test_unknown_constant(self):
  with self.assertRaises(ValueError):m.signature(fixture([0]*6).replace('const0>','random>'))

if __name__=='__main__':unittest.main()
