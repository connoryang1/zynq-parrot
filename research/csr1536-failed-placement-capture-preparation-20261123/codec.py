#!/usr/bin/env python3
"""Lossless live-file member compression/roundtrip; no model or FST reader."""
import argparse,hashlib,io,json,lzma,os,tarfile,time
from pathlib import Path
CAP=192*1024**2
class Writer:
 def __init__(self,p):self.f=p.open('xb');self.c=lzma.LZMACompressor(format=lzma.FORMAT_XZ,check=lzma.CHECK_SHA256,filters=[dict(id=lzma.FILTER_LZMA2,preset=6,dict_size=64*1024**2)]);self.n=0
 def put(self,b):
  if self.n+len(b)>CAP:raise ValueError('fixed192MiB own archive ceiling inside NEW320MiB postterminal preservation union; preserve partial')
  self.f.write(b);self.n+=len(b)
 def write(self,b):self.put(self.c.compress(b));return len(b)
 def flush(self):self.f.flush()
 def finish(self):self.put(self.c.flush());self.f.flush();self.f.close()
class Checked:
 def __init__(self,f,row):self.f=f;self.row=row;self.h=hashlib.sha256();self.n=0
 def read(self,n=-1):
  b=self.f.read(n);self.h.update(b);self.n+=len(b);return b
 def finish(self):
  if self.n!=self.row['bytes'] or self.h.hexdigest()!=self.row['sha256'] or self.f.read(1):raise ValueError('source mismatch '+self.row['path'])
def main():
 a=argparse.ArgumentParser();a.add_argument('--inventory',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--action',choices=['compress','roundtrip'],required=True);x=a.parse_args();raw=x.inventory.read_bytes();c=json.loads(raw);rows=c['members'];expected={r['member']:r for r in rows}
 if len(expected)!=len(rows):raise ValueError('duplicate member')
 if x.action=='compress':
  out=Writer(x.output)
  with tarfile.open(fileobj=out,mode='w|',format=tarfile.PAX_FORMAT) as tar:
   ti=tarfile.TarInfo('__inventory__.json');ti.size=len(raw);ti.mode=0o644;ti.mtime=0;tar.addfile(ti,io.BytesIO(raw))
   for r in rows:
    ti=tarfile.TarInfo(r['member']);ti.mode=r['mode'];ti.mtime=0
    if r['kind']=='directory':
     ti.type=tarfile.DIRTYPE;tar.addfile(ti)
    elif r['kind']=='symlink':
     if os.readlink(r['path'])!=r['target']:raise ValueError('link changed')
     ti.type=tarfile.SYMTYPE;ti.linkname=r['target'];tar.addfile(ti)
    else:
     ti.size=r['bytes']
     with Path(r['path']).open('rb') as f:
      checked=Checked(f,r);tar.addfile(ti,checked);checked.finish()
  out.finish();print('PASS compressed all members',len(rows),flush=True)
 else:
  seen=set();total=0
  with lzma.open(x.output,'rb') as stream:
   with tarfile.open(fileobj=stream,mode='r|') as tar:
    for ti in tar:
     if ti.name=='__inventory__.json':
      if ti.name in seen or tar.extractfile(ti).read()!=raw:raise ValueError('embedded inventory')
     else:
      if ti.name not in expected or ti.name in seen:raise ValueError('unexpected/duplicate member')
      r=expected[ti.name]
      if ti.mode!=r['mode']:raise ValueError('mode mismatch')
      if r['kind']=='directory':
       if not ti.isdir():raise ValueError('directory type roundtrip')
      elif r['kind']=='symlink':
       if not ti.issym() or ti.linkname!=r['target']:raise ValueError('link roundtrip')
      else:
       if not ti.isfile() or ti.size!=r['bytes']:raise ValueError('member type/size')
       h=hashlib.sha256();n=0;f=tar.extractfile(ti)
       while True:
        b=f.read(1024*1024)
        if not b:break
        h.update(b);n+=len(b)
       if n!=r['bytes'] or h.hexdigest()!=r['sha256']:raise ValueError('member roundtrip '+ti.name)
       total+=n
     seen.add(ti.name)
   while True:
    pad=stream.read(1024*1024)
    if not pad:break
    if any(pad):raise ValueError('nonzero trailing tar data')
  if seen!=set(expected)|{'__inventory__.json'}:raise ValueError('missing roundtrip member')
  print(json.dumps(dict(state='PASS all-member roundtrip',members=len(rows),raw_bytes=total,archive_bytes=x.output.stat().st_size,archive_sha256=hashlib.sha256(x.output.read_bytes()).hexdigest())),flush=True)
if __name__=='__main__':main()
