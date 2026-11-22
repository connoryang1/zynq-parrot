"""Review the completed audits without rewriting any failed receipt."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,stat,sys
sys.dont_write_bytecode=True
H=Path('/home/coyang/fpga-artifacts/context-resume/csr1536-composite-continuation-preparation-20261122/preparation01')
sys.path.insert(0,str(H));spec=importlib.util.spec_from_file_location('preserved_tail_inputs',H/'continue_full.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
B=c.BASE;T=B/'full03';R=B/'full02';original=T/'session.json';s=json.loads(original.read_text())
assert s['state']=='FAIL tail protected source/end-resource check' and s['end_error']=='AssertionError()'
assert s['total_qualified_phases']==11 and [x['label']for x in s['commands']]==['counter','parameters']
assert all(x['ownership']['returncode']==0 and x['ownership']['failure'] is None and not x['ownership']['owned_group_remaining'] for x in s['commands'])
assert s['old_partial_integrity_explicitly_excluded'] and s['old_failed_counter_receipt_explicitly_excluded']
protected=json.loads(gzip.decompress((T/'protected-inputs.json.gz').read_bytes()));differences=[];members=0
allowed=str(R/'advisory')
for root,rows in protected.items():
 actual=c.inventory(Path(root));assert set(actual)==set(rows);members+=len(rows)
 for name,before in rows.items():
  after=actual[name]
  if after!=before:
   assert name==allowed and stat.S_ISDIR(before['mode'])
   assert {k:v for k,v in before.items()if k not in ('mtime_ns','ctime_ns')}=={k:v for k,v in after.items()if k not in ('mtime_ns','ctime_ns')}
   assert after['mtime_ns']>=before['mtime_ns'] and after['ctime_ns']>=before['ctime_ns']
   differences.append(dict(path=name,before=before,after=after))
assert len(differences)==1
readerbuild=Path('/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events.build.json')
rb=json.loads(readerbuild.read_text())
for row in rb['sources']+rb['headers']:c.verify(row)
assert c.bind(c.READER)['sha256']==rb['executable']['sha256']=='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541'
fstapi=Path('/home/coyang/zynq-parrot/install/share/verilator/include/gtkwave/fstapi.c');text=fstapi.read_text()
assert c.bind(fstapi)['sha256']=='6a09b5a4aea241f12939e8005f7e2c1b2c60f28e39d66a1d02d3edd69c80a1c8'
assert '"%s.hier_%d_%p", xc->filename, getpid(), (void *)xc' in text and 'xc->fh = fopen(fnam, "w+b")' in text and 'if(fnam) unlink(fnam)' in text
for row in s['closed_audits'].values():c.verify(row)
strict=json.loads(Path(s['closed_audits']['strict']['path']).read_text());counter=json.loads(Path(s['closed_audits']['counter']['path']).read_text());geo=json.loads(Path(s['closed_audits']['parameters']['path']).read_text())
assert strict['accepted'] and counter['firsttouch_counts']==dict(i=[1,1,8],d=[1,1,8])
assert len(geo['facts']['values'])==17 and geo['facts']['values']['retained_store.storage.i_lines_p']==geo['facts']['values']['retained_store.storage.d_lines_p']==1536
assert counter['bindings']['fst']==strict['bindings']['fst']==c.bind(R/'advisory/trace.fst')
for row in counter['bindings'].values():c.verify(row)
for row in json.loads((R/'prepared.json').read_text())['inputs']:c.verify(row)
c.inherited();a=c.authority(c.FINAL,'50144661b7aef0b8e16a43b4a630595cbd110cb0462db3ac01e7c8c0f2df15e4','execute');c.budget(a)
s.update(state='PASS COMPOSITE CSR1536 cleanbuild/loader plus complete integrity/cold08 strict512b-eight-real-writes-Iretire-counter-17geometry-source-audits',source_endcheck='PASS',
 original_tail_receipt=c.bind(original),ROOT_finalizer=c.bind(Path(__file__).resolve()),protected_members_verified=members,
 directory_timestamp_review=dict(scope='Exactly one FST input directory; all file bytes, inode, permissions, timestamps and complete membership unchanged. No file metadata exception.',changes=differences,
 cause='Pinned compiled FST reader creates and unlinks its input-adjacent .hier_PID_PTR temporary hierarchy at fstapi.c:3950-4000.',reader_build=c.bind(readerbuild),compiled_fstapi=c.bind(fstapi)))
s.pop('end_error',None);dest=T/'ROOT-composite.json';assert not dest.exists();c.write(dest,s);print(json.dumps(c.bind(dest)))
