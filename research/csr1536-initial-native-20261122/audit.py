"""Complete two unchanged audits using a corrected, separately bound receipt."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,os,resource,sys,time
sys.dont_write_bytecode=True
HELPER=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-composite-continuation-preparation-20261122/preparation01')
sys.path.insert(0,str(HELPER))
spec=importlib.util.spec_from_file_location('preserved_composite_helper',HELPER/'continue_full.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
BASE=c.BASE;OLD=BASE/'full01';RUN=BASE/'full02';OUT=BASE/'full03'
COUNTER=Path('/home/coyang/zynq-parrot-retained-dense/research/retained-use-observation-20261121/verify_counters.py')
ASHA='50144661b7aef0b8e16a43b4a630595cbd110cb0462db3ac01e7c8c0f2df15e4'
a=c.authority(c.FINAL,ASHA,'execute');c.budget(a)
assert c.bind(HELPER/'continue_full.py')['sha256']=='0f6cbc6b31960caa8bb2b8cc3f8742698b33d7c8ba4fd64b71157c27f815cc35'
old,selection=c.inherited();failed=json.loads((RUN/'session.json').read_text())
assert failed['state']=='FAIL preserve composite continuation; no retry or budget raise'
assert failed['source_endcheck']=='PASS' and failed['error']=="ValueError('complete checker phase0')"
assert [r['label']for r in failed['commands']]==['integrity-run','integrity-checker','advisory-run','advisory-checker','strict','counter']
assert all(not r['ownership']['owned_group_remaining']for r in failed['commands'])
assert all(r['returncode']==0 for r in failed['commands'][1:5:2]) and failed['commands'][4]['returncode']==0
assert failed['commands'][5]['returncode']==1 and 'closed run artifact changed' in (RUN/'counter.log').read_text()
strict=json.loads((RUN/'strict01/verification.json').read_text());assert strict['accepted'] is True
assert strict['bindings']['fst']==c.bind(RUN/'advisory/trace.fst')
assert not OUT.exists();OUT.mkdir();(OUT/'tmp').mkdir()
prepared=json.loads((RUN/'prepared.json').read_text())
for r in prepared['inputs']:c.verify(r)
protected=json.loads(gzip.decompress(Path(prepared['protected_inventory']['path']).read_bytes()))
assert all(c.inventory(Path(root))==rows for root,rows in protected.items())
protected[str(RUN)]=c.inventory(RUN)
(OUT/'protected-inputs.json.gz').write_bytes(gzip.compress(json.dumps(protected,sort_keys=True).encode(),mtime=0))
proof=json.loads((RUN/'advisory/verification.json').read_text())
corrected=[]
for row in proof['files']:
 c.verify(row);p=Path(row['path']).resolve();s=p.stat()
 corrected.append(dict(c.bind(p),inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns))
proof['files']=corrected
sidecar=OUT/'closed-run-full-bindings.json';c.write(sidecar,proof)
record=dict(state='RUNNING corrected receipt counter/geometry tail only',schema='csr1536-complete-native-composite-v1',
 model=failed['model'],model_stamp=failed['model_stamp'],actual_source_list=failed['actual_source_list'],
 source_tree_baseline=failed['source_tree_baseline'],source_bp=failed['source_bp'],geometry=failed['geometry'],
 inherited_build_session=c.bind(OLD/'session.json'),inherited_runtime_strict_session=c.bind(RUN/'session.json'),
 original_run_receipt=c.bind(RUN/'advisory/verification.json'),corrected_run_receipt=c.bind(sidecar),commands=[],
 scope='Same closed trace and exact unmodified auditors; only missing receipt identity fields supplied. No new native, model, source, policy or gate relaxation.')
start=time.monotonic();env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(OUT/'tmp'))
def guard():
 assert time.monotonic()-start<960
 c.budget(a);assert c.size(OUT)<64*1024**2
 assert c.size(Path(__file__).parent)<16384
 assert c.bind(c.FINAL)['sha256']==ASHA
def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2)
def run(label,argv,seconds):
 row=dict(label=label,argv=list(map(str,argv)),timeout_s=seconds);record['commands'].append(row);c.write(OUT/'session.json',record)
 try:
  with (OUT/(label+'.log')).open('xb')as log:row['ownership']=c.owned.run(row['argv'],OUT,env,log,seconds,guard,limits)
 except BaseException as e:row['ownership']=getattr(e,'owned_receipt',None);raise
 finally:c.write(OUT/'session.json',record)
 assert row['ownership']['returncode']==0 and row['ownership']['failure'] is None and not row['ownership']['owned_group_remaining']
try:
 run('counter',['/usr/bin/python3','-B',COUNTER,'--fst',RUN/'advisory/trace.fst','--reader',c.READER,'--strict-proof',RUN/'strict01/verification.json','--run-proof',sidecar,'--out',OUT/'counter01'],240)
 run('parameters',['/usr/bin/python3','-B',c.PRIOR/'geometry.py','--fst',RUN/'advisory/trace.fst','--reader',c.READER,'--lines','1536','--out',OUT/'parameters01'],660)
 counts=json.loads((OUT/'counter01/verification.json').read_text());assert counts['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8])
 values=json.loads((OUT/'parameters01/verification.json').read_text())['facts']['values']
 assert len(values)==17 and values['retained_store.storage.i_lines_p']==values['retained_store.storage.d_lines_p']==1536
 record.update(state='PASS COMPOSITE CSR1536 cleanbuild/loader plus complete integrity/cold08 strict512b-eight-real-writes-Iretire-counter-17geometry-source-audits',
  closed_audits={k:c.bind(p)for k,p in [('strict',RUN/'strict01/verification.json'),('counter',OUT/'counter01/verification.json'),('parameters',OUT/'parameters01/verification.json')]},
  inherited_build_loader_commands=old['commands'][:4],inherited_runtime_strict_commands=failed['commands'][:5],total_qualified_phases=11,
  old_partial_integrity_explicitly_excluded=True,old_failed_counter_receipt_explicitly_excluded=True,
  all_1536_capacity_coverage=False,scoped_clone_and_STD_pending=True,no_board_operations=True)
except BaseException as e:record.update(state='FAIL preserved counter/geometry tail; no accepted composite',error=repr(e));raise
finally:
 try:
  guard();c.inherited()
  for r in prepared['inputs']:c.verify(r)
  assert all(c.inventory(Path(root))==rows for root,rows in protected.items())
  record['source_endcheck']='PASS'
 except BaseException as e:record.update(state='FAIL tail protected source/end-resource check',end_error=repr(e))
 record['elapsed_seconds']=time.monotonic()-start;c.write(OUT/'session.json',record)
assert record['state'].startswith('PASS COMPOSITE CSR1536')
print(json.dumps(c.bind(OUT/'session.json')))
