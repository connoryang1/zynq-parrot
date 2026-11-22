#!/usr/bin/env python3
"""ROOT-only base full+clone+STD archival preparation/closure. No reader/target."""
import argparse,gzip,hashlib,json,os,resource,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PREP=HERE.parent/'preparation02'
sys.path.insert(0,str(PREP))
import budget,software_owned_v2 as owned
BASE=budget.BASE;WORK=BASE/'closure-records01';OUT=budget.DURABLE/'base-full-clone-std-closed01'
DOMAINS=['core252','observer_and_geometry','SP_strict162','capacity167','actual_geometry17']
CLONE=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-observation-preparation-20261122')
STD=Path('/home/coyang/zynq-parrot-linux-host-observer/research/csr-unmasked256-regression-preparation-20261122')
EXPECTED_MODEL='9c69a2f83539ca7a3f2c74c3be0502dbbf929d09ea95f1d75bfd2bd7172fc1fd'
require=budget.require

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def binding(p):
 p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def state(p,wanted):
 q=json.loads(Path(p).read_text());require(q['state']==wanted,'terminal required '+str(p));return q

def gates(a):
 for rel,wanted in a['terminal_SHA256'].items():require(sha(BASE/rel)==wanted,'exact ROOT terminal receipt '+rel)
 full=state(BASE/'full01/session.json','PASS CSR unmasked256 trace0 clean fullcore integrity/cold08 strict512b-eight-real-writes-Iretire-counter-geometry-source-audits')
 require(full['model']['sha256']==EXPECTED_MODEL,'new fullmodel only')
 flow=state(BASE/'scoped-csr01/flow.json','PASS-one-new-CSR-unmasked256-observation-qualification')
 qual=state(BASE/'scoped-csr01/qualification01/qualification.json','PASS-matched256-cold08-five-domain-literal-equivalence-strict-counter-geometry')
 require(set(qual['domains'])==set(DOMAINS) and all(q['literal_bytes_equal'] is True for q in qual['domains'].values()),'all five literal domains')
 std=state(BASE/'scoped-csr01/architectural-regressions01/session.json','PASS four unchanged architectural tests on new CSR-unmasked qualified model; no performance claim')
 tests=['mt_context_csr_rebind_test','mt_umode_nonresident_sv39_data_handoff_test','mt_resident_reseed_irq_test','mt_protected_rpc_hardware_test']
 require([r['test'] for r in std['tests']]==tests,'all four unchanged STD cases in fixed order')
 for r in std['tests']:
  for k in ['elf','nbf','trace','log']:
   require(binding(r[k]['path'])==r[k],'actual STD artifact drift')
 for name,wanted in [('prepare-supervision.json','PASS separate prepare'),('qualify-supervision.json','PASS separate qualify'),('architectural-regressions-supervision.json','PASS four-test phase, no hardware/app performance claim')]:
  receipt=state(BASE/'scoped-csr01'/name,wanted);life=receipt['ownership'];require(life['returncode']==0 and life['failure'] is None and not life['owned_group_remaining'],'actual owned clone/STD phase completed')
 models=[BASE/'full01/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench',BASE/'scoped-csr01/build/obj/Vbsg_nonsynth_zynq_testbench']
 require(sha(models[0])==EXPECTED_MODEL and sha(models[1])==a['scoped_model_sha256'] and len(a['scoped_model_sha256'])==64,'exact new full/scoped executables')
 return dict(full=binding(BASE/'full01/session.json'),clone=binding(BASE/'scoped-csr01/flow.json'),qualification=binding(BASE/'scoped-csr01/qualification01/qualification.json'),STD=binding(BASE/'scoped-csr01/architectural-regressions01/session.json'),models=[binding(p) for p in models])

def tuple_stat(p):
 s=p.lstat();return [s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino,stat.S_IMODE(s.st_mode)]
def row(p,member):
 p=Path(p);s=p.lstat();r=dict(path=str(p),member=member,mode=stat.S_IMODE(s.st_mode),stat=tuple_stat(p))
 if p.is_symlink():
  raw=os.readlink(p).encode();r.update(kind='symlink',target=os.readlink(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 else:require(p.is_file(),'no special input '+str(p));r.update(kind='file',bytes=s.st_size,sha256=sha(p))
 return r

def paths(root):
 return sorted(str(p) for p in root.rglob('*') if (p.is_file() or p.is_symlink()) and not (p==WORK or WORK in p.parents))

def collect(a):
 started=time.monotonic();last_guard=started;gate=gates(a);members=[];excluded=[];parsed=[]
 canonical=set('scoped-csr01/records/original-'+d+'/canonical.tsv.gz' for d in DOMAINS)|set('scoped-csr01/qualification01/clone-'+d+'/canonical.tsv.gz' for d in DOMAINS)
 cache_roots=['full01/verilator/obj_dir/','scoped-csr01/build/obj/']
 for p in sorted(BASE.rglob('*')):
  if p==WORK or WORK in p.parents:continue
  if p.is_dir() and not p.is_symlink():continue
  if time.monotonic()-last_guard>0.25:budget.check();last_guard=time.monotonic()
  require(time.monotonic()-started<120,'fixed120s preparation inventory')
  rel=p.relative_to(BASE).as_posix();r=row(p,'RUN/'+rel)
  if rel in canonical:
   q=json.loads((BASE/'scoped-csr01/qualification01/qualification.json').read_text());which='reference' if '/original-' in rel else 'clone';name=rel.split('/original-',1)[1].split('/',1)[0] if which=='reference' else rel.split('/clone-',1)[1].split('/',1)[0];expected=q['domains'][name][which];rawhash=hashlib.sha256();rawbytes=0
   require(binding(p)==expected['canonical_file'],'canonical container binding')
   with gzip.open(p,'rb') as z:
    for b in iter(lambda:z.read(1024*1024),b''):rawhash.update(b);rawbytes+=len(b)
   require(rawhash.hexdigest()==expected['sha256'],'actual canonical raw-data hash')
   r.update(reason='derived canonical gzip; complete uncompressed hashes/order/recipe and raw FST retained',raw_sha256=rawhash.hexdigest(),raw_bytes=rawbytes);excluded.append(r)
  elif p.suffix in ['.o','.a','.gch'] and any(rel.startswith(q) for q in cache_roots):r['reason']='rebuildable compiled host cache only; complete byte inventory retained';excluded.append(r)
  else:
   require(not rel.endswith('canonical.tsv.gz'),'unknown canonical stream cannot be silently dropped');members.append(r)
   if p.suffix=='.json':
    try:parsed.append(json.loads(p.read_text()))
    except (ValueError,UnicodeError):pass
 require(set(r['path'][len(str(BASE))+1:] for r in excluded if r.get('reason','').startswith('derived'))==canonical,'all ten exact canonical containers accounted')
 # Preserve all actual helper bytes and directly hash-bound external dependencies.
 extra={}
 for root in (HERE.parent,CLONE,STD):
  for p in root.rglob('*'):
   if p.is_file() or p.is_symlink():extra[str(p)]=p
 def visit(v):
  if isinstance(v,dict):
   if isinstance(v.get('path'),str) and type(v.get('bytes')) is int and isinstance(v.get('sha256'),str) and len(v['sha256'])==64:
    p=Path(v['path'])
    if p.is_absolute() and p.is_file() and not (p==BASE or BASE in p.parents):
     require(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'executed external dependency drift '+str(p));extra[str(p)]=p
   for child in v.values():visit(child)
  elif isinstance(v,list):
   for child in v:visit(child)
 for q in parsed:visit(q)
 for p in sorted(extra.values()):members.append(row(p,'external/'+str(p).lstrip('/')))
 require(len({r['member'] for r in members})==len(members),'unique exact archive member paths')
 order={str(p['path']):i for i,p in enumerate(gate['models'])}
 def key(r):
  if r['path'] in order:return (0,order[r['path']])
  return (1 if r['path'].endswith('.fst') else 2,r['member'])
 members.sort(key=key)
 return dict(frozen_root_paths={str(p):paths(p) for p in (BASE,HERE.parent,CLONE,STD)},schema='csr-unmasked-base-lossless-corpus-v1',scope='full+qualified clone+four STD tests only; all256 future delta NOT accepted',gates=gate,members=members,excluded=excluded,
 canonical_recipe=dict(qualification='RUN/scoped-csr01/qualification01/qualification.json',ordered_selection='RUN/scoped-csr01/records/proposal.json',parser='external/'+str(CLONE/'helper/canonical.py').lstrip('/'),reader='external/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events',algorithm='Use exact executed canonical/framing/protocol modules and ordered proposal selectors; compare complete uncompressed canonical SHA/byte/events/tick bounds from qualification for original and clone. Raw FST plus exact parser/reader are lossless inputs. Original gzip headers/container bytes are not reproduced.',archiver_runs_reader=False),future_delta='Separate fresh admission for all256 three-role raw traces/programs/audits + source, binding this base model/source archive; prospective16MiB not admitted, no quota release or cleanup.')

def unchanged(c):
 for root,names in c['frozen_root_paths'].items():require(paths(Path(root))==names,'new/removed sealed input path '+root)
 for r in c['members']+c['excluded']:require(tuple_stat(Path(r['path']))==r['stat'],'sealed original changed '+r['path'])

def guard():
 q=budget.check();profile=budget.A[3];mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));require(mem>=2*1024**3+max(0,budget.OWN_CAP-q['RUN'])+profile['other_RUN_bytes']+profile['other_SHM_bytes'],'available physical RAM includes1GiB encoder reserve plus1GiB floor and all future RAM charges');return q

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--prepared-sha256');x=p.parse_args();require(x.prepare!=x.execute,'one phase')
 a=budget.configure(x.admission,x.admission_sha256);require(('closure-prepare' if x.prepare else 'closure-execute') in a['actions'],'ROOT explicit closure authority');guard()
 require(a['scope']=='base-full-clone-STD-only; all256 delta pending' and a['TOP']=='a44c03bb7bc520a3b5727c2bb619a055a7ed5acd' and a['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','exact base scope/source')
 prepared=WORK/'inventory.json'
 if x.prepare:
  require(not WORK.exists() and not OUT.exists(),'fresh bounded archive preparation');c=collect(a);WORK.mkdir();prepared.write_text(json.dumps(c,indent=2)+'\n');print(json.dumps(binding(prepared),indent=2));return
 require(binding(prepared)['sha256']==x.prepared_sha256 and not OUT.exists(),'exact reviewed fresh archive inventory');c=json.loads(prepared.read_text());require(gates(a)==c['gates'],'same terminal gates/models');unchanged(c);OUT.mkdir(parents=True);started=time.monotonic();record=dict(state='RUNNING lossless base archival only',admission=budget.bind(x.admission),inventory=binding(prepared),commands=[])
 def save(): (OUT/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_FSIZE,(32*1024**2,32*1024**2))
 try:
  for action,cap in [('compress',600),('roundtrip',180)]:
   left=780-(time.monotonic()-started);require(left>0,'fixed780s total archiver');argv=[sys.executable,HERE/'codec.py','--inventory',prepared,'--output',OUT/'whole-proof.tar.xz','--action',action];entry=dict(action=action,argv=list(map(str,argv)));record['commands'].append(entry);save()
   try:
    with (OUT/(action+'.log')).open('wb') as log:entry['owned']=owned.run(entry['argv'],WORK,dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),log,min(cap,left),guard,limits)
   except BaseException as e:entry['owned']=getattr(e,'owned_receipt',None);raise
   finally:save()
   require(entry['owned']['returncode']==0 and entry['owned']['failure'] is None and not entry['owned']['owned_group_remaining'],'complete owned phase')
  unchanged(c);require(gates(a)==c['gates'],'terminal proofs unchanged');record.update(state='PASS lossless base full+clone+STD archival; all256 delta pending',archive=binding(OUT/'whole-proof.tar.xz'),embedded_inventory=record['inventory'],members=len(c['members']),raw_member_bytes=sum(r['bytes'] for r in c['members']),originals_unchanged=True,resource=budget.check(),no_cleanup=True,elapsed_seconds=time.monotonic()-started);save();budget.check()
 except BaseException as e:record.update(state='FAIL preserved; no retry/cap extension/member drop',error=repr(e));save();raise
 print(record['state'])
if __name__=='__main__':main()
