#!/usr/bin/env python3
"""Write only an unlaunchable software/schema draft; never select or run a model."""
from pathlib import Path
import json
import contract as c


def main():
    prior=json.loads((c.OLD/'preparation.DRAFT.json').read_text())
    p=dict(schema='retained1792-stream-cohort-v1',state='DRAFT UNLAUNCHABLE model/canonical-gate/host-admission pending',
        schedule=list(c.ORDER),geometry=c.GEOMETRY,caps=c.CAPS,program=prior['program'],reader=prior['reader'],
        runtime_sources=c.runtime_sources(),environment=prior['environment'],linked_libraries=prior['linked_libraries'],
        model=None,model_approval=None,canonical_fullcore=None,observation_qualification=None,
        compiled_sources=None,model_stamp=None,host_admission=None,stage=None)
    path=c.HERE/'preparation.DRAFT.json'
    c.require(not path.exists(),'new draft only; preserve prior preparation')
    c.archive.write_json(path,p)
    c.load(path,c.bind(path)['sha256'],approved=False)
    print(c.bind(path))


if __name__=='__main__':main()
