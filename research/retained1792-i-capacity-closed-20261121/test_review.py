#!/usr/bin/env python3
"""Closed-proof refusal witnesses and local-source portability; no target/reader."""
import copy,json,tempfile,unittest
from pathlib import Path
import review

class ClosedProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full=json.loads((review.GOOD/'i-enabled-audit/verification.json').read_text())
        p=Path(cls.full['bindings']['program']['path']);cls.expected=review.oracle(json.loads(p.read_text()))
        cls.address=next(iter(cls.expected))
    def changed(self):return copy.deepcopy(self.full)
    def test_positive_all_addresses(self):
        self.assertEqual(review.inspect_semantics(self.full,self.expected)['ordered_instruction_retirements'],28672)
    def test_reject_one_wrong_payload_word(self):
        r=self.changed();r['retained_bursts'][self.address]['words'][7]['data']^=1
        with self.assertRaisesRegex(ValueError,'512'):review.inspect_semantics(r,self.expected)
    def test_reject_duplicate_bank(self):
        r=self.changed();r['retained_bursts'][self.address]['words'][7]['bank']=r['retained_bursts'][self.address]['words'][6]['bank']
        with self.assertRaisesRegex(ValueError,'bank'):review.inspect_semantics(r,self.expected)
    def test_reject_reordered_instruction_retirement(self):
        r=self.changed();pcs=r['retired_instruction_pcs'][self.address];pcs[0],pcs[1]=pcs[1],pcs[0]
        with self.assertRaisesRegex(ValueError,'16 target'):review.inspect_semantics(r,self.expected)
    def test_reject_missing_target(self):
        r=self.changed();del r['hits'][self.address]
        with self.assertRaisesRegex(ValueError,'every distinct'):review.inspect_semantics(r,self.expected)
    def test_reject_ordinary_fallback(self):
        r=self.changed();r['ordinary_bursts'][self.address]={}
        with self.assertRaisesRegex(ValueError,'ordinary'):review.inspect_semantics(r,self.expected)
    def test_reject_d_role(self):
        r=self.changed();r['lane']='d'
        with self.assertRaisesRegex(ValueError,'I-only'):review.inspect_semantics(r,self.expected)
    def test_reject_late_publication(self):
        r=self.changed();r['publications'][self.address]['time']=r['hits'][self.address]['lookup']
        with self.assertRaisesRegex(ValueError,'publications before'):review.inspect_semantics(r,self.expected)

class SourcePortability(unittest.TestCase):
    def test_identical_local_source_can_have_different_path(self):
        row=review.bind(review.PRODUCER)
        with tempfile.TemporaryDirectory() as d:
            local=Path(d)/'relocated-byte-identical.py';local.write_bytes(Path(review.PRODUCER).read_bytes())
            self.assertEqual(review.verify_local_copy(row,local),local)
    def test_changed_local_source_rejected(self):
        row=review.bind(review.PRODUCER)
        with tempfile.TemporaryDirectory() as d:
            local=Path(d)/'changed.py';local.write_bytes(Path(review.PRODUCER).read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'producer bytes'):review.verify_local_copy(row,local)
    def test_wrong_producer_path_rejected(self):
        row=review.bind(review.PRODUCER);row['path']='/tmp/untrusted-same-name/continuation.py'
        with self.assertRaisesRegex(ValueError,'producer path'):review.verify_local_copy(row,review.HERE/'producer/continuation.py')
if __name__=='__main__':unittest.main(verbosity=2)
