#!/usr/bin/env python3
"""Read-only complete SP source/object/loader freeze. Never executes model or compiler."""
import hashlib
import json
from pathlib import Path
import os
import subprocess
from common import *


def main():
    target=HERE/'source-freeze.json';require(not target.exists(),'preserve source freeze')
    p,n=reviewed();obj=Path(n['original_generated_root'])
    for r in (n['model'],n['Syms'],n['archive'],n['build_log'],n['PCH_text_header'],*n['seven_host_objects'].values()):verify(r)
    records=json.loads((ORIGINAL/'actual-source-list.json').read_text());records=records.get('sources',records)
    compiled={}
    for name,record in records.items():
        actual=bind(name);require(all(actual[k]==record[k] for k in ('bytes','sha256')),'compiled SP source changed: '+name)
        compiled[name]=actual
    archive=Path(n['archive']['path']);names=subprocess.check_output(['ar','t',str(archive)],text=True).splitlines()
    require(len(names)==len(set(names)),'duplicate archive members')
    members={name:hashlib.sha256(subprocess.check_output(['ar','p',str(archive),name])).hexdigest() for name in names}
    session=json.loads((ORIGINAL/'session.json').read_text());env=dict(os.environ);env.update(session['environment'])
    linked=subprocess.run(['ldd',n['model']['path']],env=env,capture_output=True,text=True,timeout=10)
    require(linked.returncode==0 and 'not found' not in linked.stdout,'original loader preflight failed')
    (HERE/'original-loader.log').write_text(linked.stdout);libraries=[]
    for line in linked.stdout.splitlines():
        for word in line.split():
            if word.startswith('/') and Path(word).is_file():libraries.append(bind(word))
    runtime=Path('/home/coyang/zynq-parrot/install/share/verilator/include')
    stamp=session['model_stamp'];verify({k:stamp[k] for k in ('path','bytes','sha256')})
    inventory=tree(obj);require(sum(r['bytes'] for r in inventory.values())==n['copy_bytes_without_gch'],'original inventory size differs')
    save(target,dict(state='FROZEN-original-SP-no-build-or-target-execution',model=n['model'],
        proposal=bind(PROPOSAL),native_identities=bind(NATIVE),source=bind(__file__),helper=bind(HERE/'common.py'),
        original_generated_files=inventory,archive_member_sha256=members,compiled_sources=compiled,
        reviewed_runtime={x:bind(runtime/x) for x in ('verilated_fst_c.h','verilated_fst_c.cpp','verilated_trace_imp.h')},
        model_stamp={k:stamp[k] for k in ('path','bytes','sha256')},environment=session['environment'],
        loader=bind(HERE/'original-loader.log'),linked_libraries=libraries,session=bind(ORIGINAL/'session.json')))
    print(target,bind(target)['sha256'])


if __name__=='__main__':main()
