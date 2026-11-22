#!/usr/bin/env python3
"""Promote only exact fresh CSR draft with ROOT final launch release; never launch."""
import argparse,json
from pathlib import Path
from contracts import ART,bind,require
from cad_checks import check_bindings

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--draft-sha256',required=True);ap.add_argument('--root-release',type=Path,required=True);ap.add_argument('--root-release-sha256',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 draft=ART/'admission.DRAFT.json';require(bind(draft)['sha256']==a.draft_sha256,'exact new draft')
 q=json.loads(draft.read_text());check_bindings(q,False);release=bind(a.root_release);require(release['sha256']==a.root_release_sha256,'exact ROOT final release')
 q.update(state='ROOT RELEASED clean CSR lower256 CAD admission; no launch by preparer',launchable=True);q['prerequisites']['root_release']=dict(ROOT_verified=True,binding=release)
 check_bindings(q)
 with a.output.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
 print(json.dumps(dict(state='PASS promotion bytes only; no launch',admission=bind(a.output)),indent=2))
if __name__=='__main__':main()
