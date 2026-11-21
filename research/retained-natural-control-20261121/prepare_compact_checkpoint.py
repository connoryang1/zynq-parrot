#!/usr/bin/env python3
"""Archive ONLY owned closed source/compact evidence; never stages or runs targets."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent


def bind(path):
 p=Path(path).resolve();h=hashlib.sha256()
 with p.open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest())


def main():
 cohort=json.loads((HERE/'cohort-v3-01/cohort.json').read_text())
 comparison=json.loads((HERE/'comparison-v3-01/comparison.json').read_text())
 if cohort['state']!='COMPLETE-both-arms-awaiting-full-trace-audit-no-performance-inference' or comparison['state']!='CLOSED-complete-audited-single-pair':raise ValueError('complete audited pair required')
 if comparison['cohort']!=bind(HERE/'cohort-v3-01/cohort.json'):raise ValueError('closed cohort mismatch')
 out=HERE/'compact-evidence';out.mkdir(exist_ok=False)
 selected=set(HERE.glob('*.json'))|set(HERE.glob('*.log'))
 # Compiled input copies, immutable program/image and detailed preparation.
 for directory in ('prepared01','image-v2-01'):
  for p in (HERE/directory).rglob('*'):
   if p.is_file() and p.suffix not in ('.pyc','.gz') and p.name not in ('mode9.nbf','mode6.nbf'):selected.add(p)
 # Closed failures/qualifications retain their records, exact earlier source,
 # and selection schema. Large selected/raw FSTs remain externally durable.
 for directory in ('failed-progress01','failed-control-diagnostic01','failed-allocation-fault01','failed-malloc-data01','failed-progress-v2-01','failed-resource-v2-01','dcache-adapter','retained-audit-qualified-advisory01','retained-audit-qualified-advisory02','retained-audit-qualified-advisory03','retained-audit-qualified-advisory04','join-qualified-advisory01','comparison-v3-01'):
  for p in (HERE/directory).rglob('*'):
   if p.is_file() and p.suffix in ('.json','.py','.tsv','.log','.stderr'):selected.add(p)
 for directory in ('cohort01','cohort-v2-01','cohort-v3-01'):
  for p in (HERE/directory).rglob('*'):
   if p.is_file() and p.suffix in ('.json','.log'):selected.add(p)
 for p in (HERE/'audits-v3-01').rglob('*'):
  if p.is_file() and (p.suffix in ('.json','.log','.tsv','.stderr') or p.name=='events.jsonl.gz'):selected.add(p)
 # Small closed event ledgers support independent join review without rawFST.
 selected.add(HERE/'dcache-adapter/closed-advisory01/events.jsonl.gz')
 selected.add(HERE/'join-qualified-advisory01/retained-events.jsonl.gz')
 entries=[]
 for p in sorted(selected):
  if not p.is_file():raise ValueError('missing explicit compact input '+str(p))
  if p.stat().st_size>4*1024*1024:raise ValueError('unexpected large compact input '+str(p))
  relative=p.relative_to(HERE)
  compress=p.suffix not in ('.py','.c','.h','.tsv','.gz')
  target=out/('records' if compress else 'preserved')/relative
  if compress:target=Path(str(target)+'.gz')
  target.parent.mkdir(parents=True,exist_ok=True)
  original=p.read_bytes()
  target.write_bytes(gzip.compress(original,mtime=0) if compress else original)
  recovered=gzip.decompress(target.read_bytes()) if compress else target.read_bytes()
  if recovered!=original:raise ValueError('archive roundtrip failed')
  entries.append(dict(original=bind(p),archived=bind(target),compression='gzip-mtime0' if compress else 'identity',roundtrip_exact=True))
 external=[]
 for p in sorted(HERE.rglob('*')):
  if out in p.parents or not p.is_file():continue
  if p.suffix=='.fst' or p.name=='selected-events.tsv.gz':external.append(bind(p))
 top_sources=sorted([p for pattern in ('*.py','*.md') for p in HERE.glob(pattern)])
 manifest=dict(state='CLOSED-compact-archive-roundtrip-PASS',purpose='Reviewable source and actual closed complete-access/retained ledgers, with all failures preserved. Huge raw waveforms/models/generated designs are excluded from Git and remain durable at hash-bound paths.',
 cohort=bind(HERE/'cohort-v3-01/cohort.json'),comparison=bind(HERE/'comparison-v3-01/comparison.json'),
 source=bind(__file__),top_owned_sources=[bind(p) for p in top_sources],
 target_source=bind(HERE.parents[1]/'testing/mt_retained_resume_data_benchmark.c'),
 model=cohort['model'],external_raw_or_selected_artifacts=external,
 entries=entries,limits=['No FPGA/routing proof or accepted optimization. Single negative native0 pair, no performance projection.',
 'Raw FST and selected105/45port streams remain external; archived actual event ledgers include every accepted normal cached reference/miss/refill/eviction and retained event, not miss-only data.',
 'Earlier capped traces are unfinalized diagnostics and are never accepted as cache/performance samples.'])
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 whitelist=[str(p.relative_to(HERE.parents[1])) for p in top_sources]+['testing/mt_retained_resume_data_benchmark.c']
 whitelist += [str(p.relative_to(HERE.parents[1])) for p in sorted(out.rglob('*')) if p.is_file()]
 whitelist.append(str((HERE/'checkpoint-whitelist.json').relative_to(HERE.parents[1])))
 (HERE/'checkpoint-whitelist.json').write_text(json.dumps(dict(state='PROPOSED-narrow-commit-whitelist-not-staged',paths=whitelist,files=len(whitelist),compact_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),forbidden='No other root files/gitlinks/SDK/RTL/model/generatedobj/rawFST/uncompressed reader binaries.'),indent=2)+'\n')
 print(json.dumps(dict(archived_entries=len(entries),whitelist_files=len(whitelist),compact_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())),indent=2))


if __name__=='__main__':main()
