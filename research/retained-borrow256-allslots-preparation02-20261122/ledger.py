"""RO04 seal-at-entry/exit accounting, with accepted separate-process monitor."""
from contextlib import contextmanager
import gzip
import json
import os
from pathlib import Path
import shutil
import sys
import time
import contract as c
from process_monitor import phase as monitor_phase


def scan(root):
    rows={};todo=[Path(root)]
    if not Path(root).exists():return rows
    while todo:
        with os.scandir(todo.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):todo.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=True):rows[Path(entry.path)]=entry.stat(follow_symlinks=True).st_size
    return rows


def inventory(root,exclude=None):
    result={}
    for path in scan(root):
        if exclude is not None and (path==exclude or exclude in path.parents):continue
        st=path.stat();row=c.bind(path);row.update(device=st.st_dev,inode=st.st_ino,mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns,mode=st.st_mode)
        result[str(path)]=row
    return result


def classify(path,stage):
    rel=Path(path).relative_to(stage);top=rel.parts[0]
    if len(rel.parts)==2 and rel.parts[1]=='trace.fst':return 'raw:'+top
    for role in c.ORDER:
        if top==role+'-audit':return 'audit:'+role
    return 'other'


def charges(rows,stage):
    out={'other':0,**{'raw:'+r:0 for r in c.ORDER},**{'audit:'+r:0 for r in c.ORDER}}
    for path,size in rows.items():out[classify(path,stage)]+=size
    return out


def phase_caps(rows,stage,C):
    q=charges(rows,stage)
    raw=sum(q['raw:'+r]for r in c.ORDER);audit=sum(q['audit:'+r]for r in c.ORDER)
    c.require(sum(q.values())<=C['stage_total'] and raw<=C['raw_total'] and audit<=C['audit_total'] and q['other']<=C['other_total'],'fixed whole/raw/audit/other phase caps')
    c.require(all(q['raw:'+r]<=C['raw_per_case'] and q['audit:'+r]<=C['audit_per_case']for r in c.ORDER),'fixed per-role raw/audit caps')
    return q


def budget():
    sys.path.insert(0,str(c.bridge.PREP))
    return c.bridge.module(c.bridge.PREP/'budget.py','actual_borrow256_allslots_budget')


def boundary(stage,p):
    c.require(Path(stage)==c.BASE,'fixed new cohort stage')
    s=budget();state=s.check();used=sum(scan(stage).values())
    c.require(state['own_bytes']-used+c.CAPS['stage_total']<=s.OWN_CAP,'entire prospective cohort inside existing768MiB; no cleanup')
    q=phase_caps(scan(stage),stage,c.CAPS)
    prep=sum(scan(c.HERE).values())+sum(scan(c.bridge.PRIOR_HELPER).values());c.require(prep<=1024**2,'both source versions share original1MiB helper cap')
    home=s.source.budget();durable=s.source.size(s.DURABLE)
    need=home['required_free_bytes']+s.DURABLE_CAP-durable+1024**2-prep
    c.require(shutil.disk_usage(c.HERE).free>=need,'same HOME2.5GiB plus ALL old/new/CAD reservations')
    if p:
        st=Path(stage).stat();c.require(p['stage_identity']==dict(path=str(stage),device=st.st_dev,inode=st.st_ino),'unchanged actual new stage')
    return dict(resource_snapshot=state,stage_charges=q,stage_bytes=used,HOME_required_free_bytes=need)


class Ledger:
    def __init__(self,stage,p,out,sources):
        started=time.monotonic();self.stage=Path(stage);self.out=Path(out);self.p=p;self.sources=sources
        c.require(self.stage==c.BASE and self.out.parent==self.stage and self.out.name in (*c.ORDER,*(r+'-audit'for r in c.ORDER)),'explicit fixed native or audit mutable output')
        self.s=budget();self.initial=self.s.check();self.home=self.s.source.budget()
        self.roots=dict(pool=c.bridge.POOL,source=c.SOURCE,helpers=c.HERE,prior_helpers=c.bridge.PRIOR_HELPER,durable=c.bridge.DURABLE)
        self.ids={k:(p.stat().st_dev,p.stat().st_ino)for k,p in self.roots.items()}
        self.seals={k:inventory(p,self.out if k=='pool' else None)for k,p in self.roots.items()}
        self.basepool=sum(r['bytes']for r in self.seals['pool'].values())
        self.stage_rows={Path(path):row['bytes']for path,row in self.seals['pool'].items() if self.stage in Path(path).parents}
        self.prep_bytes=sum(r['bytes']for k in ('helpers','prior_helpers') for r in self.seals[k].values());self.durable_bytes=sum(r['bytes']for r in self.seals['durable'].values())
        self.next_cad=0;self.cad=None;self.entry_seconds=time.monotonic()-started
        self.out.mkdir(exist_ok=True)
        self.manifest=self.out/'sealed-inactive-inputs.json.gz'
        self.manifest.write_bytes(gzip.compress(json.dumps(dict(roots={k:str(v)for k,v in self.roots.items()},files=self.seals,sources=sources),sort_keys=True).encode(),mtime=0))
        self.check()

    def check(self):
        mutable=scan(self.out);rows=dict(self.stage_rows);rows.update(mutable)
        q=phase_caps(rows,self.stage,c.CAPS);total=self.basepool+sum(mutable.values())
        c.require(total<=self.s.OWN_CAP,'same combined768MiB original full/clone/inventory/cohort')
        if self.cad is None or time.monotonic()>=self.next_cad:
            self.cad=self.s.source.reservations.cad();self.next_cad=time.monotonic()+.25
        initial=self.initial
        need=self.s.FLOOR+self.s.OWN_CAP-total+self.s.MATCHED_CAP-initial['matched_bytes']+self.s.SCRATCH_CAP-initial['scratch_bytes']+self.s.BORROW1792_CAP-initial['borrow1792_bytes']+self.cad['remaining_work']
        c.require(shutil.disk_usage(self.stage).free>=need,'same1GiB floor plus ALL remaining old/current/CAD work allocations')
        home_need=self.home['required_free_bytes']-self.home['active_CAD']['remaining_evidence']+self.cad['remaining_evidence']+self.s.DURABLE_CAP-self.durable_bytes+1024**2-self.prep_bytes
        c.require(self.durable_bytes<=self.s.DURABLE_CAP and self.prep_bytes<=1024**2,'existing64MiB durable/new1MiB helper caps')
        c.require(shutil.disk_usage(c.HERE).free>=home_need,'same HOME2.5GiB floor plus old/new/CAD remaining allocations')
        return dict(mutable_output_bytes=sum(mutable.values()),stage_charges=q,pool_total_bytes=total,RAM_required_free_bytes=need,HOME_required_free_bytes=home_need)

    def verify_exit(self):
        started=time.monotonic()
        for key,path in self.roots.items():
            c.require((path.stat().st_dev,path.stat().st_ino)==self.ids[key],'sealed root identity changed '+key)
            c.require(inventory(path,self.out if key=='pool' else None)==self.seals[key],'sealed inactive inventory/content changed '+key)
        for row in self.sources:c.verify(row)
        report=dict(state='PASS all sealed inactive bytes/inventories unchanged',inventory=c.bind(self.manifest),entry_seconds=self.entry_seconds,exit_seconds=time.monotonic()-started,resources=self.check())
        (self.out/'sealed-exit.json').write_text(json.dumps(report,indent=2)+'\n');self.check()

    @contextmanager
    def phase(self,receipt):
        error=None
        try:
            with monitor_phase(self.check,receipt) as guard:yield guard
        except BaseException as caught:error=caught
        try:self.verify_exit()
        except BaseException as caught:
            if error is None:error=caught
        if error is not None:raise error
