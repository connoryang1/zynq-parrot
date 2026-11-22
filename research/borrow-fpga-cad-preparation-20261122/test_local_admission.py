"""Pure host admission fixtures: no launcher, SSH, tmux, vendor or process signals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import sys
import io
from unittest.mock import patch
import monitor_local as monitor
import prepare_admission

HERE=Path(__file__).resolve().parent

class LocalAdmission(unittest.TestCase):
    def setUp(self):
        # ROOT's private shared-memory mount is not visible to this test
        # process. Only those explicit private copied inputs use metadata
        # fixtures; actual source readiness is the bound ROOT receipt.
        original=monitor.bind
        private={r['path']:r for r in self.draft()['bindings'] if r['path'].startswith('/dev/shm/')}
        def fixture_bind(p):
            return private[str(p)] if str(p) in private else original(p)
        guard=patch.object(monitor,'bind',side_effect=fixture_bind)
        guard.start();self.addCleanup(guard.stop)

    def draft(self):
        return json.loads((HERE/'admission.DRAFT.json').read_text())

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

    def test_explicit_source_pinned_release_writes_only_new_admission(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,release=self.promote_for_test(root);out=root/'TEST_ONLY_admission.json'
            argv=['prepare_admission','--draft-sha256',monitor.bind(HERE/'admission.DRAFT.json')['sha256'],'--root-release',str(release),'--root-release-sha256',monitor.bind(release)['sha256'],'--output',str(out)]
            with patch.object(sys,'argv',argv),patch.object(sys,'stdout',io.StringIO()),patch.object(monitor,'poll',side_effect=AssertionError('no polling')):
                prepare_admission.main()
            self.assertTrue(json.loads(out.read_text())['launchable'])
            self.assertFalse(self.draft()['launchable'])
            with patch.object(sys,'argv',argv),patch.object(sys,'stdout',io.StringIO()):
                with self.assertRaises(FileExistsError):prepare_admission.main()

    def test_wrong_readiness_and_changed_private_input_reject(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);q,_=self.promote_for_test(root)
            source=Path(q['prerequisites']['fpga_source']['binding']['path'])
            wrong=json.loads(source.read_text());wrong['script']['sha256']='0'*64
            p=root/'TEST_ONLY_wrong_readiness.json';p.write_text(json.dumps(wrong))
            q['prerequisites']['fpga_source']['binding']=monitor.bind(p)
            with self.assertRaisesRegex(RuntimeError,'wrong actual private FPGA source'):monitor.check_bindings(q)
            q,_=self.promote_for_test(root)
            private=next(r for r in q['bindings'] if r['path'].startswith('/dev/shm/'))
            private['sha256']='0'*64
            with self.assertRaisesRegex(RuntimeError,'changed bound input'):monitor.check_bindings(q)

if __name__=='__main__':unittest.main()
