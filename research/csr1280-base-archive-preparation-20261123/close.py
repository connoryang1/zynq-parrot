#!/usr/bin/env python3
"""ROOT-only clean1280 full+clone+STD archival preparation/closure. No reader/target."""
import argparse,gzip,hashlib,json,os,resource,stat,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
import archive_budget as budget
import software_owned_v2 as owned
BASE=budget.BASE;WORK=BASE/'archive32-records01';OUT=budget.DURABLE/'base-full-clone-std-closed01'
DOMAINS=['core252','observer_and_geometry','SP_strict162','capacity167','actual_geometry17']
CLONE=Path('/home/coyang/fpga-artifacts/context-resume/csr1280-observation-preparation-20261122')
STD=Path('/home/coyang/fpga-artifacts/context-resume/csr1280-regression-preparation-20261122')
EXPECTED_MODEL='95699e2ab8c4b3ef7fa8999688d2908dffa65a396c51f63aee522bbf4156a742'
HELPER_ROOTS=(str(HERE),'/home/coyang/zynq-parrot-linux-host-observer/research/csr1280-native-preparation-20261122','/home/coyang/fpga-artifacts/context-resume/csr1280-native-authority-20261123','/home/coyang/fpga-artifacts/context-resume/csr1280-observation-preparation-20261122','/home/coyang/fpga-artifacts/context-resume/csr1280-regression-preparation-20261122','/home/coyang/zynq-parrot-linux-capacity/research/csr1280-initial-native-20261123',str(budget.DURABLE))
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
 # Execute only after all clone/STD records freeze. The clean1280 producer
 # has its own source-bound eleven-phase gate, never the old1536 composite.
 sys.path.insert(0,str(CLONE/'helper'))
 import common
 require(binding(CLONE/'helper/common.py')==a['producer_verifier'],'exact new clean1280 producer verifier')
 full=common.producer()
 require(sha(BASE/'full01/session.json')=='bf2a4ff4d80e7bf254b4e7a3037b9b0f5bbc40d9310ced076d91185d6a753f41','exact clean1280 eleven-phase receipt');require(binding(a['ROOT_initial_acceptance']['path'])==a['ROOT_initial_acceptance'],'exact ROOT initial1280 independent proof')
 require(binding(a['ROOT_git_recovery']['path'])==a['ROOT_git_recovery'],'exact ROOT Git recovery receipt');git=json.loads(Path(a['ROOT_git_recovery']['path']).read_text());repos=git['repositories'];require(git['ROOT_verified'] is True and len(repos)==9 and git['all_durable_HOME_external_stores_preserved'] is True and git['all_working_source_and_private_git_to_be_archived'] is True and {r['source_path']:r['head'] for r in repos}[str(BASE/'source')]==a['TOP'] and {r['source_path']:r['head'] for r in repos}[str(BASE/'source/import/black-parrot')]==a['BP'],'exact actual nine-repository recovery receipt; external objects not archive payload');require(sum(r['archive_includes_objects'] is True for r in repos)==1 and all(r['archive_includes_objects'] or (r['durable_objects'].startswith('/home/coyang/') and r['recovery_ref']=='refs/recovery/linux-retained1280-20261123') for r in repos),'eight persistent HOME recovery refs and one SOURCE-private object store')
 require(full['model']['sha256']==EXPECTED_MODEL,'new fullmodel only')
 flow=state(BASE/'scoped-csr01/flow.json','PASS-one-CSR1280-observation-qualification')
 qual=state(BASE/'scoped-csr01/qualification01/qualification.json','PASS-matched1280-cold08-five-domain-literal-equivalence-strict-counter-geometry')
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
 return dict(full=binding(BASE/'full01/session.json'),ROOT_initial=a['ROOT_initial_acceptance'],ROOT_Git_recovery=a['ROOT_git_recovery'],clone=binding(BASE/'scoped-csr01/flow.json'),qualification=binding(BASE/'scoped-csr01/qualification01/qualification.json'),STD=binding(BASE/'scoped-csr01/architectural-regressions01/session.json'),models=[binding(p) for p in models])

def tuple_stat(p):
 s=p.lstat();return [s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino,stat.S_IMODE(s.st_mode)]
def row(p,member):
 p=Path(p);s=p.lstat();r=dict(path=str(p),member=member,mode=stat.S_IMODE(s.st_mode),stat=tuple_stat(p))
 if p.is_symlink():
  raw=os.readlink(p).encode();r.update(kind='symlink',target=os.readlink(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 else:require(p.is_file(),'no special input '+str(p));r.update(kind='file',bytes=s.st_size,sha256=sha(p))
 return r

def paths(root):
 return sorted(str(p) for p in root.rglob('*') if (p.is_file() or p.is_symlink()) and not (p==WORK or WORK in p.parents or p==OUT or OUT in p.parents))

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
 extra={};identity_pins=[];checked_bindings=set()
 for root in map(Path,HELPER_ROOTS):
  for p in root.rglob('*'):
   if (p.is_file() or p.is_symlink()) and p!=OUT and OUT not in p.parents:extra[str(p)]=p
 def visit(v):
  if isinstance(v,dict):
   if isinstance(v.get('path'),str) and type(v.get('bytes')) is int and isinstance(v.get('sha256'),str) and len(v['sha256'])==64:
    p=Path(v['path']);signature=(str(p),v['bytes'],v['sha256'])
    if p.is_absolute() and signature not in checked_bindings:
     checked_bindings.add(signature)
     require(p.is_file(),'recorded executed input missing/nonfile; no silent skip '+str(p))
     observed=binding(p);observed['stat']=tuple_stat(p);matches=observed['bytes']==v['bytes'] and observed['sha256']==v['sha256']
     cloned_obj=BASE/'scoped-csr01/build/obj';prefix='Vbsg_nonsynth_zynq_testbench'
     rewritten={prefix,prefix+'__ALL.a',prefix+'__Syms.cpp',prefix+'__Syms.o',prefix+'__Syms.d'}
     lineage=p.parent==cloned_obj and p.name in rewritten
     require(matches or lineage,'recorded executed input drift '+str(p))
     if not matches:
      identity_pins.append(dict(category='documented_clone_before_after_lineage',recorded=v,observed=observed,reason='Only copied Syms source/object/dependency,archive and binary may change; original fullmodel remains pinned and untouched-copy reproduction/source-change proof is preserved.'))
     if BASE in p.parents:
      pass # Current file is already in the full RUN member/inventory set.
     else:
      text_suffix={'.py','.c','.cc','.cpp','.h','.hpp','.sv','.svh','.v','.vh','.vlt','.mk','.md','.json','.tsv','.ld','.specs'}
      installed=any(str(p).startswith(q) for q in ('/home/coyang/zynq-parrot/install/','/home/coyang/zynq-parrot-linux-research/install/','/usr/','/lib/','/lib64/'))
      historical_archive=p.name.endswith(('.tar.gz','.tar.xz','.tgz'))
      historical_model_trace=p.suffix=='.fst' or p.name.startswith('Vbsg_nonsynth_zynq_testbench') or 'model' in p.name and p.suffix=='.gz'
      historical_canonical=p.name=='canonical.tsv.gz'
      if (installed and p.suffix not in text_suffix) or historical_archive or historical_model_trace or historical_canonical or p.suffix=='.dcp':
       category='installed_rebuildable_tool_or_library_identity' if installed else 'historical_upstream_proof_identity'
       identity_pins.append(dict(category=category,recorded=v,observed=observed,reason='Identity/provenance input, not current full/clone/STD raw proof. Exact paths/bytes/SHA and executed recipe/version/loader records retained; these binary bytes are not claimed durable in this base archive.'))
      else:extra[str(p)]=p
   for child in v.values():visit(child)
  elif isinstance(v,list):
   for child in v:visit(child)
 for q in parsed:visit(q)
 for p in sorted(extra.values()):members.append(row(p,'external/'+str(p).lstrip('/')))
 require(len({r['member'] for r in members})==len(members),'unique exact archive member paths');actual_fst=sorted(r['path'] for r in members if r['path'].endswith('.fst') and BASE in Path(r['path']).parents);require(a['expected_raw_FST_paths'] is not None and actual_fst==sorted(a['expected_raw_FST_paths']),'ROOT exact final ALL raw FST census; no unknown/failed stream drops')
 require(all(r['bytes']<=128*1024**2 for r in members),'fixed128MiB per-file; preserve on refusal')
 require(sum(r['bytes'] for r in members)<=512*1024**2,'fixed512MiB raw corpus cap; no member omission')
 order={str(p['path']):i for i,p in enumerate(gate['models'])}
 def key(r):
  if r['path'] in order:return (0,order[r['path']])
  return (1 if r['path'].endswith('.fst') else 2,r['member'])
 members.sort(key=key)
 return dict(identity_pins=identity_pins,class_totals=class_totals(members,excluded,identity_pins),frozen_root_paths={str(p):paths(p) for p in [BASE,*map(Path,HELPER_ROOTS)]},schema='csr1280-base32-lossless-corpus-v1',scope='clean1280 full+qualified clone+four STD tests only; all1280 future delta NOT accepted',gates=gate,members=members,excluded=excluded,
 canonical_recipe=dict(qualification='RUN/scoped-csr01/qualification01/qualification.json',ordered_selection='RUN/scoped-csr01/records/proposal.json',parser='external/'+str(CLONE/'helper/canonical.py').lstrip('/'),reader='external/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events',algorithm='Use exact executed canonical/framing/protocol modules and ordered proposal selectors; compare complete uncompressed canonical SHA/byte/events/tick bounds from qualification for original and clone. Raw FST plus exact parser/reader are lossless inputs. Original gzip headers/container bytes are not reproduced.',archiver_runs_reader=False),future_delta='Separate fresh admission for all1280 three-role raw traces/programs/audits + source, binding this base model/source archive; future delta cap not admitted, no quota release or cleanup.')

def class_totals(members,excluded,pins):
 out={}
 for rows,kind in [(members,'archive_members'),(excluded,'nonpayload_RUN_derived_or_cache'),(pins,'identity_only')]:
  for r in rows:
   if kind=='identity_only':category=r['category'];n=r['recorded']['bytes']
   else:
    category=('raw_FST' if r['path'].endswith('.fst') else 'model' if Path(r['path']).name=='Vbsg_nonsynth_zynq_testbench' else 'generated_CXX' if r['path'].endswith(('.cpp','.h','.hpp')) else 'remaining_source_program_proof') if kind=='archive_members' else r['reason']
    n=r['bytes']
   key=kind+':'+category;v=out.setdefault(key,dict(count=0,bytes=0));v['count']+=1;v['bytes']+=n
 return out

def unchanged(c):
 for root,names in c['frozen_root_paths'].items():require(paths(Path(root))==names,'new/removed sealed input path '+root)
 for pin in c['identity_pins']:require(tuple_stat(Path(pin['observed']['path']))==pin['observed']['stat'],'identity input changed '+pin['observed']['path'])
 for r in c['members']+c['excluded']:require(tuple_stat(Path(r['path']))==r['stat'],'sealed original changed '+r['path'])

def guard():
 q=budget.check();profile=budget.A[3];mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));require(mem>=2*1024**3+max(0,budget.OWN_CAP-q['RUN'])+profile['other_RUN_bytes']+profile['other_SHM_bytes'],'available physical RAM includes1GiB encoder reserve plus1GiB floor and all future RAM charges');return q

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--admission',type=Path,required=True);p.add_argument('--admission-sha256',required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--prepared-sha256');x=p.parse_args();require(x.prepare!=x.execute,'one phase')
 a=budget.configure(x.admission,x.admission_sha256);require(('closure-prepare' if x.prepare else 'closure-execute') in a['actions'],'ROOT explicit closure authority');guard()
 require(a['scope']=='1280-base-clean-full-clone-STD-only; all1280 delta pending' and a['TOP']=='88ab04dfcc508176cc977096ca0c132299a8a460' and a['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','exact base scope/source')
 prepared=WORK/'inventory.json'
 if x.prepare:
  require(not WORK.exists() and not OUT.exists(),'fresh bounded archive preparation');c=collect(a);WORK.mkdir();prepared.write_text(json.dumps(c,indent=2)+'\n');print(json.dumps(dict(inventory=binding(prepared),class_totals=c['class_totals']),indent=2));return
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
  unchanged(c);require(gates(a)==c['gates'],'terminal proofs unchanged');record.update(state='PASS base32 lossless1280 clean full+clone+STD archival; all1280 delta pending',archive=binding(OUT/'whole-proof.tar.xz'),embedded_inventory=record['inventory'],members=len(c['members']),raw_member_bytes=sum(r['bytes'] for r in c['members']),originals_unchanged=True,resource=budget.check(),no_cleanup=True,elapsed_seconds=time.monotonic()-started);save();budget.check()
 except BaseException as e:record.update(state='FAIL preserved; no retry/cap extension/member drop',error=repr(e));save();raise
 print(record['state'])
if __name__=='__main__':main()
