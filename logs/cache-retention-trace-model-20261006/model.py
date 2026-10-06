#!/usr/bin/env python3
import collections, hashlib, json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
traces=['scan','trie-stream','pointer-compute']
paths={n:root/f'logs/context-resume-footprint-20261002/{n}.json' for n in traces}
SETS=64; WAYS=8; RESIDENTS=(1,2)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def simulate(accesses,reserved):
    # Each entry is [tag, owner, last_use]. owner is 1/2 for protected ways or 0 shared.
    sets=[]
    for _ in range(SETS):
        ways=[]
        for owner in RESIDENTS:
            ways += [[None,owner,-1] for _ in range(reserved)]
        ways += [[None,0,-1] for _ in range(WAYS-2*reserved)]
        sets.append(ways)
    stats=collections.defaultdict(lambda:collections.Counter(accesses=0,hits=0,misses=0))
    for pass_i in range(2):
      if pass_i == 1:
        stats=collections.defaultdict(lambda:collections.Counter(accesses=0,hits=0,misses=0))
      for offset,a in enumerate(accesses):
        tick=pass_i*len(accesses)+offset
        ctx=int(a['context']); line=int(a['address'])//64; idx=line%SETS; tag=line//SETS
        st=stats[ctx]; st['accesses']+=1
        ways=sets[idx]
        hit=next((w for w in ways if w[0]==tag),None)
        if hit is not None:
            st['hits']+=1; hit[2]=tick; continue
        st['misses']+=1
        # Contexts without reserved ownership use shared ways. Residents fill an
        # invalid protected way first, then shared capacity, preserving their
        # protected minimum while allowing overflow.
        candidates=[]
        if ctx in RESIDENTS:
            candidates=[w for w in ways if w[1]==ctx and w[0] is None]
        if not candidates:
            candidates=[w for w in ways if w[1]==0 and w[0] is None]
        if not candidates:
            candidates=[w for w in ways if w[1]==0]
        if not candidates and ctx in RESIDENTS:
            candidates=[w for w in ways if w[1]==ctx]
        if not candidates:
            raise RuntimeError((ctx,reserved))
        victim=min(candidates,key=lambda w:w[2]); victim[0]=tag; victim[2]=tick
    return {str(k):dict(v,miss_rate=v['misses']/v['accesses']) for k,v in sorted(stats.items())}

def shared(accesses):
    sets=[[] for _ in range(SETS)]; stats=collections.defaultdict(lambda:collections.Counter(accesses=0,hits=0,misses=0))
    for pass_i in range(2):
      if pass_i == 1:
        stats=collections.defaultdict(lambda:collections.Counter(accesses=0,hits=0,misses=0))
      for offset,a in enumerate(accesses):
        tick=pass_i*len(accesses)+offset
        ctx=int(a['context']); line=int(a['address'])//64; idx=line%SETS; tag=line//SETS; st=stats[ctx]; st['accesses']+=1
        hit=next((x for x in sets[idx] if x[0]==tag),None)
        if hit: st['hits']+=1; hit[1]=tick
        else:
            st['misses']+=1
            if len(sets[idx])<WAYS: sets[idx].append([tag,tick])
            else: min(sets[idx],key=lambda x:x[1])[:]=[tag,tick]
    return {str(k):dict(v,miss_rate=v['misses']/v['accesses']) for k,v in sorted(stats.items())}

def aggregate(stats,contexts):
    a=sum(stats.get(str(c),{}).get('accesses',0) for c in contexts); m=sum(stats.get(str(c),{}).get('misses',0) for c in contexts)
    return {'accesses':a,'misses':m,'miss_rate':m/a if a else None}

out={'method':'64-set, 8-way line-LRU trace model. Contexts 1 and 2 receive 1/2/3 protected ways per set; residents fill protected invalid ways, then use shared ways for overflow. Context 0 uses only shared ways. Replay each trace once to warm model state, then report a second identical pass including context-0 interference.','inputs':{str(p.relative_to(root)):sha(p) for p in paths.values()},'traces':{},'limits':['Data-access traces do not model instruction-cache accesses.','The simple LRU model does not reproduce every BlackParrot replacement, write, refill, or initial-state detail.','Protected-way ownership is a proposed policy, not implemented RTL.','Contexts 1 and 2 are the paired workers in scan/trie; pointer-compute has only context 1 activity in the captured data trace.','Repeating the complete trace removes cold initialization but assumes the captured access sequence is representative of a following interval.']}
for name,p in paths.items():
    accesses=json.loads(p.read_text())['accesses']
    base=shared(accesses)
    entry={'shared8':{'by_context':base,'resident':aggregate(base,RESIDENTS),'context0':aggregate(base,(0,))},'protected':{}}
    for r in (1,2,3):
        s=simulate(accesses,r)
        entry['protected'][str(r)]={'reserved_ways_each':r,'shared_ways':WAYS-2*r,'by_context':s,'resident':aggregate(s,RESIDENTS),'context0':aggregate(s,(0,))}
    out['traces'][name]=entry
Path(__file__).with_name('results.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
