import struct
import unittest
from prepare_image_v2 import coverage,writes


def elf(raw=b'\0\1\0\2\0\3\0\4'):
 d=bytearray(256)+bytearray(raw);d[:6]=b'\x7fELF\x02\x01';struct.pack_into('<Q',d,32,64);struct.pack_into('<HH',d,54,56,1)
 struct.pack_into('<II6Q',d,64,1,6,256,0x80001000,0x80001000,len(raw),len(raw)+8,8)
 return bytes(d)


class Tests(unittest.TestCase):
 def test_all_file_bytes_including_zero(self):
  r=coverage(elf(),'03_0000000080001000_0400030002000100\n')
  self.assertTrue(r['all_file_backed_bytes_exact']);self.assertEqual(r['zero_bytes'],4)
 def test_omitted_zero_word_is_missing_not_assumed_zero(self):
  r=coverage(elf(b'\0'*8),'')
  self.assertFalse(r['all_file_backed_bytes_exact']);self.assertEqual(r['missing_bytes'],8)
 def test_wrong_zero_byte_rejected(self):
  r=coverage(elf(),'03_0000000080001000_0400030002000101\n')
  self.assertFalse(r['all_file_backed_bytes_exact']);self.assertEqual(r['wrong_bytes'],1)
 def test_duplicate_byte_writes_rejected(self):
  with self.assertRaises(ValueError):writes('03_0000000080001000_0000000000000000\n03_0000000080001000_0000000000000000\n')
 def test_mode_only_override(self):
  r=coverage(elf(b'\xff'*8),'03_0000000080001000_000000000000000f\n',(0x80001000,15))
  self.assertTrue(r['all_file_backed_bytes_exact'])
 def test_bss_is_not_filebacked(self):
  r=coverage(elf(),'03_0000000080001000_0400030002000100\n')
  self.assertEqual(r['file_backed_bytes'],8)

if __name__=='__main__':unittest.main()
