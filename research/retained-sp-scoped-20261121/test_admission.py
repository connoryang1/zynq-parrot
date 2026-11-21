import copy
import json
from pathlib import Path
import tempfile
import unittest
from common import *
from protocol import parse,PASS
from qualify import constraints,claim_once
from framing import framing
from canonical import MAX_CANONICAL_BYTES


class ColdProtocol(unittest.TestCase):
    def setUp(self):self.text=(ORIGINAL/'advisory/run.log').read_text()
    def test_actual_closed_SP_protocol(self):
        result=parse(self.text,-6);self.assertEqual(result['counter_values'],['1','1','1','1','8','8'])
    def test_wrong_or_saturated_observer_rejected(self):
        for value in ('0','2','65535'):
            with self.assertRaises(ValueError):parse(self.text.replace('i_hits=1','i_hits='+value),-6)
    def test_missing_complete_return_or_CORE(self):
        for bad in (self.text.replace(PASS,''),self.text.replace('CORE PASS','CORE FAIL')):
            with self.assertRaises((ValueError,AssertionError)):parse(bad,-6)
    def test_duplicate_actual_counter_row(self):
        row=next(l for l in self.text.splitlines() if 'RETAINED_USE_COUNTERS' in l)
        with self.assertRaises(ValueError):parse(self.text+'\n'+row+'\n',-6)


class Admission(unittest.TestCase):
    def fixture(self):
        p=proposal()
        return dict(state='FROZEN-SP-COLD08-awaiting-root-target-review',original_model=dict(sha256=MODEL_SHA),
            proposal=dict(sha256=PROPOSAL_SHA),native_identities=dict(sha256=NATIVE_SHA),
            budget=dict(native_seconds=180,host_seconds=360,FST_bytes=CAP,attempts=1,reader_seconds_per_domain=600,
                minimum_free_reserve_bytes=RESERVE,fixed_artifact_allocation_bytes=ARTIFACT_ALLOCATION,
                canonical_bytes_per_file=MAX_CANONICAL_BYTES),
            domains=p['reader_domains'],writer_leaves=p['leaves'])
    def test_actual400_and_three_domains(self):constraints(self.fixture())
    def test_every_budget_field_fixed(self):
        a=self.fixture()
        for field in a['budget']:
            bad=copy.deepcopy(a);bad['budget'][field]+=1
            with self.assertRaisesRegex(ValueError,'budget'):constraints(bad)
    def test_no_omitted_strict_SRAM_payload_or_observer(self):
        for domain in self.fixture()['domains']:
            a=self.fixture();a['domains'][domain]=a['domains'][domain][:-1]
            with self.assertRaises(ValueError):constraints(a)
    def test_old4KiB_model_rejected(self):
        a=self.fixture();a['original_model']['sha256']='ef0c7c4c9e84e97d4b71d6c80e6c118d5670411be3a3b16e5469cb89239b5f5d'
        with self.assertRaisesRegex(ValueError,'identity'):constraints(a)
    def test_no_retry_with_different_output(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'admission').write_text('fixed')
            claim_once(p/'claim',p/'admission',p/'out')
            with self.assertRaises(FileExistsError):claim_once(p/'claim',p/'admission',p/'other')


class Framing(unittest.TestCase):
    def fixture(self,end=100):
        h=bytearray(74);h[1:9]=(73).to_bytes(8,'big');h[17:25]=end.to_bytes(8,'big');h[65:73]=(1).to_bytes(8,'big')
        return bytes(h)+bytes([8])+(24).to_bytes(8,'big')+(0).to_bytes(8,'big')+(100).to_bytes(8,'big')
    def test_complete_and_unfinalized(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name)/'a.fst';p.write_bytes(self.fixture());self.assertTrue(framing(p)['all_section_bytes_exactly_cover_file'])
            p.write_bytes(self.fixture(0))
            with self.assertRaisesRegex(ValueError,'unfinalized'):framing(p)


if __name__=='__main__':unittest.main()
