"""Narrow extra gates for a fresh whole-CAD successor, not a replacement monitor.

Compose with the existing source/ownership/resources/7defines/clocks/route/package
gates. This module launches nothing and performs no vendor query.
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SELECTED='ExploreArea'
TOP768='1b24c915ed628f6d47a382b3aa89fb662884e1a1'
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
OPS=Path('/home/coyang/zynq-parrot-csr-opt-ops-20261122')
OPS_HEAD='cfc7fac2a2a0f693809d3a73038164aded1ed719'
SYNTH='synth_design -top black_parrot_bd_1_wrapper -part xc7z020clg400-1 -directive AreaOptimized_high -global_retiming on -control_set_opt_threshold 1'
IMPL=['opt_design -directive ExploreArea','place_design -directive Explore',
      'phys_opt_design -directive Explore','route_design -directive Explore -tns_cleanup',
      'phys_opt_design -directive Explore']


def expected_defines(top):
    require(top==TOP768,'exact new768 capacity/source profile')
    lines=768
    return dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=lines,BP_RETAINED_D_LINES=lines,
                BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)


def require(value,message):
    if not value:raise ValueError(message)


def expected_launch(source,work,logs):
    return dict(working_directory=str(source),environment=dict(
        ZP_REPO_DIR=str(source),ZP_FPGA_SEED_REPO_DIR=str(source),
        ZP_FPGA_LOG_ROOT=str(logs),ZP_FPGA_WORK_ROOT=str(work),
        FPGA_CFG='e_bp_unicore_zynqparrot_prefetch16k_cfg',FPGA_VIVADO_THREADS='8',
        FPGA_NUM_THREADS='',FPGA_NUM_CONTEXTS='',FPGA_ACLK_MHZ='20',
        FPGA_SPARSE_SOURCE='1',FPGA_CACHE_MISS_TRACE='0',FPGA_OPT_DIRECTIVE=SELECTED),
        argv=[str(OPS/'codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh'),'start'])


def check_launch(actual,source,work,logs,top,bp):
    require(top==TOP768 and bp==BP,'exact source profiles/BP')
    require(actual==expected_launch(source,work,logs),'exact new OPT/environment/launcher admission')
    return dict(selected=SELECTED,top=top,bp=bp,ops=OPS_HEAD)


def check_generated_text(revisions,config,receipt,console,synth_child,impl_child,new_xpr,baseline_xpr):
    require(revisions.splitlines().count('opt_directive='+SELECTED)==1
            and len([x for x in revisions.splitlines()if x.startswith('opt_directive=')])==1,
            'exact revisions selection')
    required='set ::env(IMPL_OPT_DIRECTIVE) {'+SELECTED+'}'
    require(config.splitlines().count(required)==1 and len(re.findall(r'(?m)^set ::env\(IMPL_OPT_DIRECTIVE\)',config))==1,
            'fresh exact generated config')
    rows=[line.split('\t')for line in receipt.splitlines()]
    require(rows and rows[0]==['selected_opt_directive',SELECTED],'actual run property receipt')
    seen=set()
    for row in rows[1:]:
        require(len(row)==3 and row[0].startswith('STEPS.')and row[0]not in seen,
                'all other step properties unique')
        require(row[0]!='STEPS.OPT_DESIGN.ARGS.DIRECTIVE'and row[1]==row[2],
                'opt-only override cannot change another property')
        seen.add(row[0])
    required_steps={f'STEPS.{name}.ARGS.DIRECTIVE'for name in
                    ('PLACE_DESIGN','PHYS_OPT_DESIGN','ROUTE_DESIGN','POST_ROUTE_PHYS_OPT_DESIGN')}
    require(required_steps<=seen,'all critical other step controls captured')
    marker='BP-IMPL-OPT-CONFIG: requested=ExploreArea actual=ExploreArea other_step_properties_unchanged=1'
    require(console.splitlines().count(marker)==1,'actual property readback marker, not requested env alone')
    syn=re.findall(r'(?m)^\s*(synth_design\s+[^\n]+?)\s*$',synth_child)
    imp=re.findall(r'(?m)^\s*((?:opt_design|place_design|phys_opt_design|route_design)\s+[^\n]+?)\s*$',impl_child)
    require(syn==[SYNTH]and imp==IMPL,'exact actual generated child commands/order')

    def implementation(raw):
        root=ET.fromstring(raw)
        runs=[x for x in root.iter('Run')if x.get('Id')=='impl_1']
        require(len(runs)==1,'one actual XPR impl run')
        strategies=runs[0].findall('Strategy');require(len(strategies)==1,'one XPR strategy')
        strategy=strategies[0];handle=strategy.find('StratHandle')
        require(handle is not None and handle.get('Name')=='Performance_ExplorePostRoutePhysOpt','unchanged implementation strategy')
        steps={}
        for step in strategy.findall('Step'):
            key=step.get('Id');require(key not in steps,'unique XPR step')
            steps[key]=(dict(step.attrib),[(dict(o.attrib),o.text or '')for o in step])
        opt=steps.pop('opt_design',None);require(opt is not None,'persisted XPR opt step')
        directives=[text.strip()for attrs,text in opt[1]if attrs.get('Id')=='Directive']
        require(len(directives)==1 and directives[0]!='','persisted XPR opt directive enum')
        return steps,opt,directives[0]
    before,old_opt,old_enum=implementation(baseline_xpr)
    after,new_opt,new_enum=implementation(new_xpr)
    require(before==after,'all other XPR implementation steps unchanged')
    require(old_opt[0]==new_opt[0]and len(old_opt[1])==len(new_opt[1]),'only opt value changes')
    for (oa,ov),(na,nv)in zip(old_opt[1],new_opt[1]):
        require(oa==na and (oa.get('Id')=='Directive'or ov==nv),'no other opt arguments changed')
    require(new_enum!=old_enum,'new selected option must persist differently from Explore baseline')
    # XPR serializes a vendor enum number. Do not invent its numerical mapping:
    # join its exact persisted delta to actual get_property and child command.
    return dict(state='PASS additional opt-only actual config/property/XPR/child gates',
                selected=SELECTED,XPR_old_enum=old_enum,XPR_new_enum=new_enum,
                XPR_enum_interpretation='opaque; joined to actual ExploreArea property readback and generated child',
                unchanged_other_step_properties=len(seen),limits='Additional gate only; all original complete-CAD gates remain mandatory')
