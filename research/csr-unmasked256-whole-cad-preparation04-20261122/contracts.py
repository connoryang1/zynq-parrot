"""Adapter04 namespace/resources only; exact SOURCE03 authority remains delegated."""
import hashlib,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE_HERE=HERE.parent/'csr-unmasked256-whole-cad-preparation03-20261122'
_spec=importlib.util.spec_from_file_location('csr_source03_contracts',SOURCE_HERE/'contracts.py')
assert hashlib.sha256((SOURCE_HERE/'contracts.py').read_bytes()).hexdigest()=='f16142b169e68abca4670152ee5626799dd768ee7c73c6212f88b18068363908'
OLD=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(OLD)
bind=OLD.bind;exact=OLD.exact;require=OLD.require;native=OLD.native;source_authority=OLD.source_authority
TOP=OLD.TOP;BP=OLD.BP;SOURCE=OLD.SOURCE;FAMILY_ART=OLD.FAMILY_ART;SOURCE_ART=OLD.ART
ART=FAMILY_ART/'preparation04'
WORK=Path('/run/user/1001/zp-linux-csr-unmasked256-trace0-cad-20261122-02');LOGS=OLD.LOGS
PREVIOUS_ADMISSION=SOURCE_ART/'admission01.json'
PREVIOUS_SHA='59bc5d2405976f661cf09f64752edb42d3a91e5f60699f9571ec5b3a0926046b'
CAPS=dict(OLD.CAPS,home_floor_bytes=2147483648)
LOGGING_RESERVE=134217728

def previous():
 require(bind(PREVIOUS_ADMISSION)['sha256']==PREVIOUS_SHA,'exact cancelled admission')
 return json.loads(PREVIOUS_ADMISSION.read_text())
def cancelled_closure(row):
 q=exact(row);old=previous()
 require(q['schema']=='csr256-cancelled-CAD-closure-v1' and q['ROOT_verified'] is True,'ROOT finalized cancellation closure required')
 require(q['TOP']==TOP and q['BP']==BP and q['job']=='20261122T142728Z-a44c03bb7','exact cancelled source/job')
 require(q['final_admission']==bind(PREVIOUS_ADMISSION),'cancelled exact admission binding')
 terminal=exact(q['terminal']);require(terminal['status']=='CANCELLED','actual cancelled terminal')
 require(Path(q['terminal']['path'])==SOURCE_ART/'run-20261122T142728Z-a44c03bb7/terminal-status.json','exact old terminal path')
 archived=exact(q['archival_closure']);require(str(archived.get('state','')).startswith('PASS'),'closed old metadata/source preservation')
 require(q['all_owned_children_absent'] is True and q['global_vendor_absent'] is True,'ROOT actual disappearance proof')
 require(q['future_WORK_bytes']==q['future_HOME_bytes']==0 and q['all_actual_files_still_charged'] is True and q['original_limits_unchanged'] is True,'no future old growth, occupied files still charged, no old cap edit')
 return q

def profile(row):
 q=exact(row);require(q['schema']=='csr256-CAD-adapter04-profile-v1' and q['ROOT_approved'] is True,'ROOT new unlaunched adapter04 profile')
 old=previous();require(q['previous_resource_profile']==old['resource_profile'],'no old OTHER/native reserve change')
 p,b=OLD.profile(q['previous_resource_profile'])
 require(p['current_CSR_native_future']==dict(RUN=1073741824,HOME=33554432,helper=1048576,zero_authority=None),'FULL current native futures retained')
 require(q['own_CAD']==CAPS and q['ongoing_logging_future_bytes']==LOGGING_RESERVE,'new prospective floor and explicit128MiB logging reserve')
 require(q['previous_CAD_future_WORK_bytes']==q['previous_CAD_future_HOME_bytes']==0,'old future zero only via complete ROOT receipt')
 cancelled_closure(q['cancelled_CAD_closure'])
 return q,p,b

def freeze_records(profile_row):
 q,p,b=profile(profile_row);c=exact(q['cancelled_CAD_closure'])
 return OLD.freeze_records()+[q['cancelled_CAD_closure'],c['terminal'],c['archival_closure'],bind(PREVIOUS_ADMISSION)]

def cad_limits(row):
 q,p,b=profile(row);prior=previous()['resources']
 return dict(CAPS,other_work_future_bytes=prior['other_work_future_bytes'],other_home_future_bytes=prior['other_home_future_bytes']+LOGGING_RESERVE,other_shm_future_bytes=prior['other_shm_future_bytes'])
