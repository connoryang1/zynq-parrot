#!/usr/bin/env python3
"""Snapshot exact source-list-bound configuration derivation; read-only inputs."""
import json
from pathlib import Path
import re
import shutil
from audit_geometry import HERE,OLD,NEW,bind


def main():
    result={}
    for label,base in (('old-native',OLD),('new-static',NEW)):
        entries=json.loads((base/'actual-source-list.json').read_text())
        out=HERE/label/'source';out.mkdir(exist_ok=True)
        result[label]={}
        for suffix in ('cosim/black-parrot-example/v/bp_common_pkg.sv',
                       'bp_common/src/include/bp_common_aviary_cfg_pkgdef.svh'):
            found=[r for path,r in entries.items() if path.endswith(suffix)]
            if len(found)!=1:raise ValueError('missing exact compiled cfg source')
            old=found[0];actual=bind(old['path'])
            if any(actual[k]!=old[k] for k in ('bytes','sha256')):raise ValueError('compiled cfg source changed')
            dst=out/Path(old['path']).name
            if dst.exists():
                if bind(dst)['sha256']!=actual['sha256']:raise ValueError('preserved source snapshot changed')
            else:shutil.copy2(old['path'],dst)
            result[label][dst.name]=dict(compiled_source=old,snapshot=bind(dst))
        pkg=(out/'bp_common_pkg.sv').read_text();default=(out/'bp_common_aviary_cfg_pkgdef.svh').read_text()
        if ',l2_sets             : 32' not in default or ',l2_assoc            : 2' not in default:raise ValueError('default cfg derivation changed')
        if ',l2_banks     : 1' not in pkg or not re.search(r"\{\s*l2_sets\s*:\s*64",pkg) or "'{l2_banks: 2" not in pkg:raise ValueError('named cfg derivation changed')
    target=HERE/'source-chain.json'
    if target.exists():raise ValueError('preserve source-chain proof')
    target.write_text(json.dumps(dict(state='PASS-exact-compiled-source-config-chain',sources=result,
        source=bind(__file__),geometry=bind(HERE/'geometry.json'),
        derivation='Default32sets/2ways/512b; base absentTWO_BANKS chooses1bank; oldgeneratedcustom selectsbase. Namedprefetch chooses2banks andhalvesbase32sets to16 for4KiB total; namedprefetch16k thenoverrides64sets perbank for16KiB. Actual cache-bank FSTconstants independently confirm both. Geometry-only; no effect bridge.'),indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
