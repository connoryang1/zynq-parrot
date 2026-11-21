"""Read-only map/source and isolated Make parser gates; no model/board run."""
import gzip
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent


class Contract(unittest.TestCase):
    def test_compiled_header_addresses_and_unchanged_old_definitions(self):
        old=subprocess.check_output(['git','-C',str(ROOT),'show','ee031a6f:cosim/black-parrot-example/ps.hpp'],text=True)
        new=(ROOT/'cosim/black-parrot-example/ps.hpp').read_text()
        for line in old.splitlines():
            if line.startswith('#define GP0_'):self.assertIn(line,new)
        subprocess.run(['c++','-std=c++11','-fsyntax-only','-I'+str(ROOT/'cosim/black-parrot-example'),str(HERE/'map.cpp')],check=True,capture_output=True)

    def test_actual_uce_state_and_cache_abort_qualification(self):
        source=(ROOT/'import/black-parrot/bp_me/src/v/cce/bp_uce.sv').read_text()
        states=re.search(r'enum logic \[4:0\] \{([^}]+)\} state_n, state_r;',source,re.S).group(1)
        names=[word.strip() for word in states.split(',')]
        self.assertEqual(names.index('e_retained_fill'),22)
        top=(ROOT/'cosim/black-parrot-example/v/top_zynq.sv').read_text()
        self.assertIn('& ~`OBS_I.abort_inflight',top)
        self.assertIn('& (|`OBS_I.data_mem_slow_write)',top)
        self.assertIn('& (|`OBS_D.data_mem_slow_write)',top)
        self.assertIn('retained_insert_published & `OBS_U.retained_insert_done',top)
        self.assertIn('.clk_i({~aclk,aclk}), .reset_i(~aresetn), .bp_reset_i(bp_reset_li)',top)
        self.assertIn('retained_observe_lp ? 10 : 8',top)

    def test_canonical_flags_default_off_and_model_identity(self):
        recipe=ROOT/'research/hp0-response-path-20261121/full-system-delay200-10/source-before.json.gz'
        prefix=json.loads(gzip.decompress(recipe.read_bytes()))['command_prefix']
        prefix=[arg.replace('/home/coyang/zynq-parrot-linux-capacity',str(ROOT)) for arg in prefix]
        with tempfile.TemporaryDirectory(prefix='retained-observe-make-',dir='/home/coyang') as temp:
            parent=Path(temp);(parent/'Makefile.design').symlink_to(ROOT/'cosim/black-parrot-example/Makefile.design')
            cwd=parent/'verilator';cwd.mkdir()
            probe=['--eval','observe-print:;@echo "FLAG=$(BP_RETAINED_OBSERVE) TAG=$(MODEL_CONFIG_TAG)"','observe-print']
            for value in (None,'0','1','2','','0 1'):
                command=prefix+([] if value is None else ['BP_RETAINED_OBSERVE='+value])+probe
                result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
                if value in (None,'0','1'):
                    self.assertEqual(result.returncode,0,result.stderr)
                    flag='1' if value=='1' else '0'
                    self.assertIn('FLAG='+flag,result.stdout);self.assertIn('-BP_RETAINED_OBSERVE_'+flag,result.stdout)
                else:self.assertNotEqual(result.returncode,0)
            result=subprocess.run(prefix+['EXTRA_DEFINES=BP_RETAINED_OBSERVE=1']+probe,cwd=cwd,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
