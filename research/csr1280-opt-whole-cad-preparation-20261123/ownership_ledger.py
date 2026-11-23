"""Pure identity-chain ownership. A process group/token is never sufficient."""
import hashlib,json

def need(v,m):
 if not v:raise ValueError(m)
def key(row):return (row['pid'],row['startticks'])
class Ledger:
 def __init__(self,worker):self.worker=worker;self.known={};self.events=[];self.pids={}
 def snapshot(self,s,evidence):
  w=s.get('worker')
  need(w is not None or (s.get('status')!='RUNNING' and bool(self.known)),'exact active worker identity')
  if w is not None:
   need(key(w)==key(self.worker),'exact active worker identity')
   need(w['pgrp']==w['sid']==w['pid'] and w['argv_tokens']==self.worker['argv_tokens'],'worker group/session/argv identity')
  rows={}
  for name in ('descendants','worker_group','all_vivado','global_vendor_tools'):
   for r in s.get(name,[]):
    if r['pid'] in rows:need(key(rows[r['pid']])==key(r),'same-snapshot PID reuse')
    rows[r['pid']]=r
  if w is not None:rows[w['pid']]=w
  # Reject a reused identity even if it has since become a child of the owner.
  for r in rows.values():
   if r['pid'] in self.pids:need(self.pids[r['pid']]==r['startticks'],'recorded PID reused with different start time')
  current=set()
  for r in rows.values():
   k=key(r)
   if k in self.known:
    need(r['pgrp']==r['sid']==self.worker['pid'],'recorded ownership changed SID/PGID')
    current.add(k)
  if not self.known:
   k=key(w);e=dict(identity=list(k),parent=None,evidence=evidence,kind='exact-worker-root',sid=w['sid'],pgrp=w['pgrp']);self._append(e);current.add(k)
  changed=True
  while changed:
   changed=False
   for r in rows.values():
    k=key(r)
    if k in current:continue
    parent=rows.get(r['ppid'])
    if parent is None or key(parent) not in current:continue
    need(r['pgrp']==r['sid']==self.worker['pid'],'new descendant escaped worker SID/PGID')
    need(parent['startticks']<=r['startticks'],'child predates current parent identity')
    e=dict(identity=list(k),parent=list(key(parent)),evidence=evidence,kind='child-of-currently-proved-parent',sid=r['sid'],pgrp=r['pgrp']);self._append(e);current.add(k);changed=True
  # All known orphans keep their original proof; group membership alone creates no proof.
  unknown_group=[r for r in s.get('worker_group',[]) if key(r) not in current]
  foreign=[r for r in s.get('global_vendor_tools',[]) if key(r) not in current]
  return dict(owned_current=[list(k) for k in sorted(current)],foreign_vendor_tools=foreign,unknown_worker_group=unknown_group,proven_orphans=[list(key(r)) for r in rows.values() if key(r) in current and r['ppid']==1],events=len(self.events))
 def _append(self,event):
  identity=tuple(event['identity']);need(identity not in self.known,'append-only identity unique')
  prior=self.events[-1]['event_sha256'] if self.events else None
  event=dict(event,previous_sha256=prior);event['event_sha256']=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
  self.events.append(event);self.known[identity]=event;self.pids[identity[0]]=identity[1]
