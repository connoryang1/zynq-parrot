import copy
import io
import json
import unittest
from dcache_intervals import REQUIRED,accepted_packets,normal_records,match_packets


def stream():
 keys=sorted(REQUIRED);widths={k:(64 if k=='global_cycle' else 34 if k=='data_address' else 8 if k=='data_mask' else 2 if k=='data_opcode' else 1) for k in keys}
 handles={k:n+1 for n,k in enumerate(keys)};paths={k:'TOP.fixture.'+k for k in keys}
 rows=['#FST\t0\t20\t-12']
 for k in keys:rows.append(f'#SIGNAL\t{k}\t{widths[k]}\t{handles[k]}\t{paths[k]}')
 old={}
 for t in range(20):
  cycle=max(0,(t-2)//2+1)
  v=dict(cache_clock=t&1,reset=int(t<2),global_cycle=cycle,data_v=int(2<=t<18),data_yumi=1,data_opcode=0,data_address=0x80001000,data_mask=1<<(cycle-1) if 1<=cycle<=8 else 0,critical=int(cycle==1),complete=int(cycle==8))
  for k in keys:
   if old.get(k)!=v[k]:rows.append(f'{t}\t{handles[k]}\t{v[k]:0{widths[k]}b}')
  old=v
 rows.append('#END');return '\n'.join(rows)+'\n',paths


def events():
 rows=[dict(event='reference',global_cycle=0,context=0,thread=0,address='0x80001000',line='0x80001000',operation='load',outcome='miss',target=True,epoch=0,phase='timed')]
 for n in range(8):rows.append(dict(event='fill_beat',global_cycle=n+1,line='0x80001000',mask=1<<n))
 rows.append(dict(event='fill_complete',global_cycle=8,line='0x80001000'))
 return [json.dumps(e) for e in rows]


class Service(unittest.TestCase):
 def setUp(self):
  self.text,self.paths=stream();self.references,self.misses=normal_records(events(),dict(whole_begin=0,whole_end=20))
 def test_actual_dualphase_clock_affinity_and_flags(self):
  p,c=accepted_packets(io.StringIO(self.text),self.paths,0)
  self.assertEqual(c['period_FST_ticks'],2);self.assertEqual(c['global_cycle_to_Dposedge_tick_offset'],1)
  match_packets(self.misses,p)
  self.assertEqual(self.misses[0]['durations'],dict(miss_to_first_Dcache_write=1,miss_to_critical_receive_flag=1,miss_to_full_L1_write=8))
 def test_missing_packet_fails_bijection(self):
  p,_=accepted_packets(io.StringIO(self.text),self.paths,0)
  with self.assertRaisesRegex(ValueError,'sequence differs'):match_packets(self.misses,p[:-1])
 def test_no_critical_flag_not_assumed_ready(self):
  p,_=accepted_packets(io.StringIO(self.text),self.paths,0)
  for e in p:e['critical_receive_flag']=False
  with self.assertRaisesRegex(ValueError,'critical/full'):match_packets(self.misses,p)
 def test_missing_saved_eof_rejected(self):
  with self.assertRaisesRegex(ValueError,'EOF'):accepted_packets(io.StringIO(self.text.replace('#END\n','')),self.paths,0)
 def test_wrong_physical_line_fails(self):
  p,_=accepted_packets(io.StringIO(self.text),self.paths,0);p[0]['line']='0x80002000'
  with self.assertRaisesRegex(ValueError,'sequence differs'):match_packets(self.misses,p)


if __name__=='__main__':unittest.main()
