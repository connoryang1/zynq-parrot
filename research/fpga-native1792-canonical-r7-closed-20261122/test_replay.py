#!/usr/bin/env python3
"""Lightweight relocation and corruption refusals of the actual compact verifier; no tools."""
import importlib.util,json,shutil,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r7_closed_verify',HERE/'verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def main():
 baseline=v.verify(HERE);cases=[]
 with tempfile.TemporaryDirectory(prefix='r7-compact-replay-') as t:
  root=Path(t)/'relocated';shutil.copytree(HERE,root);assert v.verify(root)==baseline;cases.append('relocated byte-identical factual replay without original producer paths')
  def reject(relative,change,label):
   p=root/relative;b=p.read_bytes();change(p,b)
   try:v.verify(root)
   except (ValueError,OSError):cases.append(label)
   else:raise AssertionError('accepted '+label)
   p.write_bytes(b)
  reject('r7/019-bp_retained_line_store.sv.gz',lambda p,b:p.write_bytes(b[:4]+bytes([b[4]^1])+b[5:]),'compressed own-source mutation refused even if gzip payload unchanged')
  reject('source/bp_common_aviary_cfg_pkgdef.svh',lambda p,b:p.write_bytes(b+b'\n'),'ordinary-geometry source mutation refused')
  reject('optimized-query/retained-RAM-ports.tsv.gz',lambda p,b:p.unlink(),'missing actual mapped-primitive inventory refused')
  assert v.verify(root)==baseline
 print(json.dumps(dict(state='PASS lightweight actual-verifier replay/refusal',cases=cases),indent=2))
if __name__=='__main__':main()
