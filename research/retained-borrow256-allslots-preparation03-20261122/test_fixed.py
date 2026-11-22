"""Fixed reserve fixtures only; no vendor, model, compiler or FST reader."""
import copy
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import contract as c
import ledger
import fixed_shared as f
import fixed_reservations as frozen

POLICY=json.loads(f.POLICY.read_text())


class FixedTests(unittest.TestCase):
    def test_live_only_current_mutable_scan_and_two_statvfs_calls(self):
        with tempfile.TemporaryDirectory(prefix='fixed-current-only-')as d:
            out=Path(d)/'d-enabled';out.mkdir();x=ledger.Ledger.__new__(ledger.Ledger)
            x.out=out;x.stage=Path(d);x.stage_rows={};x.basepool=509615329;x.durable_bytes=47509654;x.prep_bytes=300000;x.initial=dict(policy=POLICY)
            c.CAPS=c.caps(256*1024**2)
            def current(path):self.assertEqual(path,out);return {out/'run.log':31}
            with patch.object(ledger,'scan',side_effect=current)as scan,patch.object(frozen,'scan',side_effect=AssertionError('CAD/old scan forbidden')),patch.object(f,'load',side_effect=AssertionError('receipt parsing in live forbidden')),patch.object(c.prior.shared,'check',side_effect=AssertionError('legacy guard forbidden')),patch.object(f.shutil,'disk_usage',return_value=SimpleNamespace(free=1<<50))as free:
                result=x.check();self.assertEqual(scan.call_count,1);self.assertEqual(free.call_count,2)
            self.assertEqual(result['mutable_output_bytes'],31)
            self.assertEqual(result['HOME_required_free_bytes'],2935105734)

    def test_fixed_live_budget_math_and_failure(self):
        snapshot=dict(policy=POLICY)
        with patch.object(f.shutil,'disk_usage',return_value=SimpleNamespace(free=1<<50)):
            q=f.live_check(snapshot,509615329,47509654,300000,Path('/inert'))
        self.assertEqual(q['RAM_required_free_bytes'],1073741824+805306368-509615329+1123372466+2684354560)
        self.assertEqual(q['HOME_required_free_bytes'],2935105734)
        with patch.object(f.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(ValueError):f.live_check(snapshot,509615329,47509654,300000,Path('/inert'))

    def test_durable_archive_is_explicitly_deferred(self):
        with patch.object(f.shutil,'disk_usage',return_value=SimpleNamespace(free=1<<50)):
            with self.assertRaisesRegex(ValueError,'archival deferred'):f.live_check(dict(policy=POLICY),509615329,47509655,300000,Path('/inert'))

    def test_actual_three_receipt_metadata_and_halfpair_refusal(self):
        rows={k:POLICY['old_R8_freeze'][k]for k in ('work','evidence','complete')}
        result=frozen.closed_pair(dict(old_R8_freeze=rows),full=False)
        self.assertEqual(result['work']['freeze_pair_id'],POLICY['old_R8_freeze']['freeze_pair_id'])
        with self.assertRaisesRegex(ValueError,'all three'):frozen.closed_pair(dict(old_R8_freeze={k:v for k,v in rows.items()if k!='complete'}))
        wrong=copy.deepcopy(rows);wrong['work']['path']='/tmp/not-the-freeze'
        with self.assertRaisesRegex(ValueError,'fixed receipt'):frozen.closed_pair(dict(old_R8_freeze=wrong))

    def test_real_monitor_resource_failure_reaps_owned_group(self):
        import process_monitor
        with tempfile.TemporaryDirectory(prefix='fixed-resource-failure-')as d:
            receipt=Path(d)/'phase.json';count=[0]
            def check():
                count[0]+=1
                if count[0]>1:raise ValueError('fixture resource limit')
                return dict(mutable_output_bytes=0)
            with self.assertRaisesRegex(ValueError,'fixture resource limit'):
                with process_monitor.phase(check,receipt)as guard:time.sleep(.35);guard()
            q=json.loads(receipt.read_text());self.assertFalse(q['owned_group_remaining']);self.assertEqual(q['group_states'][-1]['members'],[])


if __name__=='__main__':unittest.main()
