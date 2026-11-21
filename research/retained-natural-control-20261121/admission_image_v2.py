#!/usr/bin/env python3
"""Prepare corrected-image resource admission for review; no execution."""
import json
from pathlib import Path
from prepare import bind,ROOT,HERE


def main():
 image=HERE/'image-v2-01/manifest.json';v=json.loads(image.read_text());old=HERE/'admission.json';a=json.loads(old.read_text())
 if v['state']!='PASS-packaging-coverage-only-no-execution' or not v['base_coverage']['all_file_backed_bytes_exact'] or not v['unchanged_elf']:raise ValueError('packaging preflight incomplete')
 if v['elf']!=a['elf']:raise ValueError('ELF changed')
 if bind(a['model']['path'])!=a['model']:raise ValueError('model changed')
 for r in v['sources'].values():
  if bind(r['path'])!=r:raise ValueError('target source changed')
 for item in v['mode_patches'].values():
  if not item['coverage']['all_file_backed_bytes_exact'] or bind(item['nbf']['path'])!=item['nbf']:raise ValueError('patched image incomplete')
 failed=HERE/'cohort01/cohort.json';f=json.loads(failed.read_text())
 if f['state']!='STOPPED-failure-preserved-no-retry' or len(f['runs'])!=1 or f['runs'][0]['returncode']!=-25:raise ValueError('failed cohort history mismatch')
 r=dict(a);r.update(state='PREPARED-CORRECTED-IMAGE-PREFLIGHT-PASS-EXECUTION-NOT-AUTHORIZED',image_preflight=bind(image),image_preparer=bind(HERE/'prepare_image_v2.py'),original_admission=bind(old),nbf=v['nbf'],mode_patches={k:x['nbf'] for k,x in v['mode_patches'].items()},
  failed_cohort=bind(failed),failure_diagnosis=bind(HERE/'LOADER_REGRESSION.md'),failure_null='Original cohort executed zero natural requests, repeatedly faulted in calloc from omitted ELF zeros; no complete execution or arm effect. Remains failed, not pooled.',
  execution_budget=dict(native_seconds=1800,host_guard_seconds=1980,fst_limit_bytes=1024*1024*1024,maximum_pair_fst_bytes=2*1024*1024*1024,attempts_per_mode=1,sequential=True,root_review_required=True),
  resource_basis='Proposed fixed1GiB/arm resource bound; HOME previously24GiB free, maximum2GiB pair. No trace-scope/model change. Larger cap alone would not fix original invalid loop; corrected ELF-zero materialization is mandatory. Completion feasibility is unproven; runtime budget unchanged; no effect-based extension.',
  run_template=dict(argv=[a['model']['path'],'+c_args=<exact approved v2 mode NBF> 1800000','+bsg_trace=<new isolated runtime/trace.fst>'],environment=a['run_template']['environment'],preexec='RLIMIT_CORE=0; RLIMIT_FSIZE=1073741824; host timeout1980s; only0→15 after complete0; any failure stops, no retry.'),
  limits=['No corrected-image target execution authorized or performed.','Fixed1GiB FST/arm feasibility is unproven; any failure preserves attempt/stops cohort, no automatic retry or budget increase.','No trace-scope, C/ELF/layout/corpus/model change; never pool failed original image with corrected image.','Actual complete normal-cache/retained audits required before any performance inference; native simulation uncalibrated, no Linux/FPGA projection.'],
  corrected_source_unchanged=True,admission_v2_source=bind(__file__))
 (HERE/'admission-v2.json').write_text(json.dumps(r,indent=2)+'\n');print('PREPARED corrected-image admission; NOT execution-authorized')

if __name__=='__main__':main()
