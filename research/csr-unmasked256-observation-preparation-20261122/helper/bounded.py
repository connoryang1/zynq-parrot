"""One existing1GiB/32MiB allocation; fixed OTHER charges, no old CAD scans."""
import importlib.util
import shutil
import sys
import time
from common import *

PREP=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122/preparation02')
SOURCE_PLAN=HERE.parent/'preparation-source.json'
PREP_CAP=1024**2
HOME_CAP=32*1024**2


def used(path):
    return sum(p.lstat().st_size for p in Path(path).rglob('*') if p.is_file() or p.is_symlink()) if Path(path).exists() else 0


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def contracts():
    source=json.loads(SOURCE_PLAN.read_text());row=source['original_execution_admission'];verify(row)
    budget=module(PREP/'budget.py','new_csr_fullcore_budget')
    budget.configure(row['path'],row['sha256'])
    row=source['owned'];verify(row)
    require(row['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','exact qualified owner')
    return budget,module(Path(row['path']),'new_csr_observation_owned')


class Guard:
    def __init__(self,seconds):
        self.budget,self.owned=contracts()
        self.initial=self.budget.check()
        self.original=self.initial['RUN']-used(STAGE)
        require(self.original+ARTIFACT_ALLOCATION<=self.budget.OWN_CAP,'clone256MiB must fit inside original1GiB')
        self.profile=self.budget.A[3]
        self.start=time.monotonic();self.seconds=seconds
        self.home=dict(required_floor=2415919104,OTHER=self.profile['other_HOME_bytes'])

    def __call__(self):
        require(time.monotonic()-self.start<self.seconds,'fixed whole-phase deadline')
        stage=used(STAGE);require(stage<=ARTIFACT_ALLOCATION,'clone aggregate256MiB cap')
        total=self.original+stage;require(total<=self.budget.OWN_CAP,'original+clone must fit whole1GiB')
        helper=used(HERE.parent)+used(self.budget.HELPER_ROOT)+used(HERE.parents[1]/'csr-unmasked256-regression-preparation-20261122')
        home=used(self.budget.DURABLE)
        require(helper<=PREP_CAP and home<=HOME_CAP,'combined helper1MiB/whole HOME32MiB')
        require(shutil.disk_usage(BASE.parent).free>=1024**3+self.budget.OWN_CAP-total+self.profile['other_RUN_bytes'],'RUN floor+whole remaining+fixed OTHER')
        require(shutil.disk_usage(HERE).free>=2415919104+HOME_CAP-home+PREP_CAP-helper+self.profile['other_HOME_bytes'],'HOME2.25GiB+whole remaining+fixed OTHER')
        require(shutil.disk_usage('/dev/shm').free>=512*1024**2+self.profile['other_SHM_bytes'],'unchanged SHM floor+OTHER')
        for row in (self.budget.A[1],self.budget.A[2]['ROOT_resource_profile']):verify(row)

    def finish(self):
        self();after=self.budget.check()
        require(after['RUN']==self.original+used(STAGE),'frozen non-clone original stage changed')
        return after
