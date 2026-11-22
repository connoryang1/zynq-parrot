#!/usr/bin/env python3
"""ROOT data-only immutable promotion; no CAD invocation."""
import argparse,json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;D=HERE/'admission.DRAFT.json';F=HERE/'admission.FINAL.json'
def need(v,m):
 if not v:raise ValueError(m)
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def main():
 p=argparse.ArgumentParser();p.add_argument('--expected-draft-sha256',required=True);p.add_argument('--root-terminal-release',type=Path,required=True);p.add_argument('--resource-profile',type=Path,required=True);x=p.parse_args()
 db=bind(D);need(db['sha256']==x.expected_draft_sha256,'draft mismatch');a=json.loads(D.read_text());need(not a['launchable'],'draft only')
 for r in a['inputs']:need(bind(r['path'])==r,'input drift')
 release=json.loads(x.root_terminal_release.read_text());need(release.get('allow_component_packing') is True and release.get('prior_mapping05_terminal_sha256')=='2ed7df458f1be2da9033a41da2d0a294047f56054b0b9183ac8d73bfd4020a85','ROOT terminal/release needed')
 profile=json.loads(x.resource_profile.read_text());need(profile.get('schema')=='csr-component-packing-resource-v1' and profile.get('all_other_charged_reserves_included') is True and len(profile.get('basis_records',[]))>0,'global resource profile needed')
 for r in profile['basis_records']:need(bind(r['path'])==r,'resource basis drift')
 for k in ['other_HOME_bytes','other_RUN_bytes','other_SHM_bytes']:need(type(profile[k]) is int and profile[k]>=0,'explicit nonnegative other charges')
 a.update(launchable=True,ROOT_terminal_release=bind(x.root_terminal_release),resource_profile=bind(x.resource_profile),immutable_draft=db)
 with F.open('x') as out:out.write(json.dumps(a,indent=2)+'\n')
 need(bind(D)==db,'draft drift');print(json.dumps(bind(F),indent=2))
if __name__=='__main__':main()
