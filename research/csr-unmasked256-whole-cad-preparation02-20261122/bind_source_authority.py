#!/usr/bin/env python3
"""ROOT-only metadata binding for fresh CSR FPGA source/readiness; never clone/run."""
import argparse,json
from pathlib import Path
from contracts import ART,HERE,TOP,BP,GHOST,bind,exact,require,profile,native,source_authority

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resource-profile',type=Path,required=True);p.add_argument('--resource-profile-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 r=bind(a.resource_profile);require(r['sha256']==a.resource_profile_sha256,'ROOT exact approved profile');profile(r)
 session=bind(ART/'native-proof/session.json');n=native(session);s=bind(ART/'native-proof/actual-source-list.json')
 require({k:s[k] for k in ('bytes','sha256')}=={k:n['actual_source_list'][k] for k in ('bytes','sha256')},'portable actual source-list export')
 q=dict(schema='csr256-CAD-source-authority-v1',ROOT_approved=True,TOP=TOP,BP=BP,resource_profile=r,native_session=session,actual_source_list=s,model_sha256=n['model']['sha256'],simulation_only_ghost=bind(GHOST),bindings=[bind(HERE/f) for f in ('prepare_source.py','contracts.py','software_owned_v2.py')]+[bind(Path('/home/coyang/zynq-parrot-linux-capacity/codex-skills/bp-fpga-synthesis/scripts')/f) for f in ('check_build_ready.sh','run_vivado_2024_2.sh')],scope='ROOT source/readiness only; no CAD/model/reader/board launch authority')
 with a.output.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
 source_authority(a.output)
 print(json.dumps(dict(state='PASS authority bytes only; no source preparation/CAD launched',authority=bind(a.output)),indent=2))
if __name__=='__main__':main()
