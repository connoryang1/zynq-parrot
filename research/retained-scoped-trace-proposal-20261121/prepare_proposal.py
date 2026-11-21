#!/usr/bin/env python3
"""READ-ONLY metadata proposal. No model copy/edit/compile/relink/target run."""
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
N=ROOT/'research/retained-natural-control-20261121';S=ROOT/'research/retained-native-service-20261121'
BUILD=ROOT/'research/retained-system-geometry-20261121/full-system1280-native0-03'
OBJ=BUILD/'design/verilator/obj_dir';PREFIX='Vbsg_nonsynth_zynq_testbench';SYMS=PREFIX+'__Syms'


def bind(path):
 p=Path(path).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def headers(path):
 rows=[]
 with gzip.open(path,'rt') as f:
  for line in f:
   p=line.rstrip('\n').split('\t')
   if p[0]=='#SIGNAL':rows.append(dict(key=p[1],width=int(p[2]),path=p[4]))
   elif p[0].isdigit():break
 return rows


def main():
 out=HERE/'proposal.json'
 if out.exists():raise ValueError('preserve existing proposal')
 comp=N/'comparison-v3-01/comparison.json';comparison=json.loads(comp.read_text());model=bind(OBJ/PREFIX)
 if model['sha256']!='ef0c7c4c9e84e97d4b71d6c80e6c118d5670411be3a3b16e5469cb89239b5f5d':raise ValueError('wrong immutable native model')
 if comparison['state']!='CLOSED-complete-audited-single-pair':raise ValueError('closed references required')
 union={};domain_bindings={}
 for mode in (0,15):
  domains={
   'normal105':N/f'audits-v3-01/mode{mode}-normal/normal-dcache/selected-events.tsv.gz',
   'retained45':N/f'audits-v3-01/mode{mode}-retained/selected-events.tsv.gz',
   'HP0_UCE107':S/f'mode{mode}-hp0/selected-events.tsv.gz'}
  domain_bindings[str(mode)]={}
  for domain,path in domains.items():
   declarations=headers(path);domain_bindings[str(mode)][domain]=dict(input=bind(path),declarations=len(declarations))
   for row in declarations:
    entry=union.setdefault(row['path'],dict(path=row['path'],width=row['width'],required_by=[]))
    if entry['width']!=row['width']:raise ValueError('inconsistent original declaration width')
    role=domain+':'+row['key']
    if role not in entry['required_by']:entry['required_by'].append(role)
 reader=ROOT/'research/retained-system-geometry-20261121/reader/fst_events'
 listing=subprocess.run([str(reader),str(N/'cohort-v3-01/mode0/trace.fst'),'--list'],capture_output=True,text=True,check=True,timeout=60)
 declarations=[line.split('\t') for line in listing.stdout.splitlines() if line.startswith('#VAR')]
 prefix='core_minimal.be.commit_pkt.'
 extra={prefix+'ctxtsw':1,prefix+'exception':1}
 for name,width in (('funct7',7),('rs2_addr',5),('rs1_addr',5),('funct3',3),('rd_addr',5),('opcode',7)):
  extra[prefix+'instr.t.rtype.'+name]=width
 for suffix,width in extra.items():
  found=[d for d in declarations if d[3].endswith('.'+suffix)]
  if len(found)!=1 or int(found[0][1])!=width:raise ValueError('missing actual retired instruction/context-switch leaf')
  path=found[0][3];entry=union.setdefault(path,dict(path=path,width=width,required_by=[]));entry['required_by'].append('retired-instruction-context-switch-exception')
 # Derive exact existing compiler/link argv, including the historical PCH guard.
 log=BUILD/'build.log';lines=log.read_text().splitlines()
 compile_lines=[l for l in lines if l.startswith('g++ ') and '-o '+SYMS+'.o ' in l]
 link_lines=[l for l in lines if l.startswith('g++ ') and l.rstrip().endswith('-o '+PREFIX)]
 if len(compile_lines)!=1 or len(link_lines)!=1:raise ValueError('ambiguous actual host commands')
 compile_argv=shlex.split(compile_lines[0]);link_argv=shlex.split(link_lines[0]);header=PREFIX+'__pch.h';alias=header+'.slow'
 pch_lines=[l for l in lines if l.startswith('g++ ') and l.rstrip().endswith('-x c++-header '+header+' -o '+alias+'.gch')]
 if len(pch_lines)!=1:raise ValueError('missing exact PCH creation command')
 pch_argv=shlex.split(pch_lines[0])
 if pch_argv[:-5]!=compile_argv[:-6] or compile_argv[-6:]!=['-include',alias,'-c','-o',SYMS+'.o',SYMS+'.cpp']:raise ValueError('PCH compiler/preprocessor provenance differs')
 mapped_compile=list(compile_argv);mapped_compile[-5]=header
 host_objects=[p for p in link_argv if p.endswith('.o')]
 expected_host=['main.o','ps.o','bsg_nonsynth_dpi_clock_gen.o','verilated.o','verilated_dpi.o','verilated_fst_c.o','verilated_threads.o']
 if host_objects!=expected_host:raise ValueError('not original seven frozen host/runtime objects')
 archive=OBJ/(PREFIX+'__ALL.a');members=subprocess.check_output(['ar','t',str(archive)],text=True).splitlines()
 if len(members)!=len(set(members)) or SYMS+'.o' not in members:raise ValueError('bad archive ownership')
 member_hashes={name:hashlib.sha256(subprocess.check_output(['ar','p',str(archive),name])).hexdigest() for name in members}
 inventory={p.name:bind(p) for p in sorted(OBJ.iterdir()) if p.is_file() and p.suffix!='.gch'}
 syms=(OBJ/(SYMS+'.cpp')).read_text();needle='        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n'
 if syms.count(needle)!=1 or syms.index(needle)>syms.index('__Vm_dumperp->open('):raise ValueError('actual trace-filter insertion guard differs')
 old=Path('/home/coyang/zynq-parrot-linux-research/research/resume-data-reuse-20261120')
 runtime=Path('/home/coyang/zynq-parrot/install/share/verilator/include')
 proposal=dict(state='PROPOSAL-ONLY-NO-CLONE-IMPLEMENTATION-BUILD-OR-TARGET-EXECUTION',purpose='Host tracing resource feasibility with exact complete outputs/cycles and required-event equivalence against BOTH closed native0 capacity arms; no new effect sample.',
 source=bind(__file__),model=model,comparison=bind(comp),service_closure=bind(S/'closed-inputs.json'),
 original_generated_root=str(OBJ),original_build_log=bind(log),original_generated_files=inventory,
 original_archive=bind(archive),archive_member_sha256=member_hashes,original_Syms=bind(OBJ/(SYMS+'.cpp')),
 compile_argv=compile_argv,original_PCH_creation_argv=pch_argv,textual_header_compile_argv=mapped_compile,link_argv=link_argv,
 host_objects={name:bind(OBJ/name) for name in host_objects},PCH_textual_header=bind(OBJ/header),
 trace_registration_marker=needle.strip(),filter_API='One dumpvars(1, exactcanonicalleaf) call per leaf, after trace registration and before open, in COPIED Syms.cpp only.',
 filter_leaves=sorted(union.values(),key=lambda r:r['path']),filter_leaf_count=len(union),reference_domains=domain_bindings,
 reviewed_runtime={name:bind(runtime/name) for name in ('verilated_fst_c.h','verilated_fst_c.cpp','verilated_trace_imp.h')},
 historical_complete_gate=bind(old/'scoped-mode0-validation/validation.json'),historical_guarded_driver=bind(old/'trace-filter-review/build_scoped_model.py'),
 estimated_copy_bytes_without_PCH=sum(r['bytes'] for r in inventory.values()),excluded_disposable_PCH_bytes=sum(p.stat().st_size for p in OBJ.glob('*.gch')),
 proposed_resource=dict(copy_directory='research/retained-scoped-native-20261121/build01',single_host_compile_job=True,no_RTL_elaboration=True,no_target_recompile=True,
 native_seconds_per_arm=1800,host_guard_seconds_per_arm=1980,FST_cap_bytes_per_arm=150*1024*1024,max_new_pair_FST_bytes=300*1024*1024,attempts_per_arm=1,mode_order=[0,15],root_review_required=True,free_HOME_bytes=shutil.disk_usage(HERE).free),
 mandatory_build_gates=['Original generated tree/object/archive/member hashes unchanged before/after.',
 'Untouched direct relink of copied original objects must reproduce exact ef0c executable BEFORE any filter edit.',
 'Compile ONLY copied Syms.cpp using exact guarded real-text-PCH mapping; replace ONLY copied archive Syms.o; direct relink frozen seven runtime objects.',
 'All eval/generated source/headers/other archive members/objects remain byte-identical; original binary/archive/tree never modified. Record new filtered binary identity.'],
 mandatory_qualification=['Preflight exact same8c83ELF/zero-preserving original modeNBF, original dynamic-loader/library hashes and source bindings. No ELF/source/layout/corpus/timing/parameter change.',
 'Mode0 then15, each one bounded attempt.15only after0complete guest/CORE/host and ALL mode0 equivalence gates. Any failure stops; no retry/automatic extension.',
 'Require byte-exact target protocol rows including all sums/regions/status/polls/WHOLE/ring values and identical CORE/host terminal behavior. Nondeterministic host elapsed/path diagnostics are separately retained, never used as target equivalence.',
 'Require finalized FST and exactly the reviewed leaf hierarchy; all required declarations/widths must exist. Empty hierarchy scopes are harmless.',
 'Require byte-exact canonical complete normal-access/tag/refill event stream, retained512b/ownership/publication/coherence/offer-wait stream, retired PC/instruction/context-switch/first-target-load stream, and opaque HP0AR/AW/W/R/B burst/timing/concurrency streams against corresponding ORIGINAL arm.',
 'Canonicalization may replace FST declaration handles with reviewed paths and normalize serialization order; it may not discard events, times, payloads, idle/clear/offer waits or pre/post-timing execution.',
 'Require unchanged primary cycles1159423/1191569,ring366663/375588 and complete trace clock endpoints; no repeated metrics pooled into the original negative effect pair.',
 'Only after both gates may a separately reviewed runner admit filtered clone for new predeterminedcontrols/latencies. Native9/6,N40/200 remain unauthorized by this proposal.'],
 limitations=['Observation-only filter, no address/time/access-outcome filtering. Still TRACE=1 and same post-init assertion scope.',
 'Storage reduction and150MiB completion are UNMEASURED; budget is a proposed feasibility bound, not a guarantee. Any cap failure invalidates clone admission.',
 'All alias/packed-array/struct leaf names must remain verbatim. dumpvars(0,...) enables everything and is forbidden.',
 'FutureN40/200 builds need the same union plus existing delay/FIFO fields when actually present; missing originalN0 generate scopes must not be fabricated. Qualify each new model identity before long runs.',
 'No FPGA/routing/calibrated-latency or speedup claim. This file implements no clone or execution driver.'])
 out.write_text(json.dumps(proposal,indent=2)+'\n')
 (HERE/'required-leaves.tsv').write_text(''.join(str(r['width'])+'\t'+r['path']+'\n' for r in proposal['filter_leaves']))
 print(json.dumps({k:proposal[k] for k in ('state','filter_leaf_count','estimated_copy_bytes_without_PCH','excluded_disposable_PCH_bytes','original_Syms','original_archive','proposed_resource')},indent=2))


if __name__=='__main__':main()
