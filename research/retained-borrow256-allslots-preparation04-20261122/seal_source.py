#!/usr/bin/env python3
"""Freeze monitoring-only new sources; no target, FST reader or vendor action."""
import json
from pathlib import Path
import contract as c
import fixed_shared as fixed

path=c.HERE/'source-plan.json';c.require(not path.exists(),'fresh monitoring-only source admission')
versions=[]
for root,sha,state in zip(c.bridge.PREVIOUS_HELPERS,('3ecd48a7f6c7163c2c92e5ec88ead1133d9c68c5ce03db60e407da4dc2b083a5','9d9c789692754c598578ade6cac946f2a95ae5980bfe83672b38cd9e10f17f24','87c37c7fd2b57bb546409eb0873396da1b068bd1c776f360de6c0b48be3d8ac0'),('UNEXECUTED','EXECUTED native monitoring failure; no complete target result','EXECUTED HOME reservation failure; no complete target result')):
    row=c.bind(root/'source-plan.json');c.require(row['sha256']==sha,'previous source admission unchanged')
    for record in json.loads((root/'source-plan.json').read_text())['sources']:c.verify(record)
    versions.append(dict(admission=row,state=state))
value=dict(schema='borrow256-allslots-source-admission-v1',state='PREPARED fresh paths/latest failure provenance only; ROOT execution required',
           sources=c.runtime_sources(),previous_versions=versions,model_sha256=c.bridge.MODEL_SHA,program_ELF_sha256='062a3dd884d64bc1fdf7f0048f312cc5efc84280eb89006c21ef6b60f1f43ed6',
           resource_policy=c.bind(fixed.POLICY),archive_deferral=c.bind(fixed.NOTE),new_stage=str(c.BASE),
           schedule=list(c.ORDER),caps=c.caps(256*1024**2),tests_passed=16,
           unchanged='model/program/copies/semanticValidator/full167/independent counters/EOF/0.5s scan/1s heartbeat/time/phase caps',
           correction='only fresh helper/cohort paths and latest HOME-failure/ROOT cache-relocation provenance; all monitoring/model/program/cap policies identical to03')
with path.open('x')as stream:json.dump(value,stream,indent=2);stream.write('\n')
c.require(sum(p.stat().st_size for root in (c.HERE,*c.bridge.PREVIOUS_HELPERS)for p in root.rglob('*')if p.is_file())<=1024**2,'all source versions share original1MiB cap')
print(json.dumps(c.bind(path),sort_keys=True))
