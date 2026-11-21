"""Synthetic completion receipts/transcripts only; no acquisition or board use."""
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import retention_operations as ops
import test_retention_admission as fixtures


class RetentionOperationsTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.RetentionAdmissionTests('runTest');self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.a,self.p=self.fx.a,self.fx.pins
        self.t=json.loads(self.fx.acquisition.read_text());self.t['all_attempts_declared']=False
        self.slots=ops.fixed_table(self.a,self.p,self.t)
        self.input_records=[ops.frozen.artifact(ops.frozen.ADMISSION),ops.frozen.artifact(ops.frozen.PINS)]
        self.patch=mock.patch.object(ops,'inputs',return_value=(self.a,self.p,self.t,self.slots,self.input_records))
        self.patch.start();self.addCleanup(self.patch.stop)
        for i,slot in enumerate(self.slots):
            session=json.loads(Path(slot['session_manifest']).read_text())
            receipt=dict(label=slot['label'],argv=slot['argv'],session_manifest=slot['session_manifest'],
                state='complete',runner_exit=0,pid=123456789+i,start_ticks=1234+i,
                started_utc=(ops.frozen.timestamp(session['started_utc'])-timedelta(seconds=1)).isoformat(),
                finished_utc=(ops.frozen.timestamp(session['released_utc'])+timedelta(seconds=1)).isoformat(),
                operations_source_sha256=ops.frozen.sha(Path(ops.__file__)),argv_table_sha256=ops.frozen.sha(ops.TABLE),
                validator_source_sha256=ops.VALIDATOR_SHA)
            Path(slot['supervisor_receipt']).write_text(json.dumps(receipt))

    def receipt(self,index,**changes):
        path=Path(self.slots[index]['supervisor_receipt']);d=json.loads(path.read_text());d.update(changes);path.write_text(json.dumps(d))

    def mutate_log(self,index,fn):
        path=self.fx.logs[index];path.write_text(fn(path.read_text()))

    def gate(self):return ops.complete_prefix('R2b')

    def test_all_slots_gate_and_original_frozen_audit_agree_without_effect_output(self):
        result=self.gate();full=ops.frozen.audit(self.fx.acquisition)
        self.assertEqual(sum(v['boot_count'] for v in result['accepted']),18)
        self.assertEqual(len(full['primary_boots']),16)
        self.assertIsNone(result['next_argv']);self.assertTrue(result['accepted'][0]['pilot_excluded'])
        self.assertFalse(any(x['pilot_excluded'] for x in result['accepted'][1:]))
        self.assertNotIn('cycles',json.dumps(result));self.assertFalse(result['deployment_gain_claim_established'])
        # Fixture includes negative scan, null lookup, positive parse/chase:
        # no sign or minimum capture count can select continuation.
        self.assertTrue(all('source_reset_scope' in x for x in result['accepted']))

    def test_pilot_only_acceptance_returns_exact_next_reservation(self):
        for slot in self.slots[1:]:
            import shutil
            shutil.rmtree(Path(slot['session_manifest']).parent)
            Path(slot['supervisor_receipt']).unlink()
        result=ops.complete_prefix('pilot')
        self.assertEqual(result['next_argv'],self.slots[1]['argv'])
        self.assertEqual(result['accepted'][0]['boot_count'],2)

    def test_future_output_even_empty_refuses_advance(self):
        with self.assertRaisesRegex(ValueError,'future slot already exists'):ops.complete_prefix('pilot')

    def test_missing_or_malformed_supervisor_stops(self):
        path=Path(self.slots[1]['supervisor_receipt'])
        for value in ('{',None):
            if value is None:path.unlink()
            else:path.write_text(value)
            with self.assertRaises((ValueError,FileNotFoundError)):self.gate()

    def test_live_or_pid_reused_supervisor_stops(self):
        self.receipt(0,pid=os.getpid())
        with self.assertRaisesRegex(ValueError,'still present'):self.gate()

    def test_supervisor_wrong_argv_or_session_path_refused(self):
        for change in ({'argv':self.slots[0]['argv']+['--retention-probe','present']},
                       {'session_manifest':self.slots[1]['session_manifest']}):
            with self.subTest(change=change):
                self.receipt(0,**change)
                with self.assertRaisesRegex(ValueError,'command/path binding'):self.gate()
                self.receipt(0,argv=self.slots[0]['argv'],session_manifest=self.slots[0]['session_manifest'])

    def test_failed_supervisor_or_source_provenance_refused(self):
        for key,value,pattern in [('runner_exit',1,'incomplete/nonzero'),('state','running','incomplete/nonzero'),
                ('operations_source_sha256','0'*64,'provenance'),('argv_table_sha256','0'*64,'provenance'),
                ('validator_source_sha256','0'*64,'provenance'),('pid',True,'identity'),('start_ticks',0,'identity')]:
            path=Path(self.slots[0]['supervisor_receipt']);original=path.read_text()
            with self.subTest(key=key):
                self.receipt(0,**{key:value})
                with self.assertRaisesRegex(ValueError,pattern):self.gate()
                path.write_text(original)

    def test_supervisor_finish_cannot_precede_release(self):
        session=json.loads(self.fx.sessions[0].read_text())
        self.receipt(0,finished_utc=session['started_utc'])
        with self.assertRaisesRegex(ValueError,'release follows'):self.gate()

    def test_reversed_supervisor_chronology_stops(self):
        r=json.loads(Path(self.slots[0]['supervisor_receipt']).read_text())
        self.receipt(1,started_utc=r['started_utc'])
        with self.assertRaisesRegex(ValueError,'chronology'):self.gate()

    def test_session_failure_or_unreleased_refused(self):
        self.fx.mutate_session(1,lambda d:d.update(state='failed'))
        with self.assertRaisesRegex(ValueError,'session incomplete'):self.gate()
        self.fx.mutate_session(1,lambda d:(d.update(state='complete'),d.pop('released_utc')))
        with self.assertRaises(KeyError):self.gate()

    def test_wrong_policy_workload_order_and_extra_boot_refused(self):
        path=self.fx.sessions[1];original=path.read_text()
        for mutate in (lambda d:d['plan'].reverse(),lambda d:d['plan'].append(dict(d['plan'][0]))):
            self.fx.mutate_session(1,mutate)
            with self.assertRaisesRegex(ValueError,'configuration/order|two fresh'):self.gate()
            path.write_text(original)

    def test_source_snapshot_and_fixed_identity_refused(self):
        rel=next(iter(self.p['host_sources']));path=self.fx.sessions[1].parent/'host-sources'/rel
        original=path.read_bytes();path.write_text('changed')
        with self.assertRaisesRegex(ValueError,'snapshot changed'):self.gate()
        path.write_bytes(original);self.fx.status(2,elf_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'status identity'):self.gate()

    def test_old_helper_hash_missing_return_and_wrong_bounds_refused(self):
        path=self.fx.logs[2];original=path.read_text()
        for old,new,pattern in [('BOARD_RUNNER_SOURCE_SHA256','OLD_HELPER','de54'),
                ('# poweroff -f','','shell return'),('Memory limited to 46MB','Memory limited to 64MB','46MB'),
                (self.a['identity']['elf']['sha256']+'  '+ops.frozen.GUEST_ELF,'wrong hash','guest hash')]:
            with self.subTest(pattern=pattern):
                path.write_text(original.replace(old,new))
                with self.assertRaisesRegex(ValueError,pattern):self.gate()
        path.write_text(original)

    def test_missing_scope_csr_resource_and_nonzero_prefix_refused(self):
        path=self.fx.logs[2];original=path.read_text()
        for prefix in ('PIPE_HINT_SCOPE','PIPE_HINT_RETENTION','PIPE_HINT_RESOURCE'):
            path.write_text('\n'.join(s for s in original.splitlines() if not s.startswith(prefix))+'\n')
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):self.gate()
        path.write_text(original.replace('after=0x0000000000000201','after=0x0000000000400201'))
        with self.assertRaisesRegex(ValueError,'prefix hint|prefix activity'):self.gate()

    def test_probe_library_or_wrong_global_mode_refused(self):
        path=self.fx.logs[2];original=path.read_text()
        for text in ('ICACHE_RETENTION_PROBE_PASS\n'+original,'PIPE_HINT_LIBRARY zlib=x\n'+original,
                original.replace('raw=0x8000000000000000 capability=1 mode=0',
                                 'raw=0x8000000000000001 capability=1 mode=1',1)):
            path.write_text(text)
            with self.assertRaisesRegex(ValueError,'prior probe/library|policy mode mismatch'):self.gate()

    def test_duplicate_transcript_not_independent(self):
        self.fx.logs[3].write_bytes(self.fx.logs[2].read_bytes())
        with self.assertRaisesRegex(ValueError,'duplicate transcript content'):self.gate()

    def test_final_recheck_detects_mutation_and_cli_does_not_overwrite(self):
        original=ops.check_session
        def corrupt(*args):
            result=original(*args)
            if args[0]['label']=='R2b':self.fx.logs[0].write_text('changed after admission')
            return result
        with mock.patch.object(ops,'check_session',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'changed during'):self.gate()
        out=self.fx.root/'out.json';out.write_text('old evidence')
        with mock.patch.object(ops,'complete_prefix',return_value={'state':'fake gate PASS'}):
            self.assertEqual(ops.main(['pilot','--output',str(out)]),1)
        self.assertEqual(out.read_text(),'old evidence')


class FixedOperationsInputsTests(unittest.TestCase):
    def test_real_offline_inputs_and_exact_table(self):
        a,p,t,slots,records=ops.inputs()
        self.assertEqual(len(slots),9);self.assertGreater(len(records),15)
        self.assertEqual(slots[0]['cells'],[['retention-rr','scan'],['retention-first','scan']])
        self.assertEqual([s['label'] for s in slots[1:]],['R1a','R1b','F1a','F1b','F2a','F2b','R2a','R2b'])
        self.assertTrue(all(len(s['cells'])==2 for s in slots))
        for s in slots:
            argv=s['argv'];self.assertNotIn('--retention-probe',argv);self.assertNotIn('--zlib-library',argv)
            self.assertEqual(argv[3],a['identity']['nbf']['path']);self.assertEqual(argv[6],a['identity']['package']['path'])
            for key,v in (('--loops',8 if s['pilot'] else 64),('--warmup',4 if s['pilot'] else 32),('--repeats',2 if s['pilot'] else 4)):
                self.assertEqual(argv[argv.index(key)+1],str(v))
            self.assertEqual(argv[7],str(Path(s['session_manifest']).parent))

    def test_changed_template_validator_or_table_refused(self):
        original=ops.frozen.sha
        for path in (ops.TEMPLATE,Path(ops.frozen.__file__)):
            with self.subTest(path=path),mock.patch.object(ops.frozen,'sha',side_effect=lambda p: '0'*64 if p==path else original(p)):
                with self.assertRaisesRegex(ValueError,'validator/template changed'):ops.inputs()
        # Alter only table bytes through a path mock; no frozen file is edited.
        actual_read=Path.read_text
        def altered(path,*a,**k):return '[]' if path==ops.TABLE else actual_read(path,*a,**k)
        with mock.patch.object(Path,'read_text',altered):
            with self.assertRaisesRegex(ValueError,'argv table differs'):ops.inputs()


if __name__=='__main__':unittest.main()
