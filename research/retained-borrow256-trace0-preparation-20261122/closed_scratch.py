"""ROOT-closed scratch archive reservation: retain all data, release only unused bytes."""
import hashlib,json,stat
from pathlib import Path
HERE=Path(__file__).resolve().parent
RECEIPT=Path('/home/coyang/fpga-artifacts/context-resume/reservation-closures-20261122/scratch3f3.json')
RECEIPT_SHA='8beb366b58c2d7925e37e9082ca50c2fb88a38f4f892436e46953511142aaf5a'
FAMILY=Path('/home/coyang/fpga-artifacts/context-resume/retained-scratch-trace0-fullcore-20261122')
MANIFEST=FAMILY/'closed01/archive.json'
MANIFEST_SHA='0fcbdb18912bc043ac814c8484e55bee30c5b330809143031656237490d8bba8'
FOOTPRINT_SHA='fffd3730e4499ea751d80dfe38f3812f4e1f58ba3f6225dfbd939b7d76e9c05b'
ORIGINAL_CAP=128*1024**2
OCCUPIED=42659209
RELEASED=91558519
MODEL='3f3e8b766f19746cb434e99200c0bde49853e4c0cc27aeec7a0dbacec7f6b2df'
def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(path):
 p=Path(path);h=hashlib.sha256();n=0
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block);n+=len(block)
 return dict(path=str(p),bytes=n,sha256=h.hexdigest())
def fingerprint():
 rows=[]
 for p in sorted(FAMILY.rglob('*')):
  s=p.lstat();require(not stat.S_ISLNK(s.st_mode),'closed scratch symlink forbidden')
  if stat.S_ISREG(s.st_mode):rows.append(dict(path=str(p.relative_to(FAMILY)),bytes=s.st_size,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns))
 return rows

def verify(full=False):
 receipt=bind(RECEIPT);require(receipt['sha256']==RECEIPT_SHA,'exact ROOT closure receipt')
 r=json.loads(RECEIPT.read_text());require(r['state']=='CLOSED immutable durable archive; unused reservation released by ROOT','closed archive state')
 require(r['family']==str(FAMILY)and r['family_files']==11 and r['actual_closed_logical_bytes']==OCCUPIED,'actual occupied family')
 require(r['original_allocation_bytes']==ORIGINAL_CAP and r['unused_allocation_released_bytes']==RELEASED and ORIGINAL_CAP-OCCUPIED==RELEASED,'release ONLY exact unused reservation')
 require(r['original_allocation_limit_unchanged']is True and r['new_writes_to_closed_family_require_new_admission']is True,'immutable original cap/no future writes')
 require(r['source_model_sha256']==MODEL,'closed model identity')
 require(bind(MANIFEST)==r['archive_manifest']and r['archive_manifest']['sha256']==MANIFEST_SHA,'actual closed manifest bytes')
 require(bind(HERE/'closed-scratch-footprint.json')['sha256']==FOOTPRINT_SHA,'fixed closed-file fingerprint')
 expected=json.loads((HERE/'closed-scratch-footprint.json').read_text());rows=fingerprint()
 for row in expected['metadata_bindings']:require(bind(row['path'])==row,'closed plan metadata hash')
 require(rows==expected['files'] and len(rows)==11 and sum(x['bytes']for x in rows)==OCCUPIED,'ALL occupied files retained/unchanged; no exclusions')
 m=json.loads(MANIFEST.read_text());require(m['state']=='PASS lossless durable scratch-only1792 trace0 first-native composite archive'and m['model']['sha256']==MODEL,'accepted closed model/archive lineage')
 if full:
  require(len(m['archives'])==9,'all nine closed payload archives')
  for row in m['archives']:require(bind(row['archive']['path'])==row['archive'],'closed payload archive hash')
  require(fingerprint()==rows,'closed files changed during complete payload checks')
 return dict(receipt=receipt,archive_manifest=r['archive_manifest'],source_model_sha256=MODEL,occupied_bytes=OCCUPIED,occupied_files=11,original_allocation_bytes=ORIGINAL_CAP,unused_reservation_released_bytes=RELEASED,full_payload_hashes_checked=full)
