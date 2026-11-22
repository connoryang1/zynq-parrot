"""Shared existing allocations, with cheap changing-output guards between phases."""
import importlib.util
import shutil
import sys
import time
from common import *

PREP=Path('/home/coyang/zynq-parrot-hp0-timing-diagnostic-20261122/research/retained-borrow256-trace0-preparation-20261122')
OWNED=HERE.parents[1]/'retained256-qualification-20261122/software_owned_v2.py'
PREP_CAP=1024**2
HOME_CAP=16*1024**2


def used(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file()) if Path(path).exists() else 0


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def contracts():
    sys.path.insert(0,str(PREP))
    budget=module(PREP/'budget.py','qualified_borrow256_budget')
    require(bind(OWNED)['sha256']=='52c89d489177fdee6f2c941c5744f86433f320201b9588547cc23c3f22810bc5','unchanged qualified own-group guard')
    return budget,module(OWNED,'qualified_borrow256_owned')


class Guard:
    def __init__(self,seconds):
        self.budget,self.owned=contracts()
        self.initial=self.budget.check();self.home=self.budget.source.budget()
        self.original=self.initial['own_bytes']-used(STAGE)
        require(self.original+ARTIFACT_ALLOCATION<=self.budget.OWN_CAP,'full256MiB reserved INSIDE original768MiB; no cleanup/growth')
        require(not DURABLE.exists(),'fresh16MiB durable suballocation inside original64MiB')
        self.start=time.monotonic();self.seconds=seconds;self.next_cad=0;self.cad=None

    def __call__(self):
        require(time.monotonic()-self.start<self.seconds,'fixed whole-phase deadline')
        stage=used(STAGE);require(stage<=ARTIFACT_ALLOCATION,'256MiB clone cap')
        total=self.original+stage;require(total<=self.budget.OWN_CAP,'all original work+clone within768MiB')
        if self.cad is None or time.monotonic()>=self.next_cad:
            self.cad=self.budget.source.reservations.cad();self.next_cad=time.monotonic()+1
        old=self.initial
        need=self.budget.FLOOR+self.budget.OWN_CAP-total
        need+=self.budget.MATCHED_CAP-old['matched_bytes']+self.budget.SCRATCH_CAP-old['scratch_bytes']+self.budget.BORROW1792_CAP-old['borrow1792_bytes']
        need+=self.cad['remaining_work']
        require(shutil.disk_usage(BASE.parent).free>=need,'1GiB plus ALL remaining old/current/CAD work allocations')
        durable=used(self.budget.DURABLE);require(durable<=self.budget.DURABLE_CAP and used(DURABLE)<=HOME_CAP,'existing64MiB total/16MiB subcap')
        prep=used(HERE.parent);require(prep<=PREP_CAP,'new1MiB source-only prep cap')
        home_need=self.home['required_free_bytes']-self.home['active_CAD']['remaining_evidence']+self.cad['remaining_evidence']
        home_need+=self.budget.DURABLE_CAP-durable+PREP_CAP-prep
        require(shutil.disk_usage(HERE).free>=home_need,'HOME2.5GiB plus all source/helper/evidence remaining reservations')

    def finish(self):
        self();after=self.budget.check()
        require(after['own_bytes']==self.original+used(STAGE),'all frozen original work sizes unchanged')
        return after
