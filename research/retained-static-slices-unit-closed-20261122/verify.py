#!/usr/bin/env python3
"""Portable closed-proof checks; optional lossless archive replay, no tools/targets."""
import argparse,gzip,hashlib,json,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
PASS='PASS component full-cycle-defined-client/full512-hit/logical-intent/coherence family'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--external-archive',type=Path);a=ap.parse_args();c=json.loads((HERE/'CHECKPOINT.json').read_text());stored={}
 for r in c['snapshots']:
  p=HERE/r['path'];require(HERE in p.resolve().parents,'relative compact path');raw=p.read_bytes();require(len(raw)==r['gzip_bytes'] and sha(raw)==r['gzip_sha256'],'compressed bytes');data=gzip.decompress(raw);require(len(data)==r['raw_bytes']and sha(data)==r['raw_sha256'],'lossless raw snapshot');stored[r['original']]=data
 require(len(stored)==len(c['snapshots'])==c['compact_lossless_snapshots'],'unique snapshots')
 for name,row in json.loads((HERE/'FILES.json').read_text()).items():
  raw=(HERE/name).read_bytes();require(len(raw)==row['bytes']and sha(raw)==row['sha256'],'compact root file '+name)
 root='/home/coyang/fpga-artifacts/context-resume/retained-cell36-static-slices-20261122'
 native=json.loads(stored[root+'/preparation02/host-supervision.json']);require(native['state']==PASS,'actual component PASS')
 require(sha(stored[root+'/preparation02/host-supervision.json'])==c['component_receipt_sha256'],'accepted8bd1 receipt')
 require(len(native['runs'])==12 and len(native['executables'])==6 and len(native['commands'])==36,'all case/run/phase counts')
 cases=['lines1792','lines1856','lines1911','lines1920','sparse-unequal','disabled-I-dense16cells'];require([(r['case'],r['mode'])for r in native['runs']]==[(x,m)for x in cases for m in ['inverted','different-periods']],'fixed chronology')
 for row in native['commands']:
  require(row['returncode']==0 and not row['owned_group_remaining']and row['owned_receipt']['failure']is None,'every actual phase native0/cleanup')
 for row in native['runs']:
  raw=stored[row['log']['path']];require(sha(raw)==row['log']['sha256'],'runtime log bytes');require(b'PASS' in raw,'closed runtime PASS marker')
 require(native['final_source_check']['candidate']['sha256']==c['candidate_sha256'],'actual source binding')
 candidate=stored[native['final_source_check']['candidate']['path']];require(sha(candidate)==c['candidate_sha256'],'retained candidate snapshot')
 correction=json.loads(stored[root+'/preparation02/prelaunch-allocation-correction.json']);require(correction['old_HOME_source_helper_cap_bytes']==8*1024**2 and correction['new_HOME_source_helper_cap_bytes']==16*1024**2 and correction['no_cleanup']is True,'original prelaunch refusal/correction preserved')
 old=json.loads(stored[root+'/preparation01/admission.json']);new=json.loads(stored[root+'/preparation02/admission.json']);require(old['candidate']['sha256']==new['candidate']['sha256']==c['candidate_sha256'],'same source across prospective allocation correction')
 manifest_path='/home/coyang/fpga-artifacts/context-resume/retained-cell36-static-slices-durable-20261122/closed01/manifest.json';raw=stored[manifest_path];require(sha(raw)==c['durable_manifest_sha256'],'actual durable manifest SHA');m=json.loads(raw)
 require(m['members_verified']==295 and m['raw_FSTs']==12 and m['unit_ELFs']==6 and m['source_endcheck']=='PASS','ALL durable files verified')
 require(m['archive']['archive']==c['durable_archive'],'exact external archive binding')
 require(m['durable_allocation_bytes']==96*1024**2 and m['deadline_seconds']==600 and m['elapsed_seconds']<600,'prospective archive limits')
 require(len(m['archive']['members'])==295 and len({r['member']for r in m['archive']['members']})==295,'exact unique archive members')
 stage=[r for r in m['archive']['members']if r['original']['path'].startswith('/dev/shm/')];require(len(stage)==245 and sum(r['original']['bytes']for r in stage)==85624133,'ALL actual stage files after final checkpoint')
 if a.external_archive:
  h=hashlib.sha256()
  with a.external_archive.open('rb')as f:
   for block in iter(lambda:f.read(1048576),b''):h.update(block)
  require(a.external_archive.stat().st_size==c['durable_archive']['bytes']and h.hexdigest()==c['durable_archive']['sha256'],'external archive exact')
  with tarfile.open(a.external_archive,'r|gz')as tar:
   count=0
   for member in tar:
    require(count<295,'extra archive member');expected=m['archive']['members'][count];require(member.isfile()and member.name==expected['member'],'archive member name/type');h=hashlib.sha256();n=0
    stream=tar.extractfile(member)
    for block in iter(lambda:stream.read(1048576),b''):h.update(block);n+=len(block)
    require(n==expected['original']['bytes']and h.hexdigest()==expected['original']['sha256'],'every member original bytes');count+=1
   require(count==295,'all archive members')
 print(json.dumps(dict(state='PASS portable compact receipts/source/12cases/archive bindings',snapshots=len(stored),external_all295_roundtrip=bool(a.external_archive),new_model_or_vendor_execution=False),indent=2))
if __name__=='__main__':main()
