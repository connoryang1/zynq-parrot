#!/usr/bin/env python3
"""Losslessly collect only an already CLOSED read-only optimized-DCP query; no tools."""
import gzip,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
Q=Path('/home/coyang/fpga-artifacts/context-resume/native1792-canonical-r7-preparation-20261121/read-optimized-hierarchy01')
def main():
 raw=(Q/'session.json').read_bytes();d=json.loads(raw);assert d['state'].startswith('PASS') and d['returncode']==0 and d['DCP_unchanged'] and d['input_DCP']==d['input_DCP_after'];assert len(d['outputs'])==22
 out=HERE/'optimized-query';out.mkdir(exist_ok=False);(out/'session.json').write_bytes(raw);records=[]
 for row in d['outputs']:
  p=Path(row['path']);b=p.read_bytes();assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'];assert p.suffix!='.dcp'
  z=gzip.compress(b,mtime=0);(out/(p.name+'.gz')).write_bytes(z);records.append(dict(file=p.name+'.gz',compressed_sha256=hashlib.sha256(z).hexdigest(),plain_bytes=len(b),plain_sha256=hashlib.sha256(b).hexdigest()))
 p=HERE/'bindings.json';e=json.loads(p.read_text());e['optimized_query']=dict(state='CLOSED PASS actual return0; read-only optimized-DCP stage, not placement or route',session_file='optimized-query/session.json',session_sha256=hashlib.sha256(raw).hexdigest(),outputs=records,cleanup_scope='ROOT85986 actualexit0 and globalvendorabsence checked, separately reported to curator; session return0 and unchanged input DCP bound',input_DCP_sha256=d['input_DCP']['sha256']);e['limits']='No DCP/raw model/third-party encrypted source copied; no new vendor query/tool/board. Original external closure unchanged. Only CLOSED optimized-query included after ROOT actualexit0 notification.';p.write_text(json.dumps(e,indent=2)+'\n');print(hashlib.sha256(raw).hexdigest())
if __name__=='__main__':main()
