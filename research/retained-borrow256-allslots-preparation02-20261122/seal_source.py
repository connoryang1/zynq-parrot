#!/usr/bin/env python3
"""Freeze exact new/foundation sources only; no model/reader/compiler invocation."""
import json
from pathlib import Path
import contract as c

path=c.HERE/'source-plan.json'
c.require(not path.exists(),'fresh immutable source admission')
previous=c.bridge.PRIOR_HELPER/'source-plan.json'
c.require(c.bind(previous)['sha256']=='3ecd48a7f6c7163c2c92e5ec88ead1133d9c68c5ce03db60e407da4dc2b083a5','preserve prior unexecuted source admission')
for row in json.loads(previous.read_text())['sources']:c.verify(row)
value=dict(schema='borrow256-allslots-source-admission-v1',state='PREPARED ROOT review only; no native/reader/model run by agent',
           previous_unexecuted=dict(admission=c.bind(previous),commit='a1b7c162b',scope='source-only followup: actual reader bytes verified; no prior cohort prepare/native/audit was run'),
           sources=c.runtime_sources(),preflight_sha256='ca5878f852d05ac4941c9571f0401071f619d0abc4a2dd3d2af6bcb4c82bfe81',
           actual_model_sha256=c.bridge.MODEL_SHA,semantic_Validator_is_exact_prior256=True,
           accepted_RO04_monitor_source=c.bind(c.HERE/'process_monitor.py'),
           schedule=list(c.ORDER),prospective_caps=c.caps(256*1024**2),tests_passed=11)
with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
c.require(sum(p.stat().st_size for root in (c.HERE,c.bridge.PRIOR_HELPER) for p in root.rglob('*') if p.is_file())<=1024**2,'both versions share original1MiB prep cap')
print(json.dumps(c.bind(path),sort_keys=True))
