from pathlib import Path
import tempfile
import unittest
from verify_finalized_trace import framing


def fixture(end=100,count=1):
 h=bytearray(74);h[1:9]=(73).to_bytes(8,'big');h[17:25]=end.to_bytes(8,'big');h[65:73]=count.to_bytes(8,'big')
 return bytes(h)+bytes([8])+(24).to_bytes(8,'big')+(0).to_bytes(8,'big')+(100).to_bytes(8,'big')


class Framing(unittest.TestCase):
 def check(self,data):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'fixture.fst';p.write_bytes(data);return framing(p)
 def test_complete_sections(self):self.assertTrue(self.check(fixture())['all_section_bytes_exactly_cover_file'])
 def test_recoverable_but_unfinalized_header_rejected(self):
  with self.assertRaisesRegex(ValueError,'unfinalized'):self.check(fixture(end=0))
 def test_torn_body_rejected(self):
  with self.assertRaises(ValueError):self.check(fixture()[:-1])
 def test_wrong_final_time_rejected(self):
  with self.assertRaisesRegex(ValueError,'mismatch'):self.check(fixture(end=101))
 def test_wrong_finalized_section_count(self):
  with self.assertRaisesRegex(ValueError,'mismatch'):self.check(fixture(count=2))
 def test_trailing_unframed_byte(self):
  with self.assertRaisesRegex(ValueError,'partial'):self.check(fixture()+b'0')


if __name__=='__main__':unittest.main()
