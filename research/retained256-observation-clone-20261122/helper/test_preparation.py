"""Preparation contracts only; no model/compiler/reader execution."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import common as c
import host_flow as flow
import prepare_host as prep


class Preparation(unittest.TestCase):
    def test_same_three_lossless_algorithms_and_original_domains(self):
        for name in ('canonical.py','framing.py','protocol.py'):
            self.assertEqual((c.HERE/name).read_bytes(),(prep.LINEAGE/'helper'/name).read_bytes())
        p=json.loads((prep.LINEAGE/'proposal.json').read_text())
        self.assertEqual({k:len(v) for k,v in p['domains'].items()},dict(core252=252,observer_and_geometry=45,SP_strict162=162,actual_geometry16=16,capacity167=167))
        union={r['path']:r['width'] for rows in p['domains'].values() for r in rows}
        self.assertEqual(len(union),414)
        self.assertTrue(any(s.endswith('.dcache_retained_maintenance_v') for s in union))

    def test_actual_literal_validator_root_and_five_sources(self):
        p=c.SP/'testing/rtl/retained-advisory-trace/validate.py'
        spec=importlib.util.spec_from_file_location('actual256root',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        self.assertEqual(m.ROOT,c.SP)
        self.assertEqual(c.bind(p)['sha256'],'53eaca9a63bb31efa5571b6eb12279e1779339d4d3821f50488e7846f19d5d21')

    def test_model_stage_and_no_gch_copy_guard_remain(self):
        self.assertEqual(c.MODEL_SHA,'2c9d615694c0f59d9f85e6e247ba12494854378bd3b61334cf0cdaedc671e876')
        self.assertEqual(flow.STAGE.parent,prep.budget.BASE)
        self.assertEqual(c.ARTIFACT_ALLOCATION,256*1024**2)
        self.assertLess(407140015+88816+c.ARTIFACT_ALLOCATION,prep.budget.OWN_CAP)
        self.assertIn("name.endswith('.gch')",(prep.LINEAGE/'helper/prepare_host.py').read_text())
        self.assertIn("names=set(host+",Path(prep.__file__).read_text())
        self.assertNotIn("copytree(",Path(flow.__file__).read_text())

    def test_only_trace_registration_changes_and_build_algorithm_unchanged(self):
        p=json.loads((prep.LINEAGE/'proposal.json').read_text());leaves=p['writer_leaves']
        text='prefix\n        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n        __Vm_dumperp->open(file);\n'
        result,extra=flow.filtered_source(text,leaves)
        self.assertEqual(result.replace(extra,''),text);self.assertEqual(extra.count('dumpvars(1,'),414)
        def function(path,name):
            tree=ast.parse(path.read_text());return ast.dump(next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name),include_attributes=False)
        for name in ('filtered_source','members','build','loader'):
            self.assertEqual(function(Path(flow.__file__),name),function(prep.LINEAGE/'helper/host_flow.py',name))

    def test_old_admission_schema_rejected_before_any_tools(self):
        with self.assertRaisesRegex(ValueError,'wrong admission'):
            flow.validate(dict(schema='canonical1792-observation-only-host-admission-v1'))

    def test_default_preparation_and_worker_are_not_execution(self):
        with patch.object(sys,'argv',['prepare_host.py']),self.assertRaises(SystemExit) as e:prep.main()
        self.assertEqual(e.exception.code,2)
        source=Path(flow.__file__).read_text()
        self.assertNotIn('def supervise(',source)
        self.assertIn("worker must own its group",source)


if __name__=='__main__':unittest.main()
