"""Small host-only preparation checks; no ROOT RAM/model/reader operations."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import prepare_root as p

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'retained1792-stream-cohort-20261121'))
import contract as c


class Prepare(unittest.TestCase):
    def setUp(self):
        self.facts=json.loads((HERE/'candidate.json').read_text())
        self.review=json.loads((HERE/'model-review.DRAFT.json').read_text())
    def test_exact_newcanonical_model_and_unchanged_software_bound(self):
        self.assertEqual(self.facts['model']['sha256'],p.MODEL_SHA)
        self.assertEqual(self.facts['model']['bytes'],15945696)
        rows=json.loads(Path(self.facts['compiled_sources']['path']).read_text())['sources']
        self.assertGreater(len(rows),100)
        self.assertTrue(all(set(r)=={'path','bytes','sha256'} for r in rows.values()))
        self.assertEqual(c.GEOMETRY['i_lines'],1792)
        self.assertEqual(c.CAPS['stage_total'],512*1024**2)
    def test_pending_or_redirected_review_never_approves(self):
        path=HERE/'model-review.DRAFT.json'
        with self.assertRaisesRegex(ValueError,'pending'):p.reviewed_packet(path,p.bind(path)['sha256'],self.facts,c)
        with self.assertRaisesRegex(ValueError,'external review'):p.reviewed_packet(path,'0'*64,self.facts,c)
    def test_preserved_fail_or_awaiting_checker_not_final_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);review=copy.deepcopy(self.review)
            review['state']='ROOT-REVIEWED closed canonical gate plus observation clone';review['checks']=dict.fromkeys(c.MODEL_CHECKS,True)
            for state in ('FAIL-preserved-no-retry','COMPLETE-cold08-awaiting-five-domain-and-maintained-checkers'):
                proof=root/'proof.json';proof.write_text(json.dumps({'state':state}))
                review['observation_qualification']=p.bind(proof)
                path=root/'review.json';path.write_text(json.dumps(review))
                with self.assertRaisesRegex(ValueError,'must be PASS'):p.reviewed_packet(path,p.bind(path)['sha256'],self.facts,c)
    def test_wrong_namespace_rejected_without_stage_creation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);facts=copy.deepcopy(self.facts);facts['namespace_sentinel']=str(root)
            facts['namespace_identity']={'device':-1,'inode':-1}
            with patch.object(p,'STAGE',root/'newstage'):
                with self.assertRaisesRegex(ValueError,'namespace identity'):p.namespace_and_resources(facts,c)
                self.assertFalse((root/'newstage').exists())


if __name__=='__main__':unittest.main()
