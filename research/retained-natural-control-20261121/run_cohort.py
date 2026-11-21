#!/usr/bin/env python3
"""Root-approved bounded offline0→15 cohort; no build, retry or board action."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import time
from prepare import bind,ROOT,HERE
from admission import MODEL_SHA,PREP,INTEGRITY,ADVISORY
from protocol import parse

ELF_SHA='8c83ca26bb44b3d1eb294e568a65323fa75820c6aefa049baa4e6da4002525f4'
CAP=200*1024*1024


def verify(b):
 if bind(b['path'])!=b:raise ValueError('frozen input changed: '+b['path'])


def limits():
 resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(CAP,CAP))


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve()
 if out.exists() or not str(out).startswith('/home/coyang/'):raise ValueError('fresh isolated HOME cohort directory required')
 p=json.loads(PREP.read_text());i=json.loads(INTEGRITY.read_text());a=json.loads(ADVISORY.read_text());admission=HERE/'admission.json'
 if not p['state'].startswith('PREPARED-') or not a['accepted'] or not i['state'].startswith('PASS-complete-checked-system'):raise ValueError('admission/model prerequisites failed')
 if i['executable']['sha256']!=MODEL_SHA or p['elf']['sha256']!=ELF_SHA:raise ValueError('wrong exact model/ELF')
 verify(i['build_session']);build=json.loads(Path(i['build_session']['path']).read_text());frozen=dict(build['sources_before'])
 records=[bind(PREP),bind(INTEGRITY),bind(ADVISORY),bind(admission),i['executable'],p['elf'],p['nbf'],build['actual_source_list']]+list(p['sources'].values())+[p['mode_patches'][str(mode)] for mode in (0,15)]
 for name in ('prepare.py','admission.py','protocol.py','prepare_watchpaths.py','retention-selection.json','retention-selection.tsv','run_cohort.py'):records.append(bind(HERE/name))
 for name in ('libboost_context.so.1.72.0','libboost_coroutine.so.1.72.0','libboost_system.so.1.72.0'):records.append(bind(ROOT/'../zynq-parrot/install/lib'/name))
 for r in records:frozen[r['path']]=r
 for b in frozen.values():verify(b)
 out.mkdir();env=dict(os.environ);env['LD_LIBRARY_PATH']=i['environment']['LD_LIBRARY_PATH']
 cohort=dict(state='running',authorization='Parent/root explicit2026-11-21 approval: modes0 then15 only;15 only after0 complete checker PASS; oneattempt/arm;1800s native1980s host200MiB; any failure stops; no board.',
               model=i['executable'],elf=p['elf'],base_nbf=p['nbf'],mode_order=[0,15],budget=dict(native_seconds=1800,host_seconds=1980,fst_bytes=CAP),environment=i['environment'],frozen_inputs=frozen,runs=[])
 def save():(out/'cohort.json').write_text(json.dumps(cohort,indent=2)+'\n')
 save()
 try:
  for mode in (0,15):
   if mode==15 and (len(cohort['runs'])!=1 or cohort['runs'][0]['state']!='COMPLETE-checks-PASS-awaiting-full-trace-audit'):raise ValueError('joint arm lacks complete off prerequisite')
   for b in frozen.values():verify(b)
   runtime=out/f'mode{mode}';runtime.mkdir();trace=runtime/'trace.fst';log=runtime/'run.log';nbf=p['mode_patches'][str(mode)]
   cmd=[i['executable']['path'],'+c_args='+nbf['path']+' 1800000','+bsg_trace='+str(trace)]
   row=dict(state='running',mode=mode,nbf=nbf,argv=cmd,cwd=str(runtime),command_start_monotonic=time.monotonic());cohort['runs'].append(row);save()
   linked=subprocess.run(['ldd',i['executable']['path']],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10);(runtime/'loader-preflight.log').write_text(linked.stdout)
   if linked.returncode or 'not found' in linked.stdout:raise ValueError('host library preflight failed')
   row['loader_preflight']=bind(runtime/'loader-preflight.log');row['linked_libraries']=[]
   for line in linked.stdout.splitlines():
    for word in line.split():
     if word.startswith('/') and Path(word).is_file():row['linked_libraries'].append(bind(word))
   if mode==15 and row['linked_libraries']!=cohort['runs'][0]['linked_libraries']:raise ValueError('host library identities differ between arms')
   save();start=time.monotonic()
   with log.open('wb') as output:r=subprocess.run(cmd,cwd=runtime,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=1980,preexec_fn=limits)
   row.update(returncode=r.returncode,elapsed_seconds=time.monotonic()-start,log=bind(log));save()
   # Includes maintained full CORE/host checks, exact custom marker ordering,
   # independent64-request sums, regions/status and whole/ring chronology.
   guest=parse(log.read_text(),mode,r.returncode);(runtime/'guest-observations.json').write_text(json.dumps(guest,indent=2)+'\n');row['guest']=bind(runtime/'guest-observations.json')
   template=json.loads(admission.read_text())['dcache_metadata_template'];metadata=dict(template)
   metadata['regions']=[dict(context=v['context'],base=hex(v['base']),bytes=v['bytes']) for v in guest['regions']]
   metadata['whole_begin_cycle']=guest['phases']['whole_begin'];metadata['whole_end_cycle']=guest['phases']['whole_end']
   metadata['whole_stage_labels']=json.loads(admission.read_text())['labels']
   (runtime/'trace-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');row['trace_metadata']=bind(runtime/'trace-metadata.json')
   if not 0<trace.stat().st_size<CAP:raise ValueError('missing/at-limit FST, no acceptance')
   row['trace']=bind(trace)
   for b in frozen.values():verify(b)
   for b in row['linked_libraries']:verify(b)
   row['state']='COMPLETE-checks-PASS-awaiting-full-trace-audit';save()
   print('mode',mode,row['state'],flush=True)
  cohort['state']='COMPLETE-both-arms-awaiting-full-trace-audit-no-performance-inference'
 except BaseException as e:
  cohort.update(state='STOPPED-failure-preserved-no-retry',error=repr(e))
  if cohort['runs']:
   row=cohort['runs'][-1];runtime=Path(row['cwd']);row['state']='FAIL-preserved-no-result'
   for key,name in [('trace','trace.fst'),('log','run.log')]:
    if (runtime/name).is_file():row[key]=bind(runtime/name)
  raise
 finally:save();print(out/'cohort.json',cohort['state'],flush=True)

if __name__=='__main__':main()
