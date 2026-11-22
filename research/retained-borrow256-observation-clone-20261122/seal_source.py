#!/usr/bin/env python3
"""Freeze sources for review only; no reader/compiler/model invocation."""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'helper'))
from common import bind,require,MODEL_SHA
from bounded import PREP,OWNED
import inventory

target=HERE/'preparation-source.json'
require(not target.exists(),'fresh source-only admission')
require(bind(inventory.ARCHIVE)['sha256']==inventory.ARCHIVE_SHA,'actual closed archive')
require(bind(inventory.PAIR)['sha256']==inventory.PAIR_SHA,'actual source pair bridge')
paths=[*HERE.glob('*.py'),*sorted((HERE/'helper').glob('*.py')),inventory.PLAN,inventory.ARCHIVE,inventory.PAIR,
       inventory.TEMPLATE,inventory.TEMPLATE.parent/'admission.json',OWNED,*sorted(PREP.glob('*.py'))]
rows=[bind(p) for p in sorted(set(paths))]
value=dict(schema='borrow256-observation-preparation-source-v1',state='PREPARED ROOT review only; no compiler/native/reader has run in this phase',
           model_sha=MODEL_SHA,inputs=rows,original_inventory_session_sha='fc7d7e4cf7b3f7b36d3a1322d0811d6d52c7527934539aa9c07891c5cdd266fa',
           budget=dict(new_prep_HOME_cap=1024**2,new_RAM_subcap=256*1024**2,existing_RAM_total_cap=768*1024**2,
                       new_durable_subcap=16*1024**2,existing_durable_total_cap=64*1024**2,
                       prepare_deadline=3600,qualify_deadline=6600,teardown=5),
           qualifications_pending=['five full reference streams','untouched byte-identical relink','Syms-only archive member change','one cold08','five full literal comparisons','strict512b/eight writes/16I','independent counters','all17 actual parameters'])
with target.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
require(sum(p.stat().st_size for p in HERE.rglob('*') if p.is_file())<=1024**2,'existing1MiB preparation cap, no growth')
print(json.dumps(bind(target)))
