"""Pure metadata/closed-script fixtures only; no shell launcher/network/tools."""
import copy
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import identity
import monitor_local as monitor

HERE=Path(__file__).resolve().parent
EXPECTED=json.loads((HERE/'admission.DRAFT.json').read_text())['configuration']['expected_defines']


class Identity(unittest.TestCase):
    def contexts(self,expected=EXPECTED):
        values=' '.join(k+'='+str(v) for k,v in expected.items())
        return '\n'.join('BP-EXPERIMENT-CONFIG: project='+p+' effective='+values for p in identity.PROJECTS)

    def test_all_seven_actual_fields_in_all_three_contexts(self):
        self.assertTrue(identity.contexts(self.contexts(),EXPECTED)['valid'])
        for text in [self.contexts().replace(' BP_CACHE_MISS_TRACE=0',''),self.contexts().replace('BP_CACHE_MISS_TRACE=0','BP_CACHE_MISS_TRACE=1'),self.contexts().splitlines()[0]]:
            self.assertFalse(identity.contexts(text,EXPECTED)['valid'])
        self.assertEqual(identity.actual_defines('BP_CACHE_MISS_TRACE=0.0',EXPECTED)['BP_CACHE_MISS_TRACE'],[])
        self.assertFalse(identity.contexts('# '+self.contexts().replace('\n','\n# '),EXPECTED)['valid'])

    def test_actual_old_R7_six_field_child_is_insufficient(self):
        p=Path('/home/coyang/fpga-artifacts/context-resume/native1792-canonical-r7-preparation-20261121/closed-terminal01/014-black_parrot_bd_1_wrapper.tcl.gz')
        text=gzip.decompress(p.read_bytes()).decode()
        actual=identity.actual_defines(text,EXPECTED)
        self.assertEqual(actual['BP_CACHE_MISS_TRACE'],[])
        self.assertTrue(identity.clean_script(text))
        self.assertFalse(identity.clean_script(text+'\nread_checkpoint -incremental /HOST_TEST_ONLY/seed.dcp\n'))

    def test_physical_requested_core_and_timer_independently_required(self):
        def xci(core,timer):return json.dumps({'CLKOUT1_REQUESTED_OUT_FREQ':[{'value':core}],'CLKOUT2_REQUESTED_OUT_FREQ':[{'value':timer}]})
        self.assertTrue(identity.clock_match(xci('20.000','8'))['valid'])
        self.assertFalse(identity.clock_match(xci('20','1'))['valid'])
        self.assertFalse(identity.clock_match(xci('50','8'))['valid'])
        self.assertFalse(identity.clock_match('"FREQ_HZ": 8000000')['valid'])

    def test_draft_and_missing_prerequisites_refuse_before_ssh(self):
        path=HERE/'admission.DRAFT.json';sha=monitor.bind(path)['sha256']
        with patch.object(sys,'argv',['monitor','--admission',str(path),'--admission-sha256',sha,'--job','20261122T000000Z-3daedee66','--preflight']),patch.object(monitor,'poll',side_effect=AssertionError('no network')):
            with self.assertRaisesRegex(RuntimeError,'UNLAUNCHABLE'):monitor.main()
        q=json.loads(path.read_text());q['launchable']=True
        with self.assertRaisesRegex(RuntimeError,'missing ROOT verified prerequisite'):monitor.check_bindings(q)

    def test_foreign_guard_includes_real_launcher_basenames(self):
        for token in ('/ROOT_TEST_ONLY/launch_synthesis.sh','/ROOT_TEST_ONLY/run_vivado_2024_2.sh','/ROOT_TEST_ONLY/xelab'):
            self.assertTrue(identity.vendor_process(dict(comm='bash',state='S',argv_tokens=['bash',token])))
        self.assertTrue(identity.vendor_process(dict(comm='vivado',state='R',argv_tokens=[])))
        self.assertFalse(identity.vendor_process(dict(comm='python3',state='S',argv_tokens=['python3','monitor_local.py'])))
        self.assertFalse(identity.vendor_process(dict(comm='vivado',state='Z',argv_tokens=[])))

    def test_clean_mode_does_not_confuse_OOC_IP_with_incremental_seed(self):
        self.assertTrue(identity.clean_script('read_checkpoint -cell ip /HOST_TEST_ONLY/ip.dcp\nset_property incremental_checkpoint {} [get_runs synth_1]\n'))
        self.assertFalse(identity.clean_script('set_property incremental_checkpoint /HOST_TEST_ONLY/old.dcp [get_runs synth_1]'))


if __name__=='__main__':unittest.main()
