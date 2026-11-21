"""Strict whole-v1 guest parser; complete host/CORE checks remain mandatory."""
import importlib.util
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
PASS='[BSG-PASS] checked retained lifecycle lookup whole'
MASK=(1<<64)-1
HEX=r'(0x[0-9a-fA-F]{1,16})'


def mix(x):
 x^=x>>30;x=x*0xbf58476d1ce4e5b9&MASK;x^=x>>27;x=x*0x94d049bb133111eb&MASK;return x^(x>>31)


def expected_sum(actor):
 seed=0x95cba137+actor*0x9e3779b9
 return sum(mix(seed^(1+mix(seed+epoch*64+q)%1024)) for epoch in range(16) for q in range(64) if q&7!=7)&MASK


def expected_loads(actor):
 slots=[0]*2048
 for key in range(1,1025):
  slot=mix(key)%2048
  while slots[slot]:slot=(slot+1)%2048
  slots[slot]=key
 seed=0x95cba137+actor*0x9e3779b9;result=[]
 for epoch in range(16):
  count=0
  for q in range(64):
   key=1+mix(seed+epoch*64+q)%1024+(1024 if q&7==7 else 0)
   slot=mix(key)%2048
   for _ in range(2048):
    count+=1
    if not slots[slot]:break
    if slots[slot]==key:count+=1;break
    slot=(slot+1)%2048
   else:raise ValueError('logical table unexpectedly full')
  result.append(count)
 return result


def status(v,mode,idle=False):
 allowed=(1<<63)|(3<<56)|(255<<48)|(0xffffffff<<16)|0xf0f
 if v&~allowed or v>>63!=1 or (v>>56)&3!=3 or (v>>48)&255!=8 or (v>>32)&65535!=1280 or (v>>16)&65535!=1280 or v&15!=mode or (idle and v&0x300):raise ValueError('wrong raw capability/control/geometry/idle status')


def parse(text,mode,exit_code=0):
 if mode not in (0,15):raise ValueError('initial admission permits only off0/joint15')
 spec=importlib.util.spec_from_file_location('checker',ROOT/'testing/check_run.py');checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker);checker.check_transcript(text,exit_code)
 lines=text.replace('\r','').splitlines();rows=[s for s in lines if s.startswith('RETAINED_RESUME_') or s==PASS]
 kinds=['RETAINED_RESUME_PROTOCOL','RETAINED_RESUME_CONFIG','RETAINED_RESUME_REGION','RETAINED_RESUME_REGION','RETAINED_RESUME_STACK','RETAINED_RESUME_REGION','RETAINED_RESUME_STACK','RETAINED_RESUME_REGION','RETAINED_RESUME_STACK','RETAINED_RESUME_STATUS','RETAINED_RESUME_PHASES',PASS]
 if [s.split(' ')[0] if s!=PASS else s for s in rows]!=kinds:raise ValueError('missing/duplicate/out-of-order rows')
 if rows[0]!='RETAINED_RESUME_PROTOCOL whole-v1' or text.index(PASS)>checker.CORE_PASS.search(text).start():raise ValueError('wrong protocol/completion order')
 config=re.fullmatch(r'RETAINED_RESUME_CONFIG lookup actors=4 resident=2 kib=32 warm=8 timed=8 mode='+HEX,rows[1])
 if not config or int(config[1],16)!=mode:raise ValueError('wrong mode/config')
 regions=[];stacks=[]
 for row in rows[2:9]:
  r=re.fullmatch(r'RETAINED_RESUME_REGION actor=([0-3]) base='+HEX+' bytes='+HEX+' runs='+HEX+' sum='+HEX,row)
  if r:
   actor,base,size,runs,total=[int(r[1])]+[int(x,16) for x in r.groups()[1:]]
   if size!=32768 or runs!=16 or total!=expected_sum(actor):raise ValueError('wrong region/checksum/count')
   regions.append(dict(context=actor,base=base,bytes=size,runs=runs,checksum=total));continue
  r=re.fullmatch(r'RETAINED_RESUME_STACK actor=([1-3]) base='+HEX+' bytes='+HEX,row)
  if not r or int(r[3],16)!=4096:raise ValueError('bad stack row')
  stacks.append(dict(context=int(r[1]),base=int(r[2],16),bytes=4096))
 if [r['context'] for r in regions]!=[0,1,2,3] or [r['context'] for r in stacks]!=[1,2,3]:raise ValueError('actor/stack bijection')
 intervals=regions+stacks
 for n,a in enumerate(intervals):
  if a['base']<0x80000000 or a['base']+a['bytes']>0x88000000:raise ValueError('private interval outside guest RAM')
  for b in intervals[n+1:]:
   if max(a['base'],b['base'])<min(a['base']+a['bytes'],b['base']+b['bytes']):raise ValueError('private regions/stacks overlap')
 names=['initial','ready','checked','final','start_polls','end_polls'];pattern='RETAINED_RESUME_STATUS'+''.join(' '+n+'='+HEX for n in names)
 r=re.fullmatch(pattern,rows[9])
 if not r:raise ValueError('bad raw status row')
 states=dict(zip(names,[int(x,16) for x in r.groups()]));status(states['initial'],0);status(states['ready'],mode,True);status(states['checked'],mode);status(states['final'],0,True)
 if not all(1<=states[n]<=65536 for n in ('start_polls','end_polls')):raise ValueError('poll bound')
 names=['whole_begin','whole_end','whole_cycles','warm_begin','timed_begin','timed_end','ring_cycles','control_begin','checks_done','teardown_begin']
 r=re.fullmatch('RETAINED_RESUME_PHASES'+''.join(' '+n+'='+HEX for n in names),rows[10])
 if not r:raise ValueError('bad complete phase row')
 phase=dict(zip(names,[int(x,16) for x in r.groups()]));ordered=[phase[n] for n in ('whole_begin','control_begin','warm_begin','timed_begin','timed_end','checks_done','teardown_begin','whole_end')]
 if any(a>=b for a,b in zip(ordered,ordered[1:])) or phase['whole_cycles']!=phase['whole_end']-phase['whole_begin'] or phase['ring_cycles']!=phase['timed_end']-phase['timed_begin']:raise ValueError('whole/ring chronology or arithmetic')
 return dict(mode=mode,regions=regions,stacks=stacks,status=states,phases=phase,scope='Complete checked whole-v1 bare-metal lifecycle. No trace-mechanism/capacity/performance acceptance by parser alone.')
