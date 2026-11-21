import json
import unittest
from describe_hit_lines import describe


def rows(*events):return [json.dumps(e) for e in events]


class HitLines(unittest.TestCase):
 def fixture(self):
  normal=[];retained=[]
  for start,address,actor in ((10,'0x1000',0),(20,'0x1000',0),(30,'0x2000',1)):
   normal+=rows(dict(event='reference',global_cycle=start,line=address,outcome='miss',operation='load',target=True,epoch=0,context=actor),dict(event='fill_complete',global_cycle=start+5,line=address))
   retained+=rows(dict(event='lookup_response',lane='d',global_cycle=start+2,address=address,hit=True))
  return normal,retained
 def test_repeated_line_not_extra_unique_capacity(self):
  n,r=self.fixture();c=describe(n,r,dict(whole_begin=10,whole_end=40,timed_begin=20,timed_end=30))
  self.assertEqual(c['whole']['total_hits'],3);self.assertEqual(c['whole']['distinct_request_target_lines'],2)
  self.assertEqual(c['timed_ring']['total_hits'],1)
 def test_mismatched_line_fails(self):
  n,r=self.fixture();r[0]=r[0].replace('0x1000','0x3000')
  with self.assertRaisesRegex(ValueError,'provenance'):describe(n,r,dict(whole_begin=0,whole_end=40,timed_begin=0,timed_end=40))
 def test_init_hits_not_called_request_work(self):
  n,r=self.fixture();n=[line.replace('"epoch": 0','"epoch": null') for line in n]
  c=describe(n,r,dict(whole_begin=0,whole_end=40,timed_begin=0,timed_end=40))
  self.assertEqual(c['whole']['request_target_hits'],0);self.assertEqual(c['whole']['total_hits'],3)


if __name__=='__main__':unittest.main()
