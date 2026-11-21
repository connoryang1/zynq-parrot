#!/usr/bin/env python3
"""Bind geometry-only source/model/closed-container proof; no target invocation."""
import json
from pathlib import Path
import sys
from audit_geometry import HERE,ROOT,OLD,NEW,bind
sys.path.insert(0,str(ROOT/'research/retained-natural-control-20261121'))
from verify_finalized_trace import framing


def main():
    geometry=json.loads((HERE/'geometry.json').read_text())
    source=json.loads((HERE/'source-chain.json').read_text())
    if geometry['state']!='PASS-source-and-actual-FST-L2-geometry' or source['state']!='PASS-exact-compiled-source-config-chain':raise ValueError('incomplete geometry/source proof')
    inputs={};records={}
    for label,base,field,geom in (
      ('old',OLD,'executable','old_native_ef0c_and_f1_clone'),
      ('new',NEW,'model','new_static_prefetch16k')):
        session=base/'session.json';s=json.loads(session.read_text());expected=s[field];actual=bind(expected['path'])
        if any(actual[k]!=expected[k] for k in ('bytes','sha256')):raise ValueError('model changed')
        trace=geometry['results'][geom]['trace'];observed=bind(trace['path'])
        if observed!=trace:raise ValueError('closed geometry trace changed')
        inputs[label]=dict(session=bind(session),model=actual,trace=trace,framing=framing(Path(trace['path'])))
    for p in sorted(HERE.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.name not in ('final-proof.json','checkpoint-whitelist.json'):records[str(p.relative_to(HERE))]=bind(p)
    result=dict(state='PASS-CLOSED-GEOMETRY-ERRATUM',inputs=inputs,records=records,host_tests=4,
                old_L2_bytes=4096,new_L2_bytes=16384,ordinary_L1_I_bytes=32768,ordinary_L1_D_bytes=32768,
                no_target_execution=True,no_frozen_input_edits=True,
                scope='Old one-bank native effects remain conditional; no bridge to two-bank static16KiB FPGA-target configuration. Active observation-only cohort unchanged.')
    target=HERE/'final-proof.json'
    if target.exists():raise ValueError('preserve existing proof')
    target.write_text(json.dumps(result,indent=2)+'\n')
    paths=[str(p.relative_to(ROOT)) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += ['research/retained-natural-control-20261121/L2_GEOMETRY_ERRATUM.md','research/retained-native-service-20261121/L2_GEOMETRY_ERRATUM.md',str((HERE/'checkpoint-whitelist.json').relative_to(ROOT))]
    (HERE/'checkpoint-whitelist.json').write_text(json.dumps(sorted(paths),indent=2)+'\n')
    print(target,bind(target)['sha256']);print('whitelist',bind(HERE/'checkpoint-whitelist.json'))


if __name__=='__main__':main()
