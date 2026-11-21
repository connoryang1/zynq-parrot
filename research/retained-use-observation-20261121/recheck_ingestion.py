#!/usr/bin/env python3
"""Correct the closed full01 verifier's ctime/mtime ordering, without rebuilding."""
import argparse
import json
from pathlib import Path
import re

from build_full import ROOT,binding,write


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build',type=Path,required=True)
    args=parser.parse_args();build=args.build.resolve()
    if (build/'build-accepted.json').exists():raise ValueError('new verification files only')
    previous=json.loads((build/'status.json').read_text())
    if previous['state']!='FAIL no runtime eligible' or previous['error']!="ValueError('source ingestion metadata differs: /home/coyang/zynq-parrot/install/bin/verilator_bin')":
        raise ValueError('not the exact known source-checker rejection')
    before=json.loads((build/'source-before.json').read_text())
    for path,record in before['source'].items():
        if binding(path)!=record:raise ValueError('critical source changed: '+path)
    metadata=build/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench__verFiles.dat';sources={}
    for line in metadata.read_text().splitlines():
        match=re.fullmatch(r'S\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"([^"]+)"',line)
        if not match:continue
        size,inode,ctime,cnsec,mtime,mnsec=map(int,match.groups()[:6]);path=Path(match[7]);record=binding(path)
        if (record['bytes'],record['inode'],record['ctime_ns'],record['mtime_ns'])!=(size,inode,ctime*10**9+cnsec,mtime*10**9+mnsec):
            raise ValueError('actual input metadata differs: '+str(path))
        sources[str(path)]=record
    for key in ('cosim/black-parrot-example/v/top_zynq.sv','cosim/v/bp_retained_use_counters.sv','import/black-parrot/bp_me/src/v/cce/bp_uce.sv'):
        if str(ROOT/key) not in sources:raise ValueError('owned source absent')
    # subprocess.run(check=True) reached the exact metadata exception only after
    # both clean and build returned0. Retain original status; do not hide it.
    log=(build/'build.log').read_text()
    if '- Verilator: Walltime ' not in log or not re.search(r' -o Vbsg_nonsynth_zynq_testbench(?:\s|$)',log):
        raise ValueError('missing successful compile/link completion')
    stamps=list((build/'verilator/obj_dir').glob('.build_config-*'))
    required=('-BP_RETAINED_OBSERVE_1','-BP_AXI_RESPONSE_DELAY_0','-BP_RETAINED_I_LINES_64','-BP_RETAINED_D_LINES_64','-BP_RETAINED_SETS_64')
    if len(stamps)!=1 or not all(value in stamps[0].name for value in required):raise ValueError('wrong actual model stamp')
    write(build/'actual-source-list.json',dict(sources=sources,metadata=binding(metadata)))
    write(build/'build-accepted.json',dict(state='PASS clean actual-fulltop build; runtime pending',
        model=binding(build/'verilator/obj_dir/Vbsg_nonsynth_zynq_testbench'),actual_sources=binding(build/'actual-source-list.json'),
        prior_rejected_verification=binding(build/'status.json'),source_before=binding(build/'source-before.json'),
        build_log=binding(build/'build.log'),clean_log=binding(build/'clean.log'),auditor=binding(__file__),
        model_stamp=binding(stamps[0]),
        correction='verFiles S fields are size inode ctime_sec ctime_nsec mtime_sec mtime_nsec; original checker reversed the timestamps',
        scoped_assertions='same maintained BSG guard as root10; not global assertion acceptance'))
    print(build/'build-accepted.json')


if __name__=='__main__':main()
