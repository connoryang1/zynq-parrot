#!/usr/bin/env python3
"""Create a reviewable preparation-only admission; contains no execution call."""
import json
from pathlib import Path
from prepare import bind,patch_mode,ROOT,HERE
from protocol import expected_loads,expected_sum

MODEL_SHA='ef0c7c4c9e84e97d4b71d6c80e6c118d5670411be3a3b16e5469cb89239b5f5d'
PREP=HERE/'prepared01/manifest.json'
INTEGRITY=ROOT/'research/retained-system-geometry-20261121/full-system1280-native0-03-runtime01/session.json'
ADVISORY=ROOT/'research/retained-system-geometry-20261121/scaled-advisory-trace-audit01/verification.json'


def verify(b):
 if bind(b['path'])!=b:raise ValueError('changed frozen input: '+b['path'])


def main():
 p=json.loads(PREP.read_text());i=json.loads(INTEGRITY.read_text());a=json.loads(ADVISORY.read_text())
 if not p['state'].startswith('PREPARED-') or i['state']!='PASS-complete-checked-system-1280-native0-scoped-assertions' or not a['accepted']:raise ValueError('preparation/model gates incomplete')
 verify(i['executable'])
 if i['executable']['sha256']!=MODEL_SHA:raise ValueError('wrong model')
 verify(i['build_session']);build=json.loads(Path(i['build_session']['path']).read_text())
 for b in build['sources_before'].values():verify(b)
 for b in p['sources'].values():verify(b)
 for name in ('elf','nbf','mem'):verify(p[name])
 config=p['symbols']['resume_retained_control']['address'];base=Path(p['nbf']['path']).read_text()
 for mode in (0,9,6,15):
  item=p['mode_patches'][str(mode)];verify(item)
  if Path(item['path']).read_text()!=patch_mode(base,config,mode):raise ValueError('not exact mode-only patch')
 labels={k:hex(v['address']) for k,v in p['symbols'].items() if k.startswith('retained_resume_')}
 metadata=dict(begin_pc=labels['retained_resume_request_begin'],end_pc=labels['retained_resume_request_end'],warmup_requests=8,timed_requests=8,regions='must be independently parsed from closed guest region rows; no predicted/aligned addresses',expected_target_loads_by_context={str(a):expected_loads(a) for a in range(4)},expected_total_by_context={str(a):hex(expected_sum(a)) for a in range(4)})
 result=dict(state='PREPARED-NOT-AUTHORIZED-TO-EXECUTE',model=i['executable'],model_integrity=bind(INTEGRITY),model_advisory=bind(ADVISORY),model_build_session=i['build_session'],model_source_list=build['actual_source_list'],preparation=bind(PREP),preparer=bind(HERE/'prepare.py'),admission_source=bind(__file__),elf=p['elf'],nbf=p['nbf'],mode_patches=p['mode_patches'],sources=p['sources'],
  primary_endpoint='WHOLE core-global cycles before capability/control/alloc through all64 requests, independent checks, peer parking, free, control0 and bounded retained-idle polling; excludes CRT/program load and UART reporting. Actual complete program+CORE+host checks required before accepting any metric.',
  secondary_endpoint='Complete8-round four-actor timed ring including actual handoffs and phase/park bookkeeping, newELF only; never pooled with F35 or FPGA/Linux.',
  topology=dict(resident_slots=2,logical_contexts=4),geometry=dict(retained_i_lines=1280,retained_d_lines=1280,retained_sets=256,ordinary_i_bytes=32768,ordinary_d_bytes=32768),
  workload=dict(kind='lookup',private_bytes_per_actor=32768,actors=4,warm_rounds=8,timed_rounds=8,requests=64,queries_per_request=64,heap_bytes=262144,corpus_total_bytes=131072,static_stacks_bytes=12288,library_and_allocator_storage='additional, not claimed part of corpus'),
  allowed_initial_modes=[0,15],supported_unadmitted_modes=[9,6],execution_budget=dict(native_seconds=1800,host_guard_seconds=1980,fst_limit_bytes=200*1024*1024,attempts_per_mode=1,sequential=True,root_review_required=True),
  run_template=dict(argv=[i['executable']['path'],'+c_args=<exact approved mode NBF> 1800000','+bsg_trace=<new isolated runtime/trace.fst>'],environment=i['environment'],preexec='RLIMIT_CORE=0; RLIMIT_FSIZE=209715200, host timeout1980s; preserve any native/FST/whole-completion failure. No retry/early-stop performance acceptance.'),
  labels=labels,dcache_metadata_template=metadata,
  required_trace_evidence=['full normal cached references including setup/check/free/stack/metadata interference; independent target load counts in each of64 request windows','actual normal tag writes/valid dirty state and complete fills, not miss-only reconstruction','per-lane retained lookups/hits/inserts/completed publications plus accepted mutation invalidations, clear/sweep and wrap activity clipped to WHOLE and timed-ring bounds','control-write/clear/poll intervals from actual retired labels; CSR busy is not a lower-L2/AXI/DRAM drain proof','same corpus bytes, counts, sums, private bounds, ELF/baseNBF/model and only one patched word between arms'],
  limits=['No run performed; this JSON grants no execution permission.','Full FST200MiB feasibility is unproven for this new full-trace model. Limit failure is preserved; no partial result or automatic larger budget.','Core-global interval sums/retention hit counts do not themselves partition critical stalls or prove speedup.','Native full-system memory is uncalibrated; no physical FPGA or Linux projection.'])
 (HERE/'admission.json').write_text(json.dumps(result,indent=2)+'\n');print('PREPARED review admission; no execution')

if __name__=='__main__':main()
