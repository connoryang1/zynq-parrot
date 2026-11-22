"""Verify declared AND actual reader bytes; never executes the reader."""
import unittest
from unittest.mock import patch
import bridge
import contract

ROW=dict(path='/home/coyang/fpga-artifacts/context-resume/retained-use-observation-20261121/fst-reader/fst_events',bytes=151200,
         sha256='a9227fe2368ab376b7700a08e044b81c18261432dadeb89e8baeafab021f7541')


class ReaderTests(unittest.TestCase):
    def test_actual_installed_reader_hash_without_execution(self):
        bridge.verify_reader(ROW)
        contract.verify(ROW)

    def test_actual_binary_drift_refused_by_both_bridge_and_admission_verifier(self):
        with patch.object(bridge,'bind',return_value=dict(ROW,sha256='0'*64)):
            with self.assertRaisesRegex(ValueError,'frozen bytes changed'):bridge.verify_reader(ROW)
            with self.assertRaisesRegex(ValueError,'frozen bytes changed'):contract.verify(ROW)

    def test_caller_cannot_declare_another_reader(self):
        for row in (dict(ROW,path='/tmp/not-a-reader'),dict(ROW,bytes=151201),dict(ROW,sha256='0'*64)):
            with self.subTest(row=row),self.assertRaisesRegex(ValueError,'qualified reader record'):bridge.verify_reader(row)


if __name__=='__main__':unittest.main()
