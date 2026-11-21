#!/usr/bin/env python3
"""Verify the external stopped-build archive and current kept sparse inputs; no vendor or writes there."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,re,subprocess,tarfile
P=Path(__file__).resolve().parent
E=Path('/home/coyang/fpga-artifacts/context-resume/native1792-canonical-r6-preparation-20261121')
W=Path('/home/coyang/fpga-work-linux-retained-native1792-canonical-r6/zynq-parrot-fpga-20261121T220319Z-eb7d39013')
TOP='eb7d390134a0025331a2366a979a774263b146d5';BP='8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def identity(path):
 h=hashlib.sha256();size=0
 with path.open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data);size+=len(data)
 return dict(bytes=size,sha256=h.hexdigest())
def git(repo,*args):return subprocess.check_output(['git','--no-optional-locks','-C',str(repo),*args],text=True).strip()
def main():
 m=E/'closed01/manifest.json';assert identity(m)['sha256']=='017acd4f3fae640720fa78a1b6bbe04fce9dfb65af42ba4bcc8814c9bd40487a';assert m.read_bytes()==(P/'external-closure-manifest.json').read_bytes();closure=json.loads(m.read_bytes())
 for name,row in closure['files'].items():assert identity(E/'closed01'/name)==row,'frozen closure metadata drift '+name
 archive=E/'closed01/closed-inputs.tar.gz';assert identity(archive)==dict(bytes=85792703,sha256='42d241f41b563800596041957c3ca7072aff002626190387bcde8e262c7ddfe3')
 rows=json.loads((E/'closed01/inputs.json').read_bytes());expected={r['member']:r for r in rows};assert len(expected)==1400 and not any(n.startswith('worker/research/') for n in expected)
 seen=set()
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   assert member.isfile() and member.name in expected;raw=tar.extractfile(member).read();r=expected[member.name];assert len(raw)==r['bytes'] and sha(raw)==r['sha256'];seen.add(member.name)
 assert seen==set(expected)
 inv=json.loads((P/'checkpoint-inventory.json').read_bytes());assert inv['checkpoints']==[] and inv['generated_checkpoints']==0
 assert git(W,'rev-parse','HEAD')==TOP and (W/'import/black-parrot/.git').exists() and git(W/'import/black-parrot','rev-parse','HEAD')==BP
 assert git(W,'diff','--name-only')=='' and git(W/'import/black-parrot','diff','--name-only')==''
 selected=[]
 for r in rows:
  member=r['member'];suffix=Path(member).suffix.lower()
  source=r['kind'] in {'generated_HDL_include_init','build_or_design_source','build_identity_source','canonical_RTL_source'}
  metadata=r['kind']=='generated_project_metadata_or_log' and suffix in {'.tcl','.xdc','.xci','.xpr','.xml','.bd'} and '/.Xil/' not in member
  if member.startswith('worker/') and (source or metadata):
   path=Path(r['path']);assert path.is_file(),'kept source missing '+str(path);actual=identity(path);assert actual==dict(bytes=r['bytes'],sha256=r['sha256']),'kept source drift '+str(path);selected.append(dict(member=member,**actual))
 patterns=git(W,'sparse-checkout','list').splitlines();assert set(patterns)=={'ci','codex-skills','cosim','import','software','testing','tools'}
 # Independent actual consumer files retained by the archive and still byte-identical.
 v=W/'cosim/black-parrot-example/vivado';t=(v/'black_parrot_bd_proj.runs/synth_1/black_parrot_bd_1_wrapper.tcl').read_text();defs='BP_RETAINED_BUFFER=1 BP_RETAINED_I_LINES=1792 BP_RETAINED_D_LINES=1792 BP_RETAINED_SETS=256 BP_RETAINED_OBSERVE=1 BP_AXI_RESPONSE_DELAY=0';assert 'set_property verilog_define {'+defs+'} [current_fileset]' in t
 xpr=(v/'black_parrot_bd_proj.xpr').read_text();assert all('Name="'+n+'" Val="'+val+'"' in xpr for n,val in (x.split('=') for x in defs.split()))
 cfg=(v/'bsg_blackparrot_pkg.sv').read_text();assert 'bp_cfg_gp = e_bp_unicore_zynqparrot_prefetch16k_cfg;' in cfg
 config=(v/'config.tcl').read_text();child=(v/'black_parrot_bd_proj.runs/synth_1/vivado.tcl').read_text();assert re.search(r'set ::env\(ACLK_MHZ\)\s+\{?20\}?',child) and re.search(r'set ::env\(THREADS\)\s+\{?8\}?',config)
 for n in ['sparse-stopped-source-validation.json','sparse-readiness-first-failure.json','sparse-fresh-materialization-test.json']:
  assert (P/n).read_bytes()==(E/n).read_bytes(),'root outcome receipt drift '+n
 sparse=json.loads((P/'sparse-stopped-source-validation.json').read_bytes());fresh=json.loads((P/'sparse-fresh-materialization-test.json').read_bytes());assert sparse['readiness_returncode']==0 and sparse['top']==TOP and sparse['bp']==BP and fresh['tracked_blobs_verified']==1152 and fresh['vendor_launches']==0
 assert (P/'sparse-build-ready-final.log').read_text().rstrip().endswith('BUILD READY')
 polls=[]
 for p in sorted(E.glob('poll-*.json')):
  j=json.loads(p.read_bytes());polls.append(dict(file=p.name,sha256=identity(p)['sha256'],utc=j['utc'],status=j['status'],resources=j['resources'],feature_state=j['feature_state'],identity_violations=j['identity_violations'],feedback_warnings=j['feedback_warnings']))
 assert max(r['resources']['work_allocated_bytes'] for r in polls)==1647423488 and polls[-1]['status']=='CANCELLED'
 (P/'poll-summary.json').write_text(json.dumps(polls,indent=2)+'\n')
 (P/'kept-source-index.json.gz').write_bytes(gzip.compress((json.dumps(selected,indent=2)+'\n').encode(),mtime=0))
 ack=Path('/home/coyang/fpga-artifacts/pynq-session-ack-linux.json');a=json.loads(ack.read_bytes());hold=dict(source=str(ack),source_identity=identity(ack),recorded_updated_utc=a['updated_utc'],builder_hold=a['builder_hold']);assert hold['builder_hold']['owner_thread']=='01a1f709-66c7-72d1-95fa-93795ddf79ab' and not hold['builder_hold']['linux_vivado_active'];(P/'builder-hold-snapshot.json').write_text(json.dumps(hold,indent=2)+'\n')
 assert git(W,'rev-parse','HEAD')==TOP and git(W/'import/black-parrot','rev-parse','HEAD')==BP
 result=dict(state='PASS compact cancelled-R6 closure verification; no fit result',utc=datetime.now(timezone.utc).isoformat(),external_manifest=dict(path=str(m),**identity(m)),external_archive=dict(path=str(archive),**identity(archive),members_verified=1400),checkpoints=0,independent_kept_source_hashes_verified=len(selected),sparse_patterns=patterns,actual_consumer_defines=defs,CFG='e_bp_unicore_zynqparrot_prefetch16k_cfg',requested_ACLK_MHz=20,workers=8,peak_sampled_work_bytes=1647423488,hard_cap_bytes=1610612736,source_TOP=TOP,source_BP=BP,current_tracked_source_diff='empty',scope='Operational work-cap stop before completed synthesis. No resource/route/timing/capacity result; later sparse readiness and fresh materialization are source/tooling validation only.',vendor_launches=0,board_actions=0,deletions=0,main_edits=0,validator=identity(P/'verify.py'));(P/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
