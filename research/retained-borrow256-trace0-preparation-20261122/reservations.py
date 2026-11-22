"""Exact ROOT reservation releases and active CAD budgets; never mutates prior data."""
import hashlib,json,stat
from pathlib import Path
HOME=Path('/home/coyang')
ROOT=HOME/'fpga-artifacts/context-resume/reservation-closures-20261122'
BORROW=ROOT/'borrow61d1.json';BORROW_SHA='bbd2d22e5f87446bd60fad9bf4130b2ecfcd2601640a3d9ae18b0a87319c00f9'
CONTROL=ROOT/'control256-complete.json';CONTROL_SHA='5f4a38a59f607ea3f1a55f53e68b1b6008c3f3e2d2f8f2a745689996e4f944f5'
R7=ROOT/'r7-work.json';R7_SHA='2b526287c3df7a57746906c7ad6e16b43d61a9ab33a5074aaf9fafe136f899f9'
CAD_WORK=Path('/run/user/1001/zp-linux-borrow1792-trace0-cad-20261122-01')
CAD_WORK_CAP=2560*1024**2
CAD_EVIDENCE=[HOME/'fpga-logs-linux-retained-borrow1792-trace0',HOME/'zynq-parrot-linux-host-observer/research/borrow-fpga-cad-preparation-20261122']
CAD_EVIDENCE_CAP=384*1024**2
_cache={}
def require(ok,msg):
 if not ok:raise ValueError(msg)
def bind(p):
 p=Path(p);h=hashlib.sha256();n=0
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1048576),b''):n+=len(block);h.update(block)
 return dict(path=str(p),bytes=n,sha256=h.hexdigest())
def receipt(path,sha):
 b=bind(path);require(b['sha256']==sha,'ROOT receipt drift '+str(path))
 if sha not in _cache:_cache[sha]=json.loads(Path(path).read_text())
 return _cache[sha]
def files(root):
 rows={}
 for p in root.rglob('*'):
  # ROOT inventories source symlinks by their file contents too. Permit only
  # the exact listed path set below; before/after SHA checks follow identically.
  if p.is_file():rows[str(p)]=p.stat().st_size
 return rows

def released_closed(path,sha,occupied,allocation,released,full=False):
 q=receipt(path,sha);root=Path(q['family']);rows=files(root);expected={r['path']:r for r in q['files']}
 require(q['actual_closed_logical_bytes']==occupied and q['original_allocation_bytes']==allocation and q['unused_allocation_released_bytes']==released and allocation-occupied==released,'ONLY exact unused ROOT work/durable release')
 require(q.get('original_allocation_limit_unchanged',q.get('original_limit_and_all_prior_receipts_unchanged'))is True and q['new_writes_to_closed_family_require_new_admission']is True,'original cap/immutable future writes')
 require(set(rows)==set(expected)and sum(rows.values())==occupied and all(rows[p]==r['bytes']for p,r in expected.items()),'ALL closed files retained; no exclusions/newwrites')
 if 'archive_manifest'in q:require(bind(q['archive_manifest']['path'])==q['archive_manifest'],'closed archive manifest')
 if 'durable_closure'in q:
  require(bind(q['durable_closure']['path'])==q['durable_closure']and bind(q['terminal']['path'])==q['terminal'],'R7 actual failed terminal/durable proof')
 if full:
  for r in expected.values():require(bind(r['path'])==r,'closed original bytes')
 return dict(receipt=bind(path),occupied_bytes=occupied,files=len(rows),original_cap=allocation,unused_released=released,future_growth_reserved=0)

def borrow(full=False):
 q=receipt(BORROW,BORROW_SHA);require(q['source_model_sha256']=='61d1d3cb15edc62901782a174f783cad2de1c2a83af3751b9b58524ab82049cd','actual61d model')
 return released_closed(BORROW,BORROW_SHA,43676466,96*1024**2,56986830,full)
def r7(full=False):return released_closed(R7,R7_SHA,309757881,2560*1024**2,2374596679,full)
def control(full=False):
 q=receipt(CONTROL,CONTROL_SHA)
 require(q['previous_release_bytes']==27714708 and q['additional_release_bytes']==11923842,'cumulative old256 release, never counted twice')
 require(bind(q['prior_reservation']['path'])==q['prior_reservation']and bind(q['complete_cohort_manifest']['path'])==q['complete_cohort_manifest'],'terminal complete all3audit/cohort lineage')
 result=released_closed(CONTROL,CONTROL_SHA,94579178,128*1024**2,39638550,full)
 return dict(result,remaining_growth=0)

def cad():
 require(CAD_WORK.is_dir()and all(p.is_dir()for p in CAD_EVIDENCE),'actual active CAD roots required')
 work=sum(p.stat().st_size for p in CAD_WORK.rglob('*')if p.is_file());evidence={}
 for root in CAD_EVIDENCE:
  require(root.stat().st_dev==HOME.stat().st_dev,'CAD evidence HOME volume')
  for p in root.rglob('*'):
   if p.is_file():evidence[str(p.resolve())]=p.stat().st_size
 used=sum(evidence.values());require(work<=CAD_WORK_CAP and used<=CAD_EVIDENCE_CAP,'activeCAD original work/evidence caps')
 return dict(work_root=str(CAD_WORK),work_bytes=work,work_cap=CAD_WORK_CAP,remaining_work=CAD_WORK_CAP-work,evidence_roots=list(map(str,CAD_EVIDENCE)),evidence_union_bytes=used,evidence_cap=CAD_EVIDENCE_CAP,remaining_evidence=CAD_EVIDENCE_CAP-used,work_floor=1024**3,HOME_floor=2560*1024**2)
