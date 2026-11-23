"""Restore one exact retired derived cache; caller must price current free space."""
from pathlib import Path
import argparse,json,hashlib,os,shutil
O=Path(__file__).parent
p=argparse.ArgumentParser();p.add_argument('--restore',type=int,choices=range(3),required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--required-free-bytes',type=int,required=True);a=p.parse_args()
raw=(O/'manifest.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==a.manifest_sha256
m=json.loads(raw);r=m['entries'][a.restore];t=r['target'];base=Path(r['base']['path']);dest=Path(t['path']);assert not dest.exists()and not dest.is_symlink()
assert a.required_free_bytes>=1879048192+t['bytes']and shutil.disk_usage(O).free>=a.required_free_bytes
assert hashlib.sha256(base.read_bytes()).hexdigest()==r['base']['sha256']
tmp=dest.with_name(dest.name+'.delta-restore-07');fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
try:
 h=hashlib.sha256();n=0;edits=dict(r['patches'])
 with base.open('rb')as f:
  while True:
   b=f.read(1048576)
   if not b:break
   b=bytearray(b)
   for off,value in edits.items():
    if n<=off<n+len(b):b[off-n]=value
   h.update(b);view=memoryview(b)
   while view:
    wrote=os.write(fd,view);view=view[wrote:]
   n+=len(b)
 assert n==t['bytes']and h.hexdigest()==t['sha256']
 os.fchmod(fd,t['mode']);os.fsync(fd);os.close(fd);fd=-1
 os.utime(tmp,ns=(t['mtime_ns'],t['mtime_ns']));os.link(tmp,dest);tmp.unlink()
 d=os.open(dest.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(d)
 finally:os.close(d)
 print('PASS exact bytes/SHA/mode/mtime restored; inode/ctime necessarily new',dest)
finally:
 if fd>=0:os.close(fd)
