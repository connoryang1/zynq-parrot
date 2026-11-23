from pathlib import Path
import sys,json,time,hashlib,importlib.util
sys.dont_write_bytecode=True
H=Path('/home/coyang/zynq-parrot-retained-metadata/research/csr1280-allslots-native-preparation03-20261123')
O=Path(__file__).parent
assert hashlib.sha256((H/'handoff.json').read_bytes()).hexdigest()=='d45c91c41804ad45c665ee7e86f1b9c58cde18f9d13751c009b79c8389340494'
sys.path.insert(0,str(H))
import process_monitor as pm
import fixed_shared as fixed
rows=[]
def test(name,check,body,error=None):
 p=O/(name+'.json');assert not p.exists();caught=None;start=time.monotonic()
 try:
  with pm.phase(check,p)as guard:body(guard)
 except BaseException as e:caught=e
 if error is None:assert caught is None,repr(caught)
 else:assert isinstance(caught,ValueError) and error in str(caught),repr(caught)
 d=json.loads(p.read_bytes());assert not d['owned_group_remaining']
 assert all(not s['members']for s in d['group_states']if s['phase']=='after_cleanup')
 rows.append(dict(name=name,expected_error=error,actual_error=repr(caught)if caught else None,elapsed_seconds=time.monotonic()-start,receipt_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),max_scan_seconds=d.get('max_scan_seconds'),max_callback_age_s=d.get('max_callback_age_s'),owned_group_remaining=False))
def slow_valid():time.sleep(.7);return dict(mutable_output_bytes=1)
def exercise(g):time.sleep(2.1);g()
test('scheduled-700ms-scan-accepted',slow_valid,exercise)
calls=[0]
def cap_error():
 calls[0]+=1
 if calls[0]>=2:raise ValueError('controlled artifact cap violation')
 return dict(mutable_output_bytes=1)
test('artifact-cap-still-rejected',cap_error,lambda g:(time.sleep(1.4),g()),'controlled artifact cap violation')
calls=[0]
def stale():
 calls[0]+=1
 if calls[0]>=2:time.sleep(6)
 return dict(mutable_output_bytes=1)
def until_stale(g):
 for _ in range(70):time.sleep(.1);g()
test('stale-monitor-still-rejected',stale,until_stale,'snapshot stale over5s')
p=json.loads((H/'ROOT-resource-profile.DRAFT.json').read_bytes())
a=json.loads(Path(fixed.CAD_ADMISSION['path']).read_bytes());r=a['resources']
p['OTHER']=dict(RUN_bytes=r['other_work_future_bytes'],HOME_bytes=r['other_home_future_bytes'],SHM_bytes=r['other_shm_future_bytes'])
def actual_check():
 entries,info=fixed.cad_remaining(p)
 return dict(mutable_output_bytes=0,active_CAD=info)
def real_body(g):
 for _ in range(3):time.sleep(1.1);g()
test('actual-CAD-allocation-scan',actual_check,real_body)
result=dict(state='PASS host-accounting03 scheduling/cap/staleness/real-scan tests only',source_handoff_sha256=hashlib.sha256((H/'handoff.json').read_bytes()).hexdigest(),model_executed=False,FST_read=False,board_actions=False,tests=rows)
(O/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
