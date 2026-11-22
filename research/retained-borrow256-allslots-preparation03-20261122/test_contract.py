"""Pure fixture/source tests; no model/compiler/FST reader/vendor/board."""
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contract as c
import ledger
import parser_fixture
import process_monitor

RO04=Path('/home/coyang/fpga-artifacts/context-resume/retained256-scoped-allslots-20261122/readonly-audit-continuation04')


class ContractTests(unittest.TestCase):
    def test_old_semantic_code_exact(self):
        self.assertIs(c.Validator,c.prior.Validator)
        self.assertIs(c.archive,c.prior.archive)
        for old,new,schema_from,schema_to in (
            (c.prior.check_native,c.semantic_check_native,'retained-capacity256-stream-native-v1','borrow256-capacity-stream-native-v1'),
            (c.prior.verify_audit,c.semantic_verify_audit,'retained256-stream-acceptance-v1','borrow256-stream-acceptance-v1')):
            expected=inspect.getsource(old).replace('def '+old.__name__+'(','def '+new.__name__+'(',1).replace(schema_from,schema_to)
            self.assertEqual(inspect.getsource(new),expected)
        self.assertEqual(len(c.original.audit.selection()),167)

    def test_monitor_and_parser_fixture_are_exact_ro04(self):
        for name in ('process_monitor.py','parser_fixture.py'):
            self.assertEqual((c.HERE/name).read_bytes(),(RO04/name).read_bytes())

    def test_original256_program_and_both_controls(self):
        manifest=json.loads((c.old.HERE/'preparation.DRAFT.json').read_text())['program']
        c.verify(manifest);program=json.loads(Path(manifest['path']).read_text())
        for role in c.ORDER:
            v=c.Validator(program,role)
            self.assertEqual((v.lines,v.sets,len(v.targets)),(256,256,256))
            self.assertTrue(all(len(row['words'])==8 for row in v.targets.values()))
        self.assertEqual(c.counters_for('d-enabled'),[0,256,0,256,0,2048])
        self.assertEqual(c.counters_for('d-off'),[0]*6)
        self.assertEqual(c.counters_for('i-enabled'),[256,0,256,0,2048,0])

    def test_phase_caps_include_all_prior_roles(self):
        stage=Path('/inert-test');C=c.caps(256*1024**2)
        rows={stage/'d-enabled/trace.fst':64*1024**2,stage/'d-enabled-audit/x':16*1024**2,stage/'d-off/trace.fst':13,stage/'metadata':7}
        self.assertEqual(ledger.phase_caps(rows,stage,C)['raw:d-off'],13)
        for path,n in ((stage/'i-enabled/trace.fst',64*1024**2+1),(stage/'d-off-audit/x',16*1024**2+1),(stage/'metadata',16*1024**2+1)):
            with self.subTest(path=path),self.assertRaises(ValueError):ledger.phase_caps(dict(rows,**{str(path):n}),stage,C)

    def test_same128_prospective_partition_prices_three_unchanged_program_copies(self):
        C=c.caps(128*1024**2)
        self.assertEqual((C['raw_per_case'],C['audit_per_case'],C['other_total']),(30*1024**2,8*1024**2,14*1024**2))
        self.assertEqual(C['raw_total']+C['audit_total']+C['other_total'],C['stage_total'])

    def test_required_phase_receipts_reject_stale_or_failed(self):
        with tempfile.TemporaryDirectory(prefix='borrow256-phase-test-') as d:
            out=Path(d);(out/'inventory').write_bytes(b'synthetic')
            (out/'sealed-exit.json').write_text(json.dumps(dict(state='PASS all sealed inactive bytes/inventories unchanged',inventory=c.bind(out/'inventory'))))
            record=dict(parent_pipe_serialized=True,monitor_kind='separate-owned-process',returncode=0,owned_group_remaining=False,failure=None,poll_gap_limit_s=1,max_poll_gap_s=.25,max_scan_seconds=.01)
            (out/'resource-phase.json').write_text(json.dumps(record));c.check_phase_receipts(out)
            for key,value in (('returncode',1),('owned_group_remaining',True),('max_poll_gap_s',1.01),('max_scan_seconds',.501),('parent_pipe_serialized',False)):
                (out/'resource-phase.json').write_text(json.dumps(dict(record,**{key:value})))
                with self.subTest(key=key),self.assertRaises(ValueError):c.check_phase_receipts(out)

    def test_source_snapshot_stable_without_import_order_expansion(self):
        first=c.runtime_sources();self.assertEqual(first,c.runtime_sources())
        names={Path(row['path']).name for row in first}
        self.assertTrue({'process_monitor.py','ledger.py','contract.py','audit_ro.py'}.intersection(names))
        self.assertIn('run_native.py',names)

    def test_real_concurrent_parser_uses_serialized_pipe_and_reaps(self):
        with tempfile.TemporaryDirectory(prefix='borrow256-monitor-test-') as d:
            receipt=Path(d)/'phase.json'
            with process_monitor.phase(lambda:dict(mutable_output_bytes=0),receipt) as guard:
                result=parser_fixture.exercise(c,guard,seconds=1.1)
            record=json.loads(receipt.read_text())
            self.assertTrue(record['parent_pipe_serialized']);self.assertFalse(record['owned_group_remaining'])
            self.assertEqual(record['returncode'],0);self.assertIsNone(record['failure'])
            self.assertGreater(result['event_lines'],167);self.assertGreater(result['background_callbacks'],0)


if __name__=='__main__':unittest.main()
