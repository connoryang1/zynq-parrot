#!/usr/bin/env python3
"""Read actual Verilator/Vivado make configuration; execute no consuming target."""
import argparse
import json
from pathlib import Path
import subprocess

from run import DESIGN, ROOT, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    extra = out/'print.mk'
    extra.write_text('$(info HP0_DEFINES=$(DEFINES))\n$(info HP0_SOURCES=$(VSOURCES))\n'
                     '$(info HP0_MODEL_TAG=$(MODEL_CONFIG_TAG))\n'
                     '.PHONY: hp0_configuration_only\nhp0_configuration_only:\n\t@true\n')
    rows = []
    for tool in ('verilator','vivado'):
        for label,option,accepted in (
            ('default',[],True),('high',['BP_AXI_RESPONSE_DELAY=384'],True),
            ('negative',['BP_AXI_RESPONSE_DELAY=-1'],False),('too_high',['BP_AXI_RESPONSE_DELAY=385'],False),
            ('empty',['BP_AXI_RESPONSE_DELAY='],False),('multiple',['BP_AXI_RESPONSE_DELAY=1 2'],False),
            ('pattern',['BP_AXI_RESPONSE_DELAY=%'],False),
            ('override',['EXTRA_DEFINES=BP_AXI_RESPONSE_DELAY=40'],False)):
            command = ['make','--no-print-directory','-s','-C',str(DESIGN/tool),
                       '-f','Makefile','-f',str(extra),'hp0_configuration_only',
                       'TOOL='+tool,'CFG=e_bp_unicore_zynqparrot_prefetch_cfg',*option]
            result = subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=20)
            log = out/(tool+'-'+label+'.log'); log.write_text(result.stdout+result.stderr)
            assert (result.returncode==0)==accepted, log
            if accepted:
                defines = next(line.split('=',1)[1].split() for line in result.stdout.splitlines() if line.startswith('HP0_DEFINES='))
                selected = [d for d in defines if d.startswith('BP_AXI_RESPONSE_DELAY=')]
                assert selected==['BP_AXI_RESPONSE_DELAY='+('384' if label=='high' else '0')],selected
                sources = next(line.split('=',1)[1].split() for line in result.stdout.splitlines() if line.startswith('HP0_SOURCES='))
                for name in ('bp_axi_response_delay.sv','bp_axi_response_delay_fifo.sv','top_zynq.sv'):
                    assert str(DESIGN/'v'/name) in sources,(tool,name)
            else:
                assert 'BP_AXI_RESPONSE_DELAY' in result.stderr,log
            rows.append(dict(tool=tool,label=label,accepted=accepted,argv=command,
                             returncode=result.returncode,log=record(log)))
    manifest = dict(state='PASS 16 read-only make propagation/source-list/refusal checks; no build or Vivado invocation',
                    test=record(Path(__file__)),design=record(DESIGN/'Makefile.design'),
                    hardware=record(DESIGN/'Makefile.hardware'),cases=rows)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(manifest['state'])


if __name__=='__main__': main()
