#!/usr/bin/env python3
"""One old immutable-corpus compression/roundtrip; no model, reader or compiler."""
from pathlib import Path
import argparse,contextlib,gzip,hashlib,io,json,lzma,resource,tarfile,time
CAP=32*1024**2
class Checked:
 def __init__(self,f,row):self.f=f;self.r=row;self.h=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.f.read(n);self.h.update(b);self.n+=len(b);return b
 def finish(self):
  if self.n!=self.r['bytes'] or self.h.hexdigest()!=self.r['sha256'] or self.f.read(1):raise ValueError('source member mismatch '+self.r['path'])
class XZ:
 def __init__(self,p):
  self.f=p.open('xb');self.c=lzma.LZMACompressor(format=lzma.FORMAT_XZ,check=lzma.CHECK_SHA256,filters=[dict(id=lzma.FILTER_LZMA2,preset=6,dict_size=64*1024**2)]);self.n=0
 def put(self,b):
  if self.n+len(b)>CAP:raise ValueError('fixed32MiB compressed archive cap; preserve partial')
  self.f.write(b);self.n+=len(b)
 def write(self,b):self.put(self.c.compress(b));return len(b)
 def finish(self):self.put(self.c.flush());self.f.flush();self.f.close()
 def flush(self):self.f.flush()
def main():
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--stage',type=Path,required=True);a=p.parse_args();c=json.loads(a.inputs.read_text());rows=c['members'];stage=a.stage;out=stage/'old-corpus.tar.xz';started=time.monotonic();expected={r['member']:r for r in rows};tar_cache={}
 status={'state':'RUNNING old corpus only','members':len(rows),'dictionary_bytes':64*1024**2,'archive_cap_bytes':CAP,'codec':'LZMA2preset6/XZcheckSHA256/singleprocess','models_adjacent':True}
 try:
  xz=XZ(out)
  with tarfile.open(fileobj=xz,mode='w|',format=tarfile.PAX_FORMAT) as tar:
   raw=a.inputs.read_bytes();ti=tarfile.TarInfo('__inventory__.json');ti.size=len(raw);ti.mode=0o644;ti.mtime=0;tar.addfile(ti,io.BytesIO(raw))
   for i,r in enumerate(rows):
    pr=r['provider'];pid=pr.get('id');record=c['providers'].get(pid) if pid else None
    with contextlib.ExitStack() as stack:
     if record and record['kind']=='gzip':f=stack.enter_context(gzip.open(record['binding']['path'],'rb'))
     elif record and record['kind']=='tar.gz':
      if pid not in tar_cache:tar_cache[pid]=tarfile.open(record['binding']['path'],'r:gz')
      member=tar_cache[pid].getmember(pr['member']);assert member.isfile() and member.size==r['bytes'];f=stack.enter_context(tar_cache[pid].extractfile(member))
     else:f=stack.enter_context(Path(pr['binding']['path']).open('rb'))
     checked=Checked(f,r);ti=tarfile.TarInfo(r['member']);ti.size=r['bytes'];ti.mode=0o755 if r['kind'] in ['full-model','scoped-model','canonical-reader'] else 0o644;ti.mtime=0
     tar.addfile(ti,checked);checked.finish()
    if (i+1)%128==0:print('COPIED',i+1,flush=True)
  xz.finish()
  if time.monotonic()-started>600:raise TimeoutError('fixed600s compression phase')
  roundtrip_started=time.monotonic()
  for f in tar_cache.values():f.close()
  seen=set();raw_total=0
  with lzma.open(out,'rb') as stream:
   with tarfile.open(fileobj=stream,mode='r|') as tar:
    for ti in tar:
     if time.monotonic()-roundtrip_started>180:raise TimeoutError('fixed180s roundtrip phase')
     f=tar.extractfile(ti)
     if ti.name=='__inventory__.json':
      if '__inventory__.json' in seen or f.read()!=a.inputs.read_bytes():raise ValueError('inventory member mismatch')
     else:
      if ti.name not in expected or ti.name in seen:raise ValueError('missing/unexpected/duplicate member '+ti.name)
      r=expected[ti.name];h=hashlib.sha256();n=0
      while True:
       b=f.read(1024*1024)
       if not b:break
       h.update(b);n+=len(b)
      if n!=r['bytes'] or h.hexdigest()!=r['sha256']:raise ValueError('roundtrip mismatch '+ti.name)
      raw_total+=n
     seen.add(ti.name)
   while True:
    pad=stream.read(1024*1024)
    if not pad:break
    if any(pad):raise ValueError('nonzero trailing tar data')
  if seen!=set(expected)|{'__inventory__.json'}:raise ValueError('incomplete roundtrip member coverage')
  status.update(state='PASS old corpus fits fixed32MiB and every original byte roundtrips; future freshproof fit not guaranteed',archive_bytes=out.stat().st_size,archive_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),raw_member_bytes=raw_total,roundtripped_members=len(rows),canonical_actual_regeneration='PENDING separate ROOTreader admission; recipe/hashes included, no gzipwrapper identity claim')
 except BaseException as e:status.update(state='FAIL preserved; no retry/dictionary/cap change',error=repr(e));raise
 finally:
  status.update(elapsed_seconds=time.monotonic()-started,maxrss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss);(stage/'codec-result.json').write_text(json.dumps(status,indent=2)+'\n');print(status['state'],flush=True)
if __name__=='__main__':main()
