#!/usr/bin/env python3
"""Derive only four portable pybind names from the preserved original bundle."""
from pathlib import Path
import gzip,io,tarfile,json,hashlib,difflib

def main():
 old=Path('/home/coyang/fpga-artifacts/context-resume/retained-observer-host-build-20261121');out=Path(str(old)+'-v2');out.mkdir(exist_ok=False)
 blob=(old/'source.tar.gz').read_bytes()
 if hashlib.sha256(blob).hexdigest()!='6c53393a78123253c8647841a6bb1a0d67bd312841f75ba7d4364f1020809855':raise ValueError('original source bundle drift')
 with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as t:files={m.name:t.extractfile(m).read() for m in t.getmembers()}
 key='include/bsg_zynq_pl.h';original=files[key].decode();assert original.count('py::module_')==4
 new=original.replace('py::module_','py::module');files[key]=new.encode();m=json.loads(files['manifest.json']);m['sources'][key]['derived_from_original_sha256']=m['sources'][key]['sha256'];m['sources'][key].update(bytes=len(files[key]),sha256=hashlib.sha256(files[key]).hexdigest(),derivation='Exactly4 py::module_→py::module legacy-compatible name replacements; no allocation/ownership/overlay behavior changes')
 m['compatibility_scope']='Installed native pybind11 predates module_ name; its compiler explicitly suggests module. Original compile failure preserved. Portable module alias also exists in newerpybind11. Runtime API availability and owned46MiB allocator still require actual diagnostic target qualification.'
 files['manifest.json']=(json.dumps(m,indent=2)+'\n').encode();b=io.BytesIO()
 with tarfile.open(fileobj=b,mode='w') as t:
  for n,v in files.items():
   z=tarfile.TarInfo(n);z.size=len(v);z.mode=0o644;z.mtime=0;t.addfile(z,io.BytesIO(v))
 blob=gzip.compress(b.getvalue(),mtime=0);(out/'source.tar.gz').write_bytes(blob);(out/'manifest.json').write_bytes(files['manifest.json']);(out/'compatibility.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),new.splitlines(True),fromfile='original/bsg_zynq_pl.h',tofile='native-compatible/bsg_zynq_pl.h')));(out/'preparation.json').write_text(json.dumps({'state':'PASS portable name preparation only; no compile/runtime claim','archive':{'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()},'unpacked_file_bytes':sum(map(len,files.values())),'files':len(files)},indent=2)+'\n')
 print(out/'preparation.json')
if __name__=='__main__':main()
