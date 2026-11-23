#!/usr/bin/env python3
"""ROOT-only lossless closure of both canonical CSR behavioral attempts."""
import argparse,hashlib,importlib.util,json,os,resource,shutil,socket,stat,sys,tarfile,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
B=HERE.parent
ROOTS={'RUN01':Path('/run/user/1001/zp-csr-canonical-snapshot-component-20261123-01'),'RUN02':Path('/run/user/1001/zp-csr-canonical-snapshot-component-20261123-02'),'PREPARATION':B/'csr-canonical-snapshot-component-preparation-20261123','WORKER01':B/'csr-canonical-snapshot-worker-preparation-20261123','CONTINUATION02':B/'csr-canonical-snapshot-continuation02-20261123','CLOSURE_SOURCE':HERE}
OUT=Path('/home/coyang/fpga-artifacts/context-resume/csr-canonical-snapshot-behavioral-20261123/closed01')
CODEC=Path('/home/coyang/bp-csr-canonical-snapshot-20261123/bp_be/src/v/bp_be_csr_snapshot_store_canonical.sv')
HELPERS=Path('/home/coyang/fpga-artifacts/context-resume/csr-snapshot-mapped-functional-20261122/runtime-full05')
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
def bind(p):
 p=Path(p);h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())
def save(p,d):
 with p.open('x')as f:json.dump(d,f,separators=(',',':'));f.write('\n')
def usage(p):return sum(x.stat().st_size for x in p.rglob('*')if x.is_file())if p.exists()else 0
def module(name,row):
 need(bind(row['path'])==row,'helper byte binding');s=importlib.util.spec_from_file_location(name,row['path']);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def native(a,owned):
 for r in a['sessions']:need(bind(r['path'])==r,'actual original session changed')
 x,y=[json.loads(Path(r['path']).read_text())for r in a['sessions']]
 need(x['state']=='FAIL preserved; no retry'and x['error']=="RuntimeError('native returncode noncanonical')",'old failure retained')
 need(y['state'].startswith('PASS composite behavioral canonical real-two-bank13312 sweep')and y['source_endcheck']=='PASS'and y['old01_endcheck'].startswith('PASS complete read-only'),'actual composite proof/end checks')
 need(y['final_global_idle']['vendor_processes']==[],'composite final vendor absence')
 need(len(x['commands'])==len(y['commands'])==5,'exact5+5 command history')
 for d in (x,y):
  need(d['source_endcheck']=='PASS'and d['ownership_final']['linux_claim_state']=='RELEASED'and not d['ownership_final']['owned_group_remaining'],'both workers released and sources verified')
  need(not Path('/proc',str(d['ownership_final']['pid'])).exists(),'old worker PID absent; never signal')
  for c in d['commands']:
   o=c['owned'];need(o['returncode']==0 and o['failure']is None and not o['owned_group_remaining']and not owned.group_state(o['owned_pgid']),'native0/owned groups gone')
  need(bind(d['admission']['path'])==d['admission'],'actual admission retained')
 need(y['promotion']['MEPC']['encoded_bits']==y['promotion']['noncanonical']['encoded_bits']==741,'promoted741 width')
 p=y['commands'][0];need(p['analysis']['marker']=='CSR_PRIMARY_EQUIVALENCE_PASS checks=106668 cycles=53341 reads=13341 saves=13318 reloads=13325','actual positive marker')
 need('CSR_CANONICAL_REAL_PRODUCER_SWEEP_PASS banks=2 contexts=4 fields=26 inputbits=64 writes=13312'in Path(p['log']['path']).read_text(),'actual full producer sweep')
 need(y['commands'][-1]['analysis']['expected_assertion']=='CSR_CANONICAL_RECONSTRUCTION_MISMATCH','actual decoded mutation rejected')
 return x,y

def rows(a,guard):
 result=[];covered=[]
 def add(p,member):
  guard();st=p.lstat();r=dict(path=str(p),member=member,mode=stat.S_IMODE(st.st_mode),device=st.st_dev,inode=st.st_ino,mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns)
  if p.is_symlink():r.update(kind='symlink',target=os.readlink(p),bytes=st.st_size)
  elif p.is_dir():r.update(kind='directory',bytes=0)
  else:
   need(p.is_file()and st.st_size<=8*1024**2,'ordinary file/member8MiB cap');h=hashlib.sha256()
   with p.open('rb')as f:
    for b in iter(lambda:f.read(1024**2),b''):guard();h.update(b)
   r.update(kind='file',bytes=st.st_size,sha256=h.hexdigest())
  result.append(r)
 for name,root in ROOTS.items():
  need(root.is_dir()and not root.is_symlink(),'exact ordinary root '+name);covered.append(str(root))
  for p in [root,*sorted(root.rglob('*'))]:add(p,name+(''if p==root else '/'+str(p.relative_to(root))))
 # Preserve every actual input/header/package/helper, including codec, gold,
 # all17 RTL sources and glbl. No installed library trees are traversed.
 plan=json.loads((ROOTS['WORKER01']/'plan.json').read_text())
 paths={r['path']for r in plan['inputs']+plan['compile_sources']}
 paths.add(str(CODEC))
 for i,path in enumerate(sorted(paths)):
  if any(path==s or path.startswith(s+'/')for s in covered):continue
  add(Path(path),'INPUTS/%03d-%s'%(i,Path(path).name))
 need(len({r['member']for r in result})==len(result),'unique exact archive names')
 need(sum(r['bytes']for r in result)<=32*1024**2,'whole raw32MiB bound; no exclusions')
 return result

def independent(out,inventory,guard):
 expected={r['member']:r for r in inventory};seen=set()
 with tarfile.open(out/'all.tar.xz','r:xz')as tar:
  for m in tar:
   guard();need(m.name not in seen,'duplicate member');seen.add(m.name)
   if m.name=='__inventory__.json':need(tar.extractfile(m).read()==(out/'inventory.json').read_bytes(),'embedded exact inventory');continue
   need(m.name in expected,'unknown member');r=expected[m.name];need(m.mode==r['mode'],'independent mode')
   if r['kind']=='directory':need(m.isdir(),'directory')
   elif r['kind']=='symlink':need(m.issym()and m.linkname==r['target'],'symlink target')
   else:
    need(m.isfile()and m.size==r['bytes'],'file size/type');h=hashlib.sha256();f=tar.extractfile(m)
    for b in iter(lambda:f.read(1024**2),b''):guard();h.update(b)
    need(h.hexdigest()==r['sha256'],'independent every-byte member SHA')
 need(seen==set(expected)|{'__inventory__.json'},'exact full membership')
 return dict(state='PASS independent all-member readback',members=len(expected))
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--admission',type=Path,required=True);ap.add_argument('--admission-sha256',required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
 need(args.admission.resolve().parent==HERE,'ROOT authority inside sealed closure source root');authority=bind(args.admission);need(args.execute and authority['sha256']==args.admission_sha256,'explicit ROOT execute SHA')
 a=json.loads(args.admission.read_text());need(a['schema']=='csr-canonical-behavioral-lossless-closure-v1'and a['ROOT_approved']is True,'unadmitted draft cannot run')
 need(a['output']==str(OUT)and not OUT.exists(),'one fresh exact output')
 need(a['limits']==dict(whole_seconds=900,encode_seconds=600,decode_seconds=180,raw_bytes=33554432,archive_bytes=7340032,HOME_family_bytes=8388608,source_bytes=65536,AS_bytes=1073741824),'fixed prospective bounds')
 need(socket.gethostname()=='blackparrot1','actual host')
 for r in a['inputs']:need(bind(r['path'])==r,'exact closure source')
 need(a['resources']['ROOT_approved']is True and a['resources']['all_existing_future_caps_priced']is True,'ROOT fresh summed resources')
 owned=module('software_owned_v2',a['owned']);q=module('csr_close_qualified_worker',a['qualified']);need(q.owned is owned,'exact qualified owner API')
 need(a['owned']['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','qualified52c')
 need(a['qualified']['sha256']=='62cd736136ade5398bee673a53014262be16b362323d2cd812f50ec47e2460a3','qualified global inventory')
 q.empty_inventory();native(a,owned);started=time.monotonic();last=[0];lives=[]
 def guard():
  need(time.monotonic()-started<900,'whole900s');need(bind(args.admission)==authority,'authority stable')
  now=time.monotonic()
  if now-last[0]<0.25:return
  last[0]=now;home=sum(usage(ROOTS[n])for n in ('PREPARATION','WORKER01','CONTINUATION02','CLOSURE_SOURCE'))+CODEC.stat().st_size+usage(OUT)
  need(home<=8388608 and usage(HERE)<=65536,'whole original HOME8MiB union and new source64KiB')
  r=a['resources'];parent=OUT.parent
  while not parent.exists():parent=parent.parent
  need(shutil.disk_usage(parent).free>=1879048192+8388608-home+r['OTHER_HOME_bytes'],'HOME1792MiB+remaining8M+OTHER')
  need(shutil.disk_usage('/run/user/1001').free>=1073741824+r['OTHER_RUN_bytes'],'RUNfloor+ALL remaining including shared behavioral256M until explicit freeze')
  need(shutil.disk_usage('/dev/shm').free>=536870912+r['OTHER_SHM_bytes'],'SHMfloor+OTHER')
  need(q.empty_inventory()['vendor_processes']==[],'no vendor during closed-source capture')
 guard();OUT.mkdir(parents=True);state=dict(state='RUNNING lossless capture',admission=authority,no_cleanup=True,no_reservation_release=True)
 def limit():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1073741824,)*2);resource.setrlimit(resource.RLIMIT_FSIZE,(7340032,)*2)
 try:
  before=rows(a,guard);save(OUT/'inventory.json',dict(schema='full-live-member-inventory-v1',members=before));inventory=bind(OUT/'inventory.json')
  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
  for k in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH'):env.pop(k,None)
  for action,seconds in [('compress',600),('roundtrip',180)]:
   guard();argv=['/usr/bin/python3','-I','-B',str(HERE/'codec.py'),'--inventory',inventory['path'],'--output',str(OUT/'all.tar.xz'),'--action',action]
   try:
    with (OUT/(action+'.log')).open('xb')as log:life=owned.run(argv,OUT,env,log,seconds,guard,limit)
   except BaseException as e:
    lives.append(getattr(e,'owned_receipt',dict(failure=repr(e),owned_group_remaining=False)));raise
   lives.append(life);need(life['returncode']==0 and life['failure']is None and not life['owned_group_remaining'],'codec owned lifecycle')
  state['independent_readback']=independent(OUT,before,guard);need(rows(a,guard)==before,'all original bytes/modes/link/membership/identities stable');native(a,owned)
  for r in a['inputs']:need(bind(r['path'])==r,'end helper binding')
  guard();state.update(state='PASS complete lossless canonical behavioral history; ROOT may separately freeze unused futures',archive=bind(OUT/'all.tar.xz'),inventory=inventory,all_actual_originals_retained=True,global_vendor_at_end=q.empty_inventory(),eligible_for_ROOT_future_freeze=True)
 except BaseException as e:state.update(state='FAIL preserved; no retry/delete/release',error=repr(e));raise
 finally:
  state.update(owned=lives,elapsed_seconds=time.monotonic()-started);save(OUT/'complete.json',state)
 print(json.dumps(bind(OUT/'complete.json')),flush=True)
if __name__=='__main__':main()
