#!/usr/bin/env python3
"""Prepare a new immutable admission from explicit ROOT release bytes; never launch."""
import argparse
import json
from pathlib import Path
from monitor_local import bind,check_bindings

HERE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--draft-sha256',required=True)
    ap.add_argument('--root-release',type=Path,required=True)
    ap.add_argument('--root-release-sha256',required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();draft=HERE/'admission.DRAFT.json'
    if bind(draft)['sha256']!=a.draft_sha256:raise RuntimeError('external draft SHA mismatch')
    release=bind(a.root_release.resolve())
    if release['sha256']!=a.root_release_sha256:raise RuntimeError('external ROOT release SHA mismatch')
    q=json.loads(draft.read_text())
    if q['launchable'] is not False:raise RuntimeError('original draft must remain unlaunchable')
    q.update(state='ROOT RELEASED local clean CAD admission; no launch by preparer',launchable=True)
    q['prerequisites']['root_release']=dict(ROOT_verified=True,binding=release)
    check_bindings(q)
    with a.output.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
    print(json.dumps(dict(state='PASS admission bytes only; no launch/poll',admission=bind(a.output.resolve())),indent=2))

if __name__=='__main__':main()
