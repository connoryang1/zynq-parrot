#!/usr/bin/env python3
"""Create immutable FINAL admission after ROOT terminal/resource review; no vendor."""
import argparse,hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
D=HERE/'admission.DRAFT.json';F=HERE/'admission.FINAL.json'
def bind(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def need(ok,msg):
 if not ok:raise ValueError(msg)
def main():
 p=argparse.ArgumentParser();p.add_argument('--root-terminal-release',type=Path,required=True);p.add_argument('--expected-draft-sha256',required=True);args=p.parse_args()
 before=bind(D);need(before['sha256']==args.expected_draft_sha256,'draft mismatch')
 a=json.loads(D.read_text());need(not a['launchable'] and a['ROOT_terminal_release'] is None,'draft must remain unlaunchable')
 for r in a['inputs']:need(bind(r['path'])==r,'frozen input drift')
 release=json.loads(args.root_terminal_release.read_text())
 need(release.get('current_CAD_job')=='20261122T084853Z-1008854d3' and release.get('terminal_verified') is True and release.get('allow_component_mapping') is True,'ROOT terminal/resource admission needed')
 a['ROOT_terminal_release']=bind(args.root_terminal_release);a['launchable']=True;a['immutable_draft']=before
 with F.open('x') as out:out.write(json.dumps(a,indent=2)+'\n')
 need(bind(D)==before,'draft changed')
 print(json.dumps(bind(F),indent=2))
if __name__=='__main__':main()
