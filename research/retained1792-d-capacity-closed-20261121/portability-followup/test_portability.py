"""Light source-byte/path fixtures; no model, reader or audit execution."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('portable_closed_review',ROOT/'review.py')
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.bridge=json.loads((review.GOOD/'audit-continuation.json').read_text())
        self.origin=Path('/home/coyang/zynq-parrot-linux-host-observer/research/retained1792-audit-continuation-20261121/continuation.py')

    def test_actual_main_copy_has_exact_producer_bytes(self):
        local=Path('/home/coyang/zynq-parrot-linux-capacity/research/retained1792-audit-continuation-20261121/continuation.py')
        self.assertEqual(review.qualified_contract(self.bridge,local),local)

    def test_identical_relocated_copy_accepted_corrupted_copy_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'continuation.py';p.write_bytes(self.origin.read_bytes())
            review.qualified_contract(self.bridge,p)
            p.write_bytes(p.read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'byte-identical'):review.qualified_contract(self.bridge,p)

    def test_wrong_original_path_not_accepted_even_for_same_filename_bytes(self):
        b=copy.deepcopy(self.bridge)
        next(row for row in b['sources'] if row['path']==str(self.origin))['path']='/arbitrary/continuation.py'
        with self.assertRaisesRegex(ValueError,'fixed producer'):review.qualified_contract(b,self.origin)

    def test_duplicate_anchor_or_changed_hash_rejected(self):
        for mode in ('duplicate','changed-hash'):
            b=copy.deepcopy(self.bridge);row=next(row for row in b['sources'] if row['path']==str(self.origin))
            if mode=='duplicate':b['sources'].append(copy.deepcopy(row))
            else:row['sha256']='0'*64
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'fixed producer'):review.qualified_contract(b,self.origin)


if __name__=='__main__':unittest.main()
