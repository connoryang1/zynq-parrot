import io
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from copy import deepcopy
from fst_adapter import consume,suffixes,core,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_analyze_resume_data_reuse_vcd import Trace,vcd,widths


def fixture():
 t=Trace();t.miss(0x80000000);t.fill(0x80000000,0);t.hit(0x80000008)
 t.miss(0x80001000);t.fill(0x80001000,0);t.hit(0x80001008)
 return t


def as_fst(trace):
 text=vcd(trace.samples,opposite=True);keys=suffixes();reverse={'TOP.'+name:k for k,name in keys.items()};mapping={};rows=['#FST\t0\t999999\t-12'];bitsizes={k:max(widths()[k],max(int(s[k]).bit_length() for s in trace.samples)) for k in keys}
 for line in text.splitlines():
  f=line.split()
  if f[:1]==['$var']:
   key=reverse['TOP.'+f[4]];handle=len(mapping)+1;mapping[f[3]]=(handle,key);rows.append(f'#SIGNAL\t{key}\t{bitsizes[key]}\t{handle}\tTOP.{f[4]}')
 stamp=0;groups={}
 for line in text.splitlines():
  if line.startswith('#'):stamp=int(line[1:])
  elif line.startswith('b'):
   bits,code=line[1:].split();handle,key=mapping[code];groups.setdefault(stamp,{})[handle]=bits.zfill(bitsizes[key])
 for stamp,group in sorted(groups.items()):
  for handle,bits in group.items():rows.append(f'{stamp}\t{handle}\t{bits}')
 rows.append('#END');return '\n'.join(rows)+'\n'


class Tests(unittest.TestCase):
 def test_original_vcd_exact_events_and_stats(self):
  t=fixture();original=[];selected=[];r=core.analyze(io.StringIO(vcd(t.samples,opposite=True)),emit=original.append);s=consume(io.StringIO(as_fst(t)),emit=selected.append)
  self.assertEqual(original,selected);self.assertEqual(r['stats'],s['stats']);self.assertEqual(r['coverage'],s['coverage']);self.assertEqual(r['active_dcache_edges'],s['active_dcache_edges'])
 def test_startup_reset_before_any_access_restarts_epoch(self):
  t=fixture();first=deepcopy(t.samples[0]);one=deepcopy(t.samples[1]);reset=deepcopy(first);reset['global_cycle']=2
  wrapped=SimpleNamespace(samples=[first,one,reset]+t.samples)
  r=consume(io.StringIO(as_fst(wrapped)))
  self.assertEqual(len(r['startup_reset_epochs']),1);self.assertEqual(r['stats']['accepted_cached_references'],4);self.assertEqual(r['stats']['observed_initialization_slots'],512)
 def test_postaccess_reset_still_rejected(self):
  t=fixture();r=deepcopy(t.samples[0]);r['global_cycle']=t.samples[-1]['global_cycle']+1
  with self.assertRaisesRegex(core.EvidenceError,'reset after active'):consume(io.StringIO(as_fst(SimpleNamespace(samples=t.samples+[r]))))
 def test_startup_reset_does_not_invent_initial_tags(self):
  t=fixture();preamble=[deepcopy(t.samples[0]),deepcopy(t.samples[1]),deepcopy(t.samples[0])]
  # Drop the actual64-row clear epoch. The earlier partial clear cannot count.
  with self.assertRaises(core.EvidenceError):consume(io.StringIO(as_fst(SimpleNamespace(samples=preamble+t.samples[65:]))))
 def test_no_eof(self):
  with self.assertRaises(core.EvidenceError):consume(io.StringIO(as_fst(fixture()).replace('#END\n','')))
 def test_missing_signal(self):
  text='\n'.join(l for l in as_fst(fixture()).splitlines() if not l.startswith('#SIGNAL\tclock\t'))+'\n'
  with self.assertRaises(core.EvidenceError):consume(io.StringIO(text))
 def test_wrong_path(self):
  text=as_fst(fixture()).replace('TOP.be.clk_i','TOP.unrelated.clock')
  with self.assertRaises(core.EvidenceError):consume(io.StringIO(text))
 def test_duplicate_declaration(self):
  text=as_fst(fixture());decl=next(l for l in text.splitlines() if l.startswith('#SIGNAL'))
  with self.assertRaises(core.EvidenceError):consume(io.StringIO(text.replace(decl,decl+'\n'+decl)))
 def test_unknown_active_sample_rejected(self):
  text=as_fst(fixture());line=next(l for l in text.splitlines() if l.startswith('#SIGNAL\tsets\t'));f=line.split('\t');handle=f[3];size=int(f[2])
  rows=text.splitlines();changed=[]
  for row in rows:
   parts=row.split('\t')
   if len(parts)==3 and parts[0].isdigit() and parts[1]==handle and int(parts[0])>0:row=parts[0]+'\t'+handle+'\t'+'x'*size
   changed.append(row)
  with self.assertRaises(core.EvidenceError):consume(io.StringIO('\n'.join(changed)+'\n'))

if __name__=='__main__':unittest.main()
