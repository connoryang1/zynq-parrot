"""Fresh source-bound guard; clone+STD remain inside SAME1GiB/32MiB family."""
import importlib.util
import shutil
import time
from common import *
SOURCE_PLAN=HERE.parent/'preparation-source.json'
POOL_CAP=1024**3;HOME_CAP=32*1024**2;PACKET_CAP=128*1024
DURABLE_FAMILY=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked768-fullcore-20261123')
PACKET_ROOTS=(HERE.parent,HERE.parents[1]/'csr768-regression-preparation-20261123')


def used(path):
    p=Path(path)
    return sum(q.lstat().st_size for q in p.rglob('*') if q.is_file() or q.is_symlink()) if p.exists() else 0


def contracts():
    source=json.loads(SOURCE_PLAN.read_text())
    row=source['ROOT_resource_profile'];verify(row);q=json.loads(Path(row['path']).read_text())
    require(q['schema']=='csr768-native-resource-profile-v1' and q['ROOT_approved'] is True and q['all_other_charged_reserves_included'] is True,'fresh ROOT full OTHER resource profile required')
    require(q['TOP']=='1b24c915ed628f6d47a382b3aa89fb662884e1a1' and q['BP']=='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa','exact profile source')
    require(q['caps']==dict(RUN=POOL_CAP,base_HOME=HOME_CAP,helper_HOME=128*1024,program_inside_RUN=8*1024**2),'unchanged original whole pool/base caps')
    require(q['RUN_floor_bytes']>=1024**3 and q['HOME_floor_bytes']>=1879048192 and q['SHM_floor_bytes']>=512*1024**2 and q['required_MemAvailable_bytes']>=8*1024**3,'unchanged current floors/headroom')
    require(all(type(q[k]) is int and q[k]>=0 for k in ('other_RUN_bytes','other_HOME_bytes','other_SHM_bytes')),'explicit other reserves')
    for r in q['basis_records']:verify(r)
    row=source['owned'];verify(row)
    require(row['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','qualified own process guard')
    spec=importlib.util.spec_from_file_location('csr768_observation_owner',row['path']);owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
    return source,q,owned


class Guard:
    def __init__(self,seconds):
        self.source,self.profile,self.owned=contracts();self.plan=bind(SOURCE_PLAN)
        self.start=time.monotonic();self.seconds=seconds
        self.original=used(BASE)-used(STAGE)
        require(self.original+ARTIFACT_ALLOCATION<=POOL_CAP,'prospective clone256MiB must fit unchanged whole1GiB with all failed inputs')
        self.home=dict(required_floor=self.profile['HOME_floor_bytes'],OTHER=self.profile['other_HOME_bytes'],new_source_inside_existing_logging=True)
        self.initial=self.snapshot();self()

    def snapshot(self):return dict(RUN=used(BASE),HOME=used(DURABLE_FAMILY),clone=used(STAGE),helper=sum(used(p) for p in PACKET_ROOTS))

    def __call__(self):
        require(time.monotonic()-self.start<self.seconds,'fixed whole-phase deadline')
        require(bind(SOURCE_PLAN)==self.plan,'source plan immutable')
        verify(self.source['ROOT_resource_profile']);q=self.profile
        for r in q['basis_records']:verify(r)
        s=self.snapshot();require(s['clone']<=ARTIFACT_ALLOCATION and s['RUN']<=POOL_CAP,'clone256MiB and whole1GiB caps')
        require(s['HOME']<=HOME_CAP and s['helper']<=PACKET_CAP,'whole32MiB durable and new source128KiB inside logging')
        require(shutil.disk_usage(BASE.parent).free>=q['RUN_floor_bytes']+POOL_CAP-s['RUN']+q['other_RUN_bytes'],'RUN floor+whole remaining+ALL_OTHER')
        require(shutil.disk_usage(HERE).free>=q['HOME_floor_bytes']+HOME_CAP-s['HOME']+q['other_HOME_bytes'],'HOME floor+whole durable remaining+ALL_OTHER logging/source')
        require(shutil.disk_usage('/dev/shm').free>=q['SHM_floor_bytes']+q['other_SHM_bytes'],'SHM floor+ALL_OTHER')
        mem=next(int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'))
        require(mem>=q['required_MemAvailable_bytes'],'same physical memory headroom')

    def finish(self):
        self();after=self.snapshot();require(after['RUN']-after['clone']==self.original,'all inactive nonclone original bytes unchanged')
        return after
