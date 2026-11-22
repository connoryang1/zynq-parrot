#!/usr/bin/env python3
"""Read immutable archives/proofs only; never run a model, reader or vendor tool."""
import argparse,gzip,hashlib,io,json,tarfile
from pathlib import Path
ROOT=Path('/home/coyang/fpga-artifacts/context-resume')
CLOSED=ROOT/'retained256-qualification-20261122/cohort-ro04-closed01'
FORMAL=ROOT/'reservation-closures-20261122/control256-complete.json'
RECIPE=ROOT/'retained256-cohort-archive-20261122/preparation01'
EXPECTED_MANIFEST='922d8674d69cdb660465566656c80ab1464074c2f5ab5995716610513c23ea6f'
EXPECTED_ARCHIVE='57945a81bdbfcf72828d88f71104e7680691f81282349fc1630cd52d48fe4f1b'
EXPECTED_FORMAL='5f4a38a59f607ea3f1a55f53e68b1b6008c3f3e2d2f8f2a745689996e4f944f5'
ROLES=('d-enabled','d-off','i-enabled')
COUNTERS={'d-enabled':[0,256,0,256,0,2048],'d-off':[0]*6,'i-enabled':[256,0,256,0,2048,0]}
ACCEPT={'d-enabled':'7ee90c878a551e030f0c16a55ee0fa28fc11b16762be87907e5f5c50d2c2b2f9','d-off':'15a5f76e0295337c1af25e5777ef0c722c55e7101f519f5be2f2f60b7ec7fcd7','i-enabled':'7c4ffe1808c07f6aad04dd8dd4b14d69169d933bb31605b5ab0f9b526fb5d2d4'}
def need(v,m):
 if not v:raise ValueError(m)
def rawbind(path,raw):return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def bind(p):p=Path(p);return rawbind(p,p.read_bytes())
def readj(raw):return json.loads(raw)
def checkrow(row,raw):need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'exact proof/input bytes '+row['path'])
def target_check(v,role):
 need(v['state'].startswith('PASS negative actual ordinary-memory fallback' if role=='d-off' else 'PASS actual distinct') and v['lines']==256 and v['sets']==256 and v['lane']==role[0],'exact completed256 audit')
 targets=v['targets'];need(len(targets)==256 and {x['slot'] for x in targets.values()}==set(range(256)),'all256 distinct slots')
 need(all(len(x['words'])==8 for x in targets.values()),'actual full64B expected per target')
 enabled=role!='d-off';bursts=v['retained_bursts'] if enabled else v['ordinary_bursts'];need(len(bursts)==256,'all256 winning L1 bursts')
 need(len(v['publications'])==(256 if enabled else 0) and len(v['hits'])==(256 if enabled else 0),'all publications/hits or none in off')
 need(len(v['ordinary_bursts'])==(0 if enabled else 256) and len(v['retained_bursts'])==(256 if enabled else 0),'ordinary/retained complete paths')
 seen=set()
 for b in (bursts.values() if isinstance(bursts,dict) else bursts):
  address=int(b['address']);need(address not in seen and str(address) in targets,'unique matching target burst');seen.add(address)
  words=list(b['words'].values()) if isinstance(b['words'],dict) else b['words'];need(len(words)==8,'eight actual winning64-bit writes')
  expected=targets[str(address)]['words'];actual={int(w['address']):int(w['data']) for w in words}
  need(len(actual)==8 and all(actual.get(address+8*k)==expected[k] for k in range(8)),'all512 actual winning SRAM bits')
 if role=='i-enabled':need(set(v['retired_instruction_pcs'])==set(targets) and all(len(pcs)==16 for pcs in v['retired_instruction_pcs'].values()),'all16 actual instruction PCs per I target')
 else:need(v['d_protected_load_retirements']==2048,'all2048 protected target D load retirements')
 return dict(targets=256,publications=len(v['publications']),hits=len(v['hits']),retained_L1_bursts=len(v['retained_bursts']),ordinary_L1_bursts=len(v['ordinary_bursts']),winning_64bit_L1_writes=2048,checked_payload_bytes=16384,I_target_instruction_PCs=sum(len(x) for x in v['retired_instruction_pcs'].values()),D_protected_load_retirements=v['d_protected_load_retirements'],markers=v['markers'])

def review(curate=None):
 manifest=bind(CLOSED/'manifest.json');need(manifest['sha256']==EXPECTED_MANIFEST,'ROOT manifest external anchor');m=readj((CLOSED/'manifest.json').read_bytes());need(m['state']=='PASS OLD256 complete lossless closure; prior operational failures preserved','closed whole archive')
 archive=bind(m['archive']['path']);need(archive==m['archive'] and archive['sha256']==EXPECTED_ARCHIVE and archive['bytes']==13153559,'exact raw archive')
 formal=bind(FORMAL);need(formal['sha256']==EXPECTED_FORMAL,'formal closure anchor');f=readj(FORMAL.read_bytes());need(f['complete_cohort_manifest']==manifest and f['actual_closed_logical_bytes']==94579178 and f['unused_allocation_released_bytes']==39638550 and f['no_cleanup'] and f['new_writes_to_closed_family_require_new_admission'],'formal closed-family bytes/release')
 for row in f['files']:need(bind(row['path'])==row,'all formal durable files unchanged')
 expected={x['member']:x for x in m['inventory']};seen=set();data={};compact={};total=0
 with tarfile.open(archive['path'],'r|gz') as tar:
  for info in tar:
   need(info.name in expected and info.name not in seen,'all and only unique archived members');seen.add(info.name);r=expected[info.name];need(info.mode==r['mode'],'mode preserved')
   if r['type']=='directory':need(info.isdir(),'directory type');continue
   if r['type']=='symlink':need(info.issym() and info.linkname==r['link'],'symlink target/type');continue
   need(info.isfile(),'regular file');raw=tar.extractfile(info).read();checkrow(r,raw);total+=len(raw)
   # Raw waveforms/ELFs/NBFs stay external. Keep all small executed source and proof documents.
   if info.name.endswith(('.json','.py','.md','.log','.stderr','.tsv')):
    data[info.name]=raw;compact['archive/'+info.name]=raw
 need(len(seen)==m['all_members']==259 and total==m['all_regular_bytes']==46692110,'all259 members and46692110 raw bytes independently verified')
 prep=readj(data['stage/preparation.json']);need(prep['model']['sha256']=='1e9519cf83ede8d1bb7dd1d7924a98945cb274d8f2b666faf73737fb3376fe59','old8df trace1 model')
 need(prep['geometry']==dict(i_lines=256,d_lines=256,sets=256,line_bytes=64,ordinary_sets=64,ordinary_ways=8,l2_bytes=16384,observe=1,delay=0,num_threads=2,num_contexts=4),'actual old256 geometry')
 roles={}
 for role in ROLES:
  n=readj(data['stage/'+role+'/verification.json']);accept=data['stage/'+role+'-audit-ro04/acceptance.json'];need(hashlib.sha256(accept).hexdigest()==ACCEPT[role],'exact complete role acceptance')
  a=readj(accept);v=readj(data['stage/'+role+'-audit-ro04/verification.json']);need(n['counters']==COUNTERS[role] and n['state'].startswith('PASS negative checked' if role=='d-off' else 'PASS primary256') and n['actual_returncode']==-6,'native checked pass with precise teardown allowance, not exit0')
  checkrow(v['bindings']['run'],data['stage/'+role+'/verification.json']);checkrow(v['bindings']['preparation'],data['stage/preparation.json']);checkrow(a['files'][0],data['stage/'+role+'-audit-ro04/verification.json'])
  life=readj(data['stage/'+role+'-audit-ro04/reader.owned.json']);need(life['returncode']==0 and life['failure'] is None and not life['owned_group_remaining'],'reader actual0/cleanup')
  counter=readj(data['stage/'+role+'-audit-ro04/counter-words.json']);need(counter['values']==COUNTERS[role] and counter['state'].startswith('PASS final FST counter'),'counter corroboration')
  stream=v['archive']['full_stream'];need(stream['reader_returncode']==0 and stream['exact_end_records']==1 and stream['lines']==stream['events']+169,'complete167 stream/EOF')
  roles[role]=dict(target_check(v,role),native_counter_words=n['counters'],native_process_returncode=-6,native_scope='accepted existing precise postPASS teardown exception; not a normal exit0',acceptance_sha256=ACCEPT[role],full167_stream=stream,raw_FST=next(x for x in n['files'] if x['path'].endswith('/trace.fst')))
 failures=[]
 for idx,dirname in enumerate(('d-enabled-audit','d-enabled-audit-ro01','d-enabled-audit-ro02','d-enabled-audit-ro03'),1):
  need('stage/'+dirname+'/acceptance.json' not in expected,'original failure must not become accepted');facts=readj(data[f'helpers/ROOT-audit-failure{idx:02}/ROOT-exit.json']);need(facts['exit_code']==1 and not facts['native_retried'] and not facts['acceptance_created'],'failed audit preserved without native retry');failures.append(dict(stage_directory=dirname,ROOT_facts=facts))
 result=dict(state='PASS independent lossless OLD256 closure and serialized full-payload proof review',archive_manifest=manifest,archive=archive,formal_closure=formal,archive_members=259,archive_regular_bytes=total,geometry=prep['geometry'],model=prep['model'],BP_commit='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c',TOP_source='596e4677fdcbbf59706be254384f778861f0cc36',cache_miss_trace=1,program_ELF_sha256='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6',roles=roles,failed_operational_audits=failures,archive_operational_seconds=m['elapsed_seconds'],no_new_reader_model_target_vendor_or_cleanup=True,limits='Historical canonical8df/trace1 simulation functional evidence only. Not the new bb575 borrowing/trace0 small image; no FPGA fit/application or latency claim.')
 if curate:
  curate=Path(curate);curate.mkdir(exist_ok=True)
  for p in [CLOSED/'manifest.json',FORMAL,Path(m['admission']['path']),Path(m['reservation']['path'])]+[RECIPE/n for n in ('archive_cohort.py','test_archive.py','README.md','handoff.json')]:compact['external/'+p.name if p.name not in ('manifest.json','README.md') else 'external/'+p.parent.name+'-'+p.name]=p.read_bytes()
  with (curate/'proofs.tar.gz').open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
   for name,value in sorted(compact.items()):
    info=tarfile.TarInfo(name);info.size=len(value);info.mtime=0;tar.addfile(info,io.BytesIO(value))
  index=[dict(member=k,bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for k,v in sorted(compact.items())]
  (curate/'proof-members.json').write_text(json.dumps(index,indent=2)+'\n');result['compact_proofs']=bind(curate/'proofs.tar.gz');result['compact_members']=len(index)
  (curate/'review.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--curate',type=Path);a=p.parse_args();v=review(a.curate);print(json.dumps(dict(state=v['state'],archive_members=v['archive_members'],roles={k:{x:y for x,y in v.items() if x in ('publications','hits','retained_L1_bursts','ordinary_L1_bursts','winning_64bit_L1_writes')} for k,v in v['roles'].items()}),indent=2))
