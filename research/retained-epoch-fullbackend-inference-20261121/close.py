#!/usr/bin/env python3
"""Verify local closed receipts and preserve lossless snapshots; no remote/tool launch."""
from pathlib import Path
import collections,gzip,hashlib,json,re
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; RUN=PREP/'run01'
def bind(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
 a=json.loads((PREP/'admission.json').read_bytes());assert bind(PREP/'admission.json')['sha256']=='6ed830cd4b311bc51b302b285ae2939dc4d543e0056de3d53c5ed5a0b0894720'
 for row in a['inputs']:assert bind(PREP/row['path'])=={k:row[k] for k in ('bytes','sha256')}
 s=json.loads((RUN/'session.json').read_bytes());assert s['state'].startswith('PASS') and s['source_endcheck']=='PASS'
 assert [x['label'] for x in s['commands']]==['idle-fresh','upload','candidate','no-orphans','closed-files','collect'];assert all(x['returncode']==0 for x in s['commands'])
 for row in s['commands']:assert bind(RUN/(row['label']+'.log'))==row['log']
 rows=json.loads((RUN/'closed-files.log').read_bytes())
 for row in rows:assert bind(RUN/'remote'/row['name'])=={k:row[k] for k in ('bytes','sha256')}
 r=json.loads((RUN/'remote/session.json').read_bytes());assert r==s['remote_result'];assert r['state'].startswith('PASS') and r['returncode']==0 and r['elapsed_seconds']<580
 for row in r['inputs']+r['outputs']:assert bind(RUN/'remote'/Path(row['path']).name)=={k:row[k] for k in ('bytes','sha256')}
 assert sum(x['bytes'] for x in rows)<=32*1024**2
 log=(RUN/'remote/console.log').read_text();assert 'ACTUAL_MAX_THREADS 8' in log and 'ACTUAL_TOOL_VERSION 2024.2' in log and 'FULLBACKEND_CANONICAL_INFERENCE_COMPLETE' in log
 assert '[Synth 8-326]' not in log and not re.search(r'^ERROR:',log,re.M)
 snapshots=[]
 sources=[PREP/'admission.json']+[PREP/x['path'] for x in a['inputs']]+[p for p in RUN.iterdir() if p.is_file()]+[p for p in (RUN/'remote').iterdir() if p.is_file()]
 for p in sorted(set(sources)):
  rel=str(p.relative_to(PREP));b=p.read_bytes();target=HERE/(rel.replace('/','__')+'.gz');target.write_bytes(gzip.compress(b,mtime=0));assert gzip.decompress(target.read_bytes())==b
  snapshots.append(dict(source=rel,snapshot=target.name,raw=bind(p),gzip=bind(target)))
 result=dict(state='PASS closed single constrained fullbackend candidate epoch mapping',admission_sha256=bind(PREP/'admission.json')['sha256'],source_start_end_and_collected_input_bindings='PASS',all_six_outer_stages_zero=True,owned_group_reaped_and_global_no_Vivado='PASS runtime guard plus independent no-orphans receipt; no fresh remote observation by closer',native_seconds=r['elapsed_seconds'],mapped_top_level_bytes=sum(x['bytes'] for x in rows),comparison=s['comparison'],warnings=dict(CRITICAL_WARNING_lines=len(re.findall(r'^CRITICAL WARNING:',log,re.M)),WARNING_lines=len(re.findall(r'^WARNING:',log,re.M)),Synth8_326_present=False),scope='Actual named D epoch_ram maps24RAM64M/96RAMD64E and zero epochFF. This is real controller standalone1792 constrainedcandidate, not a paired area delta versus old1280 no-XDC controls or wholeCPU fit/speedup proof. Synthesized-netlist functional equivalence remains untested.',snapshots=snapshots)
 result['closure_files']={n:bind(HERE/n) for n in ('close.py','ANALYSIS.md')}
 (HERE/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('snapshots','comparison')},indent=2));print('manifest',bind(HERE/'manifest.json'))
if __name__=='__main__':main()
