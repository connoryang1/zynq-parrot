"""Host-only Make/Tcl configuration gates. No model, vendor or board tools."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
DESIGN=ROOT/'cosim/black-parrot-example/Makefile.design'
VERILATOR=ROOT/'cosim/mk/Makefile.verilator'
VIVADO=ROOT/'cosim/mk/Makefile.vivado'
TCL=ROOT/'cosim/tcl/vivado-utils.tcl'

def defaults():
    text=DESIGN.read_text()
    return {name:re.search(r'^'+name+r'\s*\?=\s*(\d+)\s*$',text,re.M)[1]
            for name in ('BP_RETAINED_BUFFER','BP_RETAINED_I_LINES','BP_RETAINED_D_LINES','BP_RETAINED_SETS')}


def environment():return {k:v for k,v in os.environ.items() if not k.startswith('BP_') and k not in ('EXTRA_DEFINES','MAKEFLAGS','MFLAGS','MAKEOVERRIDES')}


def make_fixture(path):
    (path/'mk').mkdir();(path/'tcl').mkdir()
    for name in ('Makefile.common','Makefile.env'):(path/name).write_text('')
    for name in ('Makefile.master','Makefile.sim'):(path/'mk'/name).write_text('')
    (path/'tcl/vivado-utils.tcl').symlink_to(TCL)
    (path/'tcl/bsg-utils.tcl').write_text('# Test-only no-op utility; no vendor commands.\n')
    (path/'Makefile').write_text('TOP := '+str(path)+'\nCOSIM_MK_DIR := '+str(path/'mk')+'\nCOSIM_TCL_DIR := '+str(path/'tcl')+'\nECHO := echo\n'
        'include '+str(DESIGN)+'\ninclude '+str(VERILATOR)+'\ninclude '+str(VIVADO)+'\n'
        '.PHONY: show\nshow:\n\t@printf "%s\\n" "$(DEFINES)" "$(MODEL_CONFIG_STAMP)"\n')


MOCK='''
array set definitions {}
set context source_ip
set lose 0
proc current_project {} { return $::context }
proc get_filesets {name} { return $::context }
proc get_property {name object} { return $::definitions($object) }
proc set_property {name value object} {
    if {$::lose} { set value [lsearch -all -inline -not -glob $value BP_CACHE_MISS_TRACE=*] }
    set ::definitions($object) $value
}
'''


def tcl(program,env=None):
    # tclsh stdin does not reliably return nonzero for an uncaught Tcl error.
    wrapped='if {[catch {\n'+program+'\n} error]} {puts stderr $error; exit 1}\n'
    return subprocess.run(['tclsh'],input=wrapped,text=True,capture_output=True,env=env or environment(),timeout=10)


class Profile(unittest.TestCase):
    def make(self,args=()):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);make_fixture(p)
            result=subprocess.run(['make','--no-print-directory','show',*args],cwd=p,text=True,capture_output=True,env=environment(),timeout=10)
        return result

    def test_default_on_off_and_stamp_identity(self):
        default=self.make();on=self.make(['BP_CACHE_MISS_TRACE=1']);off=self.make(['BP_CACHE_MISS_TRACE=0'])
        for result in (default,on,off):self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(default.stdout,on.stdout)
        self.assertIn('BP_CACHE_MISS_TRACE=1',on.stdout);self.assertIn('-miss-trace1',on.stdout)
        self.assertIn('BP_CACHE_MISS_TRACE=0',off.stdout);self.assertIn('-miss-trace0',off.stdout)
        self.assertNotEqual(on.stdout.splitlines()[-1],off.stdout.splitlines()[-1])
        for result in (on,off):
            for key,value in defaults().items():self.assertIn(key+'='+value,result.stdout)

    def test_invalid_and_extra_defines_refused(self):
        for value in ('','2','-1','01','true','1 0'):
            with self.subTest(value=value):self.assertNotEqual(self.make(['BP_CACHE_MISS_TRACE='+value]).returncode,0)
        for value in ('BP_CACHE_MISS_TRACE','BP_CACHE_MISS_TRACE=0','BP_CACHE_MISS_TRACE=1'):
            result=self.make(['EXTRA_DEFINES='+value]);self.assertNotEqual(result.returncode,0);self.assertIn('instead of an EXTRA_DEFINES override',result.stderr)

    def test_actual_generated_tcl_carries_seventh_define_in_three_fresh_contexts(self):
        for setting in (0,1):
            with self.subTest(setting=setting),tempfile.TemporaryDirectory() as td:
                p=Path(td);make_fixture(p)
                observe=('BP_RETAINED_OBSERVE=1' if re.search(r'^BP_RETAINED_OBSERVE\s*\?=',DESIGN.read_text(),re.M)
                         else 'EXTRA_DEFINES=BP_RETAINED_OBSERVE=1')
                result=subprocess.run(['make','--no-print-directory','config.tcl','vivado.tcl','BP_CACHE_MISS_TRACE='+str(setting),observe],cwd=p,text=True,capture_output=True,env=environment(),timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                generated=(p/'vivado.tcl').read_text();self.assertIn('set ::env(BP_CACHE_MISS_TRACE) '+str(setting),generated)
                program=MOCK+'\nsource '+str(p/'vivado.tcl')+'\n'
                program+='foreach context {source_ip final_bd edited_ip} {\nset definitions($context) {EXISTING=1}\nvivado_apply_experiment_defines\n'
                program+='if {"BP_CACHE_MISS_TRACE='+str(setting)+'" ni $definitions($context)} {error "lost seventh define"}\n'
                required=' '.join(key+'='+value for key,value in defaults().items())+' BP_RETAINED_OBSERVE=1 BP_AXI_RESPONSE_DELAY=0 EXISTING=1'
                program+='foreach required {'+required+'} {if {$required ni $definitions($context)} {error "lost $required"}}\n'
                program+='if {[llength $definitions($context)]!=8} {error "expected all seven defines plus preserved existing entry"}\n}\n'
                program+='foreach caller {vivado_create_design vivado_create_ip_proj vivado_customize_ip} {if {[string first vivado_apply_experiment_defines [info body $caller]]<0} {error "missing fresh-context caller $caller"}}\n'
                run=tcl(program);self.assertEqual(run.returncode,0,run.stderr)
                self.assertEqual(run.stdout.count('BP-EXPERIMENT-CONFIG:'),3)

    def test_tcl_boolean_conflict_and_readback_loss_fail_closed(self):
        for value in ('2','01','-1',''):
            run=tcl('source '+str(TCL)+'\nset ::env(BP_CACHE_MISS_TRACE) '+json.dumps(value)+'\nvivado_experiment_defines')
            self.assertNotEqual(run.returncode,0,(value,run.stdout,run.stderr))
        base=MOCK+'\nsource '+str(TCL)+'\nset ::env(BP_CACHE_MISS_TRACE) 0\n'
        run=tcl(base+'set definitions(source_ip) {BP_CACHE_MISS_TRACE=1}\nvivado_apply_experiment_defines')
        self.assertNotEqual(run.returncode,0);self.assertIn('conflicting Verilog define',run.stderr)
        run=tcl(base+'set definitions(source_ip) {}\nset lose 1\nvivado_apply_experiment_defines')
        self.assertNotEqual(run.returncode,0);self.assertIn('lost requested Verilog define',run.stderr)

    def test_top_default_and_existing_generic_feature_are_preserved(self):
        source=(ROOT/'cosim/black-parrot-example/v/top_zynq.sv').read_text()
        self.assertIn('`ifndef BP_CACHE_MISS_TRACE\n`define BP_CACHE_MISS_TRACE 1\n`endif',source)
        self.assertEqual(source.count('.cache_miss_trace_p(`BP_CACHE_MISS_TRACE)'),1)
        self.assertNotIn('.cache_miss_trace_p(1\'b1)',source)


if __name__=='__main__':unittest.main()
