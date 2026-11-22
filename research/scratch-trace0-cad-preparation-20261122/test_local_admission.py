"""Pure host admission fixtures: no launcher, SSH, tmux, vendor or process signals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import monitor_local as monitor

HERE=Path(__file__).resolve().parent

class LocalAdmission(unittest.TestCase):
    def draft(self):
        return json.loads((HERE/'admission-source04.DRAFT.json').read_text())

    def promote_for_test(self,root):
        q=self.draft();q['launchable']=True
        p=root/'TEST_ONLY_root_release.json'
        p.write_text(json.dumps(dict(state='ROOT ADMITTED local clean CAD',top=q['configuration']['top'],bp=q['configuration']['bp'],launch=q['direct_launch'],resources=q['resources'],holds_released=True,operational_bindings=q['operational_bindings'])))
        q['prerequisites']['root_release']=dict(ROOT_verified=True,binding=monitor.bind(p))
        return q,p

    def test_draft_fails_before_poll(self):
        with patch.object(monitor,'poll',side_effect=AssertionError('no process launch')):
            with self.assertRaisesRegex(RuntimeError,'UNLAUNCHABLE'):
                monitor.check_bindings(self.draft())

    def test_exact_local_release_not_area_or_farm_needed(self):
        with tempfile.TemporaryDirectory() as d:
            q,_=self.promote_for_test(Path(d))
            self.assertNotIn('uce_area',q['prerequisites'])
            self.assertNotIn('farm_admission',q['prerequisites'])
            monitor.check_bindings(q)
            changed=copy.deepcopy(q);changed['direct_launch']['environment']['FPGA_CACHE_MISS_TRACE']='1'
            with self.assertRaisesRegex(RuntimeError,'exact source/profile'):monitor.check_bindings(changed)
            changed=copy.deepcopy(q);changed['direct_launch']['argv'][0]='/TEST_ONLY/not-reviewed'
            with self.assertRaisesRegex(RuntimeError,'exact source/profile'):monitor.check_bindings(changed)

    def test_release_source_and_hold_are_bound(self):
        with tempfile.TemporaryDirectory() as d:
            q,p=self.promote_for_test(Path(d));r=json.loads(p.read_text());r['holds_released']=False;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(RuntimeError,'prerequisite changed'):monitor.check_bindings(q)
            q['prerequisites']['root_release']['binding']=monitor.bind(p)
            with self.assertRaisesRegex(RuntimeError,'holds not released'):monitor.check_bindings(q)
            r['holds_released']=True;r['operational_bindings']=[];p.write_text(json.dumps(r));q['prerequisites']['root_release']['binding']=monitor.bind(p)
            with self.assertRaisesRegex(RuntimeError,'operational source'):monitor.check_bindings(q)

    def test_cancel_body_is_exact_maintained_protocol(self):
        q=self.draft();parent=Path(q['cancellation_derivation']['parent']['path'])
        self.assertEqual(monitor.bind(parent),q['cancellation_derivation']['parent'])
        body=parent.read_text().split('ssh_builder "$builder" bash -s -- "$job_id" "$log_root" <<\'REMOTE\'\n',1)[1].split('\nREMOTE',1)[0]+'\n'
        self.assertEqual((HERE/'cancel_local.sh').read_text(),body)

if __name__=='__main__':unittest.main()
