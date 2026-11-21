"""Local subprocess tests only; never invoke a physical-board wrapper."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import retention_supervisor as supervisor


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'guest' / 'session.json'
        self.receipt = self.root / 'pilot-supervisor.json'

    def slot(self, code):
        return dict(label='pilot', session_manifest=str(self.manifest),
                    supervisor_receipt=str(self.receipt),
                    argv=[sys.executable, '-c', code, str(self.manifest)])

    def data(self):
        return json.loads(self.receipt.read_text())

    def complete_code(self, suffix=''):
        return ("import json,pathlib,sys,datetime; "
                "pathlib.Path(sys.argv[1]).parent.mkdir(); "
                "end=datetime.datetime.now(datetime.timezone.utc).isoformat(); "
                "pathlib.Path(sys.argv[1]).write_text(json.dumps(dict(state='complete',released_utc=end))); " + suffix)

    def test_real_child_return_and_enclosed_release_are_recorded(self):
        slot = self.slot(self.complete_code())
        self.assertEqual(supervisor.run_one(slot, {}, []), 0)
        data = self.data()
        self.assertEqual((data['state'], data['runner_exit'], data['argv']), ('complete', 0, slot['argv']))
        self.assertGreater(data['pid'], 1)
        self.assertGreater(data['start_ticks'], 0)
        self.assertLessEqual(data['started_utc'], json.loads(self.manifest.read_text())['released_utc'])
        self.assertLessEqual(json.loads(self.manifest.read_text())['released_utc'], data['finished_utc'])

    def test_nonzero_child_cannot_be_promoted_by_complete_manifest(self):
        with self.assertRaises(RuntimeError):
            supervisor.run_one(self.slot(self.complete_code('sys.exit(7)')), {}, [])
        self.assertEqual((self.data()['state'], self.data()['runner_exit']), ('failed', 7))

    def test_exit_zero_without_complete_manifest_is_failed(self):
        with self.assertRaises(FileNotFoundError):
            supervisor.run_one(self.slot('pass'), {}, [])
        self.assertEqual((self.data()['state'], self.data()['runner_exit']), ('failed', 0))

    def test_incomplete_manifest_refuses_continuation(self):
        code = "import pathlib,sys; pathlib.Path(sys.argv[1]).parent.mkdir(); pathlib.Path(sys.argv[1]).write_text('{\"state\":\"reserved\"}')"
        with self.assertRaises(RuntimeError):
            supervisor.run_one(self.slot(code), {}, [])
        self.assertEqual(self.data()['state'], 'failed')

    def test_duplicate_claim_prevents_any_child_execution(self):
        self.receipt.with_suffix('.claim').write_text('existing attempt')
        marker = self.root / 'child-was-run'
        code = 'import pathlib; pathlib.Path(' + repr(str(marker)) + ').touch()'
        with self.assertRaises(FileExistsError):
            supervisor.run_one(self.slot(code), {}, [])
        self.assertFalse(marker.exists())
        self.assertFalse(self.receipt.exists())

    def test_dependency_change_after_child_fails_receipt(self):
        dependency = self.root / 'dependency'
        dependency.write_text('original')
        record = supervisor.operations.frozen.artifact(dependency)
        code = self.complete_code('pathlib.Path(' + repr(str(dependency)) + ').write_text("changed")')
        with self.assertRaises(RuntimeError):
            supervisor.run_one(self.slot(code), {}, [record])
        self.assertEqual((self.data()['state'], self.data()['runner_exit']), ('failed', 0))

    def test_missing_compatibility_proof_prevents_production_launch(self):
        slot = self.slot('raise RuntimeError("must not run")')
        with mock.patch.object(supervisor.operations, 'inputs', return_value=(None, None, None, [slot], [])), \
             mock.patch.object(supervisor, 'ABSENT_PROOF', self.root / 'missing-proof.json'), \
             mock.patch.object(supervisor.subprocess, 'run') as run:
            with self.assertRaises(FileNotFoundError):
                supervisor.main(['pilot'])
        run.assert_not_called()
        self.assertFalse(self.receipt.exists())


if __name__ == '__main__':
    unittest.main()
