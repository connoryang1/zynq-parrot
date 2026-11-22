#!/usr/bin/env python3
"""Copy only already-closed source/log/list bytes; never invoke a child tool."""
import hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parent

def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def require(ok,msg):
 if not ok:raise ValueError(msg)
def size(p):return sum(x.stat().st_size for x in p.rglob('*') if x.is_file())
def main():
 a=R/'admission.json';c=R/'completion.json'
 require(bind(a)['sha256']=='51ffbff468033ffc6992d3cd1f55278a1f6270480386f83d1bb91d1e9f7fe05b','RO admission')
 require(bind(c)['sha256']=='6ce0a22b592077a96957bc9c058371f6f6594d0d28e73322e2b12adb04f819c7','RO completion')
 doc=json.loads(a.read_text());completion=json.loads(c.read_text());require(completion['derived_component_correctness'] is True and completion['original_operational_budget_compliance'] is False,'separate derived correctness only')
 out=R/'compact-inputs';require(not out.exists(),'fresh source/log preservation only')
 chosen=[]
 for rec in doc['inputs']['immutable_stage_inventory']:
  p=Path(rec['path'])
  if '/source/' in str(p) or p.suffix=='.log' or p.name.endswith('-hierarchy.tsv'):
   require(bind(p)==rec,'immutable compact input '+str(p));chosen.append(rec)
 require(sum(x['bytes'] for x in chosen)==494671 and len(chosen)==46,'fixed compact selection')
 require(size(R)+sum(x['bytes'] for x in chosen)+65536<=2*1024**2,'RO2MiB total output cap')
 require(shutil.disk_usage(R).free>=3*1024**3+sum(x['bytes'] for x in chosen),'HOME reserve')
 out.mkdir();copies=[]
 for rec in chosen:
  p=Path(rec['path']);stage=next(Path(s) for s in doc['inputs']['stage_bytes'] if p.is_relative_to(Path(s))) if hasattr(p,'is_relative_to') else next(Path(s) for s in doc['inputs']['stage_bytes'] if str(p).startswith(s+'/'))
  q=out/stage.name/str(p.relative_to(stage));q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());require(bind(q)['sha256']==rec['sha256'],'copy mismatch');copies.append(dict(original=rec,snapshot=bind(q)))
 require(size(R)<=2*1024**2,'final RO2MiB cap')
 m=dict(state='PASS compact immutable source/log/list preservation only; no child tool',admission=bind(a),completion=bind(c),files=copies,raw_FST_and_models='Retained unmodified in RAM; NOT copied or executed',original_operational_budget_compliance=False)
 p=out/'manifest.json';p.write_text(json.dumps(m,indent=2)+'\n');require(size(R)<=2*1024**2,'final manifest cap');print(p,bind(p))
if __name__=='__main__':main()
