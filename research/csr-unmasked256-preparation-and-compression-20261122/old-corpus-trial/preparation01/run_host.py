#!/usr/bin/env python3
"""ROOT-only one archival feasibility attempt, no compiler/model/reader/vendor."""
from pathlib import Path
import argparse,hashlib,json,os,resource,shutil,signal,subprocess,sys
import software_owned_v2 as owned
HERE=Path(__file__).resolve().parent
STAGE=Path('/run/user/1001/zp-csr-old-corpus-xz-feasibility-20261122-01')
RUN_CAP=128*1024**2;HOME_CAP=1024**2;DICT_RSS=1024**3
RECEIPT=HERE/'host-result.json'
def need(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def used(p):return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.exists() else 0
def vendor_busy():
 names={'vivado','vivado_lab','xelab','xsim','xsimk','xvlog','xsc','planahead'};launch={'run_vivado_2024_2.sh','launch_synthesis.sh'};rows=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   comm=(p/'comm').read_text().strip();args=[s.decode(errors='replace') for s in (p/'cmdline').read_bytes().split(b'\0') if s]
   if comm in names or any(x.rsplit('/',1)[-1] in names|launch for x in args):rows.append(dict(pid=int(p.name),comm=comm))
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 return rows
def main():
 p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,default=HERE/'admission.DRAFT.json');p.add_argument('--admission-sha256');p.add_argument('--execute',action='store_true');p.add_argument('--preflight',action='store_true');x=p.parse_args();need(x.execute!=x.preflight,'one action');a=json.loads(x.admission.read_text());ab=bind(x.admission)
 if x.admission_sha256:need(ab['sha256']==x.admission_sha256,'reviewed exact admission')
 need(a['stage']==str(STAGE) and a['limits']==dict(RUN=RUN_CAP,HOME=HOME_CAP,archive=32*1024**2,dict_bytes=64*1024**2,child_AS=DICT_RSS,compression_seconds=600,roundtrip_seconds=180,total_seconds=780),'fixed allocations/codec/deadline')
 for r in a['inputs']:need(bind(r['path'])==r,'source/archive input drift '+r['path'])
 c=json.loads((HERE/'input-list.json').read_text())
 for r in c['providers'].values():need(bind(r['binding']['path'])==r['binding'],'original provider drift')
 for r in c['members']:
  if 'id' not in r['provider']:need(bind(r['provider']['binding']['path'])==r['provider']['binding'],'original live/mirrored payload drift')
 closure=json.loads(Path(a['obsolete_profile_closure']['path']).read_text());need(closure['future_native_POOL_bytes']==0 and closure['future_native_HOME_bytes']==0 and closure['no_cleanup'] is True,'old obsolete future reservations not formally closed')
 if not a.get('ROOT_approved'):
  need(x.preflight,'ROOT actual resource admission required');print('SOURCE PASS; ROOT resources/execute NOT admitted');return
 rp=a['ROOT_resource_profile'];need(bind(rp['path'])==rp,'ROOT profile binding');profile=json.loads(Path(rp['path']).read_text())
 need(profile.get('all_other_charged_reserves_included') is True and len(profile.get('basis_records',[]))>0,'explicit global resource basis')
 for r in profile['basis_records']:need(bind(r['path'])==r,'global basis drift')
 for k in ['other_HOME_bytes','other_RUN_bytes','other_SHM_bytes']:need(type(profile[k]) is int and profile[k]>=0,'explicit separately priced volumes')
 def guard():
  need(bind(x.admission)==ab and bind(rp['path'])==rp,'admission/resource profile drift')
  n=used(STAGE);h=used(HERE);need(n<=RUN_CAP and h<=HOME_CAP,'new family cap')
  need(shutil.disk_usage('/run/user/1001').free>=1024**3+RUN_CAP-n+profile['other_RUN_bytes'],'RUN floor+remaining+OTHER')
  need(shutil.disk_usage(HERE).free>=2684354560+HOME_CAP-h+profile['other_HOME_bytes'],'HOME floor+remaining+OTHER')
  need(shutil.disk_usage('/dev/shm').free>=512*1024**2+profile['other_SHM_bytes'],'SHM floor+OTHER')
  mem={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')}
  need(mem['MemAvailable']>=1024**3+DICT_RSS+RUN_CAP-n+profile['other_RUN_bytes']+profile['other_SHM_bytes'],'physical available memory includes encoderAScap and all RAM reservations')
  need(not vendor_busy(),'vendor/launcher appeared; no heavy archival overlap')
  return dict(RUN_bytes=n,HOME_bytes=h)
 proof=guard()
 if x.preflight:print(json.dumps(dict(state='PASS ROOT-profile source/resource preflight only',admission=ab,resources=proof),indent=2));return
 need(x.admission_sha256==ab['sha256'] and not STAGE.exists() and not RECEIPT.exists(),'one ROOT-reviewed fresh attempt')
 sentinel=Path('/run/user/1001/zp-retained-borrow256-trace0-fullcore-20261122-01/full01/session.json');need(sentinel.is_file(),'ROOT host namespace required')
 STAGE.mkdir();state=dict(state='RUNNING old corpus only',admission=ab,preflight=proof,originals_unchanged=True)
 def save():
  tmp=RECEIPT.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(RECEIPT)
 save()
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(DICT_RSS,DICT_RSS));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
 try:
  with (STAGE/'codec.log').open('wb') as log:state['owned']=owned.run([sys.executable,HERE/'codec.py','--inputs',HERE/'input-list.json','--stage',STAGE],STAGE,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,780,guard,limits)
  need(state['owned']['returncode']==0,'fixed old-corpus codec/roundtrip failed')
  result=json.loads((STAGE/'codec-result.json').read_text());need(result['state'].startswith('PASS old corpus fits') and result['roundtripped_members']==c['count'],'complete all-member roundtrip')
  for r in a['inputs']:need(bind(r['path'])==r,'source/end drift')
  need(bind(x.admission)==ab,'admission end drift');state.update(state='PASS old corpus only; no futurefullproof/compressedgzip identity claim',result=result,resources=guard(),result_binding=bind(STAGE/'codec-result.json'))
 except BaseException as e:state.setdefault('owned',getattr(e,'owned_receipt',None));state.update(state='FAIL preserved; no retry/codec/cap extension',error=repr(e));raise
 finally:save();print(state['state'])
if __name__=='__main__':main()
