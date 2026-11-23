#!/usr/bin/env python3
"""ROOT-owned packaging leaf; no Make dependencies, board action or approval."""
import argparse,base64,hashlib,io,json,os,re,subprocess,tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

def need(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def main():
 p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--execute',action='store_true');x=p.parse_args()
 need(x.execute and bind(x.admission)['sha256']==x.admission_sha256,'exact fresh ROOT package admission')
 a=json.loads(x.admission.read_text());need(a['schema']=='csr256-routed-bitgen-package-v1' and a['ROOT_approved']is True,'DRAFT cannot package')
 need(a['ROOT_bitgen_route_DRC_source_review_PASS']is True and a['physical_approval']is None,'package review only; no hardware approval')
 for row in a['source_inputs']+a['bitgen_review_inputs']:need(bind(row['path'])==row,'source/review drift')
 rows=a['bundle_inputs'];names=['black_parrot_bd_1.'+s for s in ('bit','map','hwh')]
 need([Path(r['path']).name for r in rows]==names,'exact three-member ordering/stem')
 for row in rows:need(bind(row['path'])==row and row['bytes']>0,'bitgen bundle drift')
 need(rows[2]['bytes']==107340 and rows[2]['sha256']=='05a71dfc14db5d7efdb21cd1a5c9a9ec67c79133f48ff860bd783209049cb16b','archived exact parent HWH')
 ranges=[(r.get('MASTERBUSINTERFACE'),r.get('BASEVALUE'),r.get('HIGHVALUE'))for r in ET.parse(rows[2]['path']).iter('MEMRANGE')if r.get('INSTANCE')=='top_0' and r.get('MASTERBUSINTERFACE')in ('GP0_AXI','GP1_AXI')]
 need(sorted(ranges)==[('GP0_AXI','0x40000000','0x40000FFF'),('GP1_AXI','0x80000000','0xBFFFFFFF')],'exact top0 host ranges')
 definitions=re.findall(r'(?:^|\s)-D([A-Za-z0-9_]+)=([^\s]+)',Path(rows[1]['path']).read_text())
 for name,value in [('GP0_ADDR_BASE',0x40000000),('GP1_ADDR_BASE',0x80000000)]:
  found=[v for n,v in definitions if n==name];need(len(found)==1 and int(found[0],0)==value,'exact unique host MAP base '+name)
 out=Path(a['package']);need(out.name=='black_parrot_bd_1.zynq.pynqz2.tar.xz.b64' and not out.exists(),'fresh package namespace')
 need(sum(r['bytes'] for r in rows)<=16*1024**2,'prospective16MiB raw bundle cap')
 # Existing Makefile.collateral format: tar -Jc BIT MAP HWH | base64.
 container=io.BytesIO()
 with tarfile.open(fileobj=container,mode='w:xz')as tar:
  for row,name in zip(rows,names):tar.add(row['path'],arcname=name,recursive=False)
 encoded=base64.encodebytes(container.getvalue());need(len(encoded)<=16*1024**2,'prospective16MiB package cap')
 with out.open('xb')as f:f.write(encoded)
 expected=dict(zip(names,rows));seen=set()
 with tarfile.open(fileobj=io.BytesIO(base64.b64decode(out.read_bytes())),mode='r:xz')as tar:
  for member in tar:
   need(member.name in expected and member.name not in seen and member.isfile(),'exact regular member set')
   seen.add(member.name);r=expected[member.name];data=tar.extractfile(member).read()
   need(member.size==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'],'all three package payloads equal')
 need(seen==set(names),'complete bundle')
 checker=a['verify_package_script'];need(bind(checker['path'])==checker,'maintained checker pin')
 tmp=Path(a['TMPDIR']);need(tmp.is_dir() and str(tmp).startswith('/run/user/1001/'),'owned charged RUN extraction scratch')
 env=dict(os.environ,TMPDIR=str(tmp));cp=subprocess.run([checker['path'],str(out),rows[0]['sha256']],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,check=False)
 (out.parent/'package-check.log').write_bytes(cp.stdout);need(cp.returncode==0 and b'PACKAGE_OK=1\n' in cp.stdout,'maintained package check0')
 for row in rows+a['source_inputs']+a['bitgen_review_inputs']+[checker]:need(bind(row['path'])==row,'input/source drift after packaging')
 result=dict(state='PASS exact three-member candidate package; no physical/clean-build acceptance',admission=bind(x.admission),package=bind(out),bundle=rows,checker=checker,physical_approval=None)
 (out.parent/'package.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
