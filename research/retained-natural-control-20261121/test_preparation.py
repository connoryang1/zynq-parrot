import struct
import unittest
from prepare import patch_mode,elf_bytes
from protocol import parse,expected_sum,PASS


def fixture(mode=15):
 def h(v):return hex(v)
 cap=(1<<63)|(3<<56)|(8<<48)|(1280<<32)|(1280<<16)
 rows=['RETAINED_RESUME_PROTOCOL whole-v1',f'RETAINED_RESUME_CONFIG lookup actors=4 resident=2 kib=32 warm=8 timed=8 mode={h(mode)}']
 for a in range(4):
  rows.append(f'RETAINED_RESUME_REGION actor={a} base={h(0x80100008+a*0x8008)} bytes=0x8000 runs=0x10 sum={h(expected_sum(a))}')
  if a:rows.append(f'RETAINED_RESUME_STACK actor={a} base={h(0x80010000+a*0x1000)} bytes=0x1000')
 rows+=['RETAINED_RESUME_STATUS initial='+h(cap)+' ready='+h(cap|mode)+' checked='+h(cap|mode|0x400)+' final='+h(cap)+' start_polls=0x2 end_polls=0x3',
 'RETAINED_RESUME_PHASES whole_begin=0x1 whole_end=0x64 whole_cycles=0x63 warm_begin=0xa timed_begin=0x14 timed_end=0x1e ring_cycles=0xa control_begin=0x2 checks_done=0x28 teardown_begin=0x32',PASS,'CORE PASS','Returning from ps_main with RC: 0','BSG PASS']
 return '\n'.join(rows)+'\n'


class Tests(unittest.TestCase):
 def test_patch_all_supported(self):
  # Memory NBF doubleword, exact file-backed all-ones sentinel.
  nbf='03_0000000080001000_ffffffffffffffff\n'
  for mode in (0,9,6,15):self.assertIn(f'{mode:016x}',patch_mode(nbf,0x80001000,mode))
 def test_patch_reject_mode(self):
  with self.assertRaises(ValueError):patch_mode('03_0000000080001000_ffffffffffffffff\n',0x80001000,2)
 def test_patch_reject_stale(self):
  with self.assertRaises(ValueError):patch_mode('03_0000000080001000_0000000000000000\n',0x80001000,15)
 def test_patch_reject_unaligned(self):
  with self.assertRaises(ValueError):patch_mode('',0x80001001,15)
 def test_non_file_backed(self):
  data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';struct.pack_into('<Q',data,32,64);struct.pack_into('<HH',data,54,56,0)
  with self.assertRaises(ValueError):elf_bytes(data,0x80001000,8)
 def test_valid_both_arms(self):
  for mode in (0,15):self.assertEqual(parse(fixture(mode),mode)['mode'],mode)
 def test_no_admit_unreviewed_modes(self):
  with self.assertRaises(ValueError):parse(fixture(9),9)
 def test_missing_host_completion(self):
  with self.assertRaises(ValueError):parse(fixture().replace('BSG PASS',''),15)
 def test_status_mismatch(self):
  text=fixture().replace('mode=0xf','mode=0x0')
  with self.assertRaises(ValueError):parse(text,15)
 def test_checksum_mismatch(self):
  text=fixture().replace(hex(expected_sum(0)),'0x1')
  with self.assertRaises(ValueError):parse(text,15)
 def test_duplicate_row(self):
  with self.assertRaises(ValueError):parse('RETAINED_RESUME_PROTOCOL whole-v1\n'+fixture(),15)
 def test_whole_excludes_teardown_rejected(self):
  with self.assertRaises(ValueError):parse(fixture().replace('teardown_begin=0x32','teardown_begin=0x70'),15)
 def test_corpus_stack_overlap(self):
  with self.assertRaises(ValueError):parse(fixture().replace('base=0x80011000','base=0x80100008'),15)
 def test_actual_calloc_bounds_not_rounded(self):
  result=parse(fixture(),15);self.assertEqual(result['regions'][0]['base']&63,8)
 def test_wrong_capacity_bit(self):
  text=fixture().replace('initial=0x8308050005000000','initial=0x0308050005000000')
  self.assertNotEqual(text,fixture())
  with self.assertRaises(ValueError):parse(text,15)

if __name__=='__main__':unittest.main()
