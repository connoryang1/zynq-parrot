"""Offline fixed program bindings, declaration and safe-result refusal tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import retained29_protocol as base
import retained29_cost_protocol as cost
import retained29_safe_functional_protocol as functional
import retained29_safe_session as safe
import test_retained29_session as old

ROOT=base.ROOT
PREP=ROOT/'research/retained-trigger-accounting-20261121/closed-cost01/verification.json'

def programs():
    proof=json.loads(PREP.read_text())
    present=json.loads((ROOT/'research/retained29-session-preparation-20261121/closed-preparation-002/probe-present.DRAFT.json').read_text())
    return dict(program_preparation=base.binding(PREP),programs=dict(
        **{kind:{key:row[key] for key in ('elf','transfer')} for kind,row in proof['programs'].items()},
        probe={key:present['artifacts'][key] for key in ('elf','transfer')}))


class ProgramBindings(unittest.TestCase):
    def test_actual_new_rv64_programs_and_transfers_bind_closed_runtime_proof(self):
        a=programs();cost.validate_programs(a)
        self.assertEqual({k:r['elf']['sha256'] for k,r in a['programs'].items()},cost.ELF_SHAS)
        self.assertNotEqual(cost.ELF_SHAS['plain'],base.ELF_SHAS['benchmark-functional'])
    def test_old_plain_elf_or_changed_transfer_never_substitutes(self):
        a=programs();old=json.loads((ROOT/'research/retained29-session-preparation-20261121/closed-preparation-002/benchmark-functional.DRAFT.json').read_text())
        a['programs']['plain']['elf']=old['artifacts']['elf']
        with self.assertRaises(ValueError):cost.validate_programs(a)
        a=programs();a['programs']['regex']['transfer']=a['programs']['plain']['transfer']
        with self.assertRaises(ValueError):cost.validate_programs(a)
    def test_all21_original_sources_match_cost_preparation_snapshots(self):
        proof=json.loads(PREP.read_text());self.assertTrue(proof['legacy_sources_unchanged'])
        self.assertEqual(len(cost.original.source_hashes()),21)
        # Closed COST proof binds every original source in the root preparation;
        # reverify its bytes rather than trusting the boolean in isolation.
        record=next(row['original'] for row in proof['snapshots'] if row['original']['path'].endswith('/manifest.json'))
        base.verify_binding(record);manifest=json.loads(Path(record['path']).read_text())
        self.assertEqual(manifest['legacy_sources_before'],cost.original.source_hashes())
        self.assertEqual(manifest['legacy_sources_after'],cost.original.source_hashes())


class Cohort(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'cohort.json'
        self.plan=cost.plan_for('cost-performance-acquisition','regex',2)
        self.a=dict(role=self.plan['role'],plan=self.plan,sources={'HOST_VERIFY':'a'},artifacts={'HOST_VERIFY':'a'},visit_id='R1')
        self.record=dict(schema='bp-retained29-cost-cohort-v1',state='predeclared-reviewed',declared_utc='2026-11-21T00:00:00+00:00',
            sources=self.a['sources'],artifacts=self.a['artifacts'],elf_sha256=cost.ELF_SHAS,
            visits=[dict(id='R1',independent_boot=True,plan=self.plan),dict(id='R2',independent_boot=True,plan=cost.plan_for('cost-performance-acquisition','regex',5))])
    def tearDown(self):self.tmp.cleanup()
    def check(self):
        self.path.write_text(json.dumps(self.record));self.a['cohort_record']=base.binding(self.path);return cost.validate_cohort(self.a)
    def test_explicit_two_boot_declaration_and_rotation(self):self.check()
    def test_single_boot_duplicate_id_wrong_order_or_source_rejected(self):
        mutations=[lambda r:r['visits'].pop(),lambda r:r['visits'][1].update(id='R1'),
            lambda r:r['visits'][0]['plan']['cases'].reverse(),lambda r:r.update(sources={}),
            lambda r:r['visits'][0].update(independent_boot=False),lambda r:r.update(elf_sha256={})]
        original=copy.deepcopy(self.record)
        for mutate in mutations:
            self.record=copy.deepcopy(original);self.a['plan']=copy.deepcopy(self.plan);mutate(self.record)
            with self.assertRaises(ValueError):self.check()
    def test_noncanonical_workload_size_loop_and_rotation_rejected(self):
        for key,value in [('loops',255),('repeats',2),('rotation',True),('warmup',8)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):cost.validate_plan(plan)


class SafeGate(unittest.TestCase):
    def test_full_unchanged_probe_result_requires_final_safe_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);core=old.admission('probe-present');wrapper=dict(supervisor_sources={'HOST_VERIFY':'1'})
            input_path=root/'input.json';input_path.write_text(json.dumps(wrapper))
            console=root/'console.log';console.write_text(old.boot(core)+core['artifacts']['elf']['sha256']+'  '+base.GUEST['probe-present']+'\n'+old.guest(core)+'RETAINED29_EXIT rc=0\n# \n'+old.footer())
            receipt=root/'safe-publication.json';receipt.write_text(json.dumps(dict(state='verified old2dd/helper/overlay/operating recovery',label='final',power_pending=None,own_guest=None)))
            result=dict(schema=functional.SCHEMA,safe_engine_schema=safe.ENGINE_SCHEMA,state=functional.SUCCESS_STATE,
                role='probe-present',safe_recovery_verified=True,recovery='complete before reservation release',guest_boots=1,
                performance_inference=False,performance_accepted=False,supervisor_admission=wrapper,admission=core,
                sources=core['sources'],supervisor_sources=wrapper['supervisor_sources'],hardware=core['hardware'],artifacts=core['artifacts'],
                supervisor_admission_record=base.binding(input_path),guest=dict(runner_exit=0,runner_signal=None,guest_exit=0,shell_return=True,console=base.binding(console)),
                started_utc='2026-11-21T00:00:00+00:00',release_after_recovery_utc='2026-11-21T00:10:00+00:00',
                reservation_release_utc='2026-11-21T00:10:00+00:00',operation_logs={},operation_journal=base.binding(receipt))
            path=root/'session.json'
            def check():path.write_text(json.dumps(result));return functional.verify_result(base.binding(path),'probe-present')
            with patch.object(functional,'validate_admission',return_value=core):
                check()
                for key,value in [('safe_recovery_verified',False),('guest_boots',2),('recovery','unconfirmed'),('performance_accepted',True)]:
                    bad=copy.deepcopy(result);result[key]=value
                    with self.assertRaises(ValueError):check()
                    result=bad
                receipt.write_text(json.dumps(dict(state='verified old2dd/helper/overlay/operating recovery',label='initial')))
                result['operation_journal']=base.binding(receipt)
                with self.assertRaises(ValueError):check()


if __name__=='__main__':unittest.main()
