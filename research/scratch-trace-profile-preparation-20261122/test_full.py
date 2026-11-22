"""Host preparation/guards/parameter fixtures only; no compiler/model/reader."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import run_full as r
import geometry

SELECTION=r.HERE/'selection1792.json'


class FullPreparation(unittest.TestCase):
    def test_exact_actual_source_and_qualified_software_selection(self):
        a=r.validate_selection(SELECTION,r.bind(SELECTION)['sha256'])
        self.assertEqual(a['lines'],1792);self.assertEqual(a['trace'],0)
        self.assertEqual(a['BP'],'7566c67aad9b93f5546fcc5e258e405402a47850')
        self.assertIn('NOT selected maximum',a['scope'])

    def test_draft_wrong_sha_wrong_bp_and_profile_rejected(self):
        with self.assertRaisesRegex(ValueError,'external ROOT'):r.validate_selection(SELECTION,'0'*64)
        original=json.loads(SELECTION.read_text())
        for key,value in [('state','DRAFT'),('BP','0'*40),('trace',1),('workers',9),('lines',256)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as td:
                q=copy.deepcopy(original);q[key]=value;p=Path(td)/'selection.json';p.write_text(json.dumps(q))
                with self.assertRaises(ValueError):r.validate_selection(p,r.bind(p)['sha256'])

    def stream(self,wrong=None):
        expected,widths=geometry.expected(1792);records=['#FST\t0\t10\t-12\n']
        for i,key in enumerate(expected,1):records.append('#SIGNAL\t%s\t%d\t%d\tTOP.unicore_lite.%s\n'%(key,widths[key],i,key))
        for i,(key,value) in enumerate(expected.items(),1):
            if wrong and key==wrong[0]:value=wrong[1]
            records.append('0\t%d\t%s\n'%(i,format(value,'0%db'%widths[key])))
        return records+['#END\n']

    def test_all16_geometry_plus_actual_trace_parameter_zero(self):
        values=geometry.parse(iter(self.stream()),1792)['values']
        self.assertEqual(len(values),17);self.assertEqual(values['core_minimal.cache_miss_trace_p'],0)
        for wrong in [('core_minimal.cache_miss_trace_p',1),('l2_banks_p',1),('retained_store.storage.i_lines_p',256)]:
            with self.subTest(wrong=wrong),self.assertRaises(ValueError):geometry.parse(iter(self.stream(wrong)),1792)
        with self.assertRaisesRegex(ValueError,'all17'):geometry.parse(iter(self.stream()[:-1]),1792)

    def test_prepare_only_and_actual_trace0_command_no_forced_capacity(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/'stage'
            with patch.object(r.budget,'BASE',base),patch.object(r.budget,'check',return_value={}),patch.object(r.owned,'run',side_effect=AssertionError('no tools')), \
                 patch.object(sys,'argv',['test','--selection',str(SELECTION),'--selection-sha256',r.bind(SELECTION)['sha256'],'--prepare-only']):
                r.main()
            p=json.loads((base/'prepared01.json').read_text());command=p['command']
            self.assertIn('BP_CACHE_MISS_TRACE=0',command);self.assertIn('VERILATOR_BUILD_JOBS=8',command);self.assertIn('OBJCACHE=',command)
            self.assertFalse(any(arg.startswith(('BP_RETAINED_I_LINES=','BP_RETAINED_D_LINES=','NUM_THREADS=')) for arg in command))

    def test_prelaunch_owned_failure_always_persists_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/'stage';argv=['test','--selection',str(SELECTION),'--selection-sha256',r.bind(SELECTION)['sha256']]
            with patch.object(r.budget,'BASE',base),patch.object(r.budget,'check',return_value={}):
                with patch.object(sys,'argv',argv+['--prepare-only']):r.main()
                error=RuntimeError('synthetic prelaunch guard');error.owned_receipt=dict(returncode=None,failure=repr(error),owned_pgid=None,owned_group_remaining=False)
                with patch.object(r.owned,'run',side_effect=error),patch.object(sys,'argv',argv+['--execute','--prepared-sha256',r.bind(base/'prepared01.json')['sha256']]),self.assertRaisesRegex(RuntimeError,'synthetic prelaunch'):
                    r.main()
            q=json.loads((base/'full01/session.json').read_text());self.assertEqual(q['state'],'FAIL preserved, no accepted result')
            self.assertEqual([x['label'] for x in q['commands']],['make-preflight'])
            self.assertEqual(json.loads((base/'full01/make-preflight-owned.json').read_text()),error.owned_receipt)


if __name__=='__main__':unittest.main()
