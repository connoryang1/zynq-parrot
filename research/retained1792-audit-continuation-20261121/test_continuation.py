"""Host-only inheritance/budget fixtures; no model or reader execution."""
import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sys
import unittest
from unittest import mock
import continuation as c


class ContinuationTests(unittest.TestCase):
    def bridge(self):
        return dict(schema='retained1792-audit-continuation-v1',
            state='ROOT-APPROVED audit attempt2; inherited native only',
            original_preparation=dict(path=str(c.STAGE/'preparation.json'),bytes=9508,sha256=c.ADMISSION_SHA),
            inherited_native_sha256=c.NATIVE_SHA,failed_attempt=c.bind(c.STOP),
            change=dict(phase='read-only audit only',old_HOME_floor=3*1024**3,
                new_HOME_floor=1024**3,native_HOME_floor=3*1024**3),
            caps=copy.deepcopy(c.CAPS),geometry=copy.deepcopy(c.GEOMETRY),sources=c.sources())

    def test_explicit_inheritance_validates_without_promoting_attempt1(self):
        c.validate_bridge(self.bridge())
        stopped=c.check_stop(check_original=False)
        self.assertEqual(stopped['root_audit']['exit_code'],1)
        self.assertEqual(stopped['root_native']['proof_sha256'],c.NATIVE_SHA)

    def test_wrong_native_admission_failed_receipt_and_source_rejected(self):
        for key in ('native','admission','failed','source'):
            b=self.bridge()
            if key=='native': b['inherited_native_sha256']='0'*64
            if key=='admission': b['original_preparation']['sha256']='0'*64
            if key=='failed': b['failed_attempt']['path']='/untrusted/replacement'
            if key=='source': b['sources'][0]['sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError): c.validate_bridge(b)

    def test_no_cap_time_ram_or_native_floor_raise(self):
        for key in ('audit_per_case','stage_total','reader_s','RAM_reserve'):
            b=self.bridge();b['caps'][key]+=1
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'unchanged caps'):c.validate_bridge(b)
        for key in ('new_HOME_floor','native_HOME_floor','phase'):
            b=self.bridge();b['change'][key]=0
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'only audit HOME'):c.validate_bridge(b)

    def test_unsigned_external_continuation_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'continuation.json';p.write_text(json.dumps(self.bridge()))
            with mock.patch.object(c,'check_stop',side_effect=AssertionError('must not read inheritance')):
                with self.assertRaisesRegex(ValueError,'external continuation'):c.load(p,'0'*64)

    def test_don_dispatch_uses_only_old_admission_and_native_sha(self):
        p={'_continuation':self.bridge()}
        with mock.patch.object(c.old,'check_native',return_value='checked') as check:
            self.assertEqual(c.check_native(c.STAGE,'d-enabled',p,'new-preparation',c.NATIVE_SHA),'checked')
            self.assertEqual(check.call_args.args[3],str(c.STAGE/'preparation.json'))
            with self.assertRaisesRegex(ValueError,'only exact inherited'):c.check_native(c.STAGE,'d-enabled',p,'new','0'*64)
            c.check_native(c.STAGE,'d-off',p,'new-preparation','1'*64)
            self.assertEqual(check.call_args.args[3],'new-preparation')

    def usage(self, stage, homefree=1536*1024**2, ramfree=2*1024**3):
        return lambda path:SimpleNamespace(free=homefree if Path(path)==c.HERE else ramfree)

    def test_audit_floor1g_native_still3g(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td)
            with mock.patch.object(c.shutil,'disk_usage',side_effect=self.usage(stage)),mock.patch.object(c,'AUDIT_PHASE',True):
                c.check_budget(stage,{})
            with mock.patch.object(c.shutil,'disk_usage',side_effect=self.usage(stage)),mock.patch.object(c,'AUDIT_PHASE',False):
                with self.assertRaisesRegex(ValueError,'HOME preparation'):c.check_budget(stage,{})
            with mock.patch.object(c.shutil,'disk_usage',side_effect=self.usage(stage,homefree=1024**3)),mock.patch.object(c,'AUDIT_PHASE',True):
                with self.assertRaisesRegex(ValueError,'HOME preparation'):c.check_budget(stage,{})

    def test_failed_and_new_audits_share32m_cap_including_nested_projection(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td)
            for name,size in [('d-enabled-audit',16*1024**2),('d-enabled-audit-attempt2/counter-check-input',16*1024**2+1)]:
                d=stage/name;d.mkdir(parents=True)
                with (d/'fixture').open('wb') as f:f.truncate(size)
            with self.assertRaisesRegex(ValueError,'per-case budget including failed'):c.check_budget(stage,{})

    def test_ram_reserve_and_prep_caps_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td)
            with mock.patch.object(c.shutil,'disk_usage',side_effect=self.usage(stage,homefree=4*1024**3,ramfree=1024**3)):
                with self.assertRaisesRegex(ValueError,'RAM1GiB'):c.check_budget(stage,{})
            prep=stage/'prep';prep.mkdir()
            with (prep/'fixture').open('wb') as f:f.truncate(c.CAPS['preparation']+1)
            with mock.patch.object(c,'HERE',prep),mock.patch.object(c.shutil,'disk_usage',return_value=SimpleNamespace(free=4*1024**3)):
                with self.assertRaisesRegex(ValueError,'HOME preparation'):c.check_budget(stage,{})

    def test_driver_derivations_are_only_reviewed_import_and_attempt_changes(self):
        original=(c.old.HERE/'run_stream1792.py').read_text()
        expected=original.replace('import contract as c','import continuation as c').replace("cohort=Path(preparation['stage'])","c.require(args.role != 'd-enabled', 'D-enabled native is inherited; re-execution forbidden')\n    cohort=Path(preparation['stage'])")
        self.assertEqual((c.HERE/'run_continued.py').read_text(),expected)
        expected=(c.old.HERE/'audit_stream1792.py').read_text().replace('import contract as c','import continuation as c\nc.AUDIT_PHASE = True').replace("out=stage/(args.role+'-audit')",'out=c.audit_output(stage,args.role)').replace("schema='retained1792-stream-acceptance-v1',role=args.role,","schema='retained1792-stream-continuation-acceptance-v1',role=args.role,\n                    attempt=2 if args.role=='d-enabled' else 1,inherited_native=args.role=='d-enabled',")
        self.assertEqual((c.HERE/'audit_attempt.py').read_text(),expected)
        expected=inspect.getsource(c.old.verify_audit).replace("out=Path(stage)/(role+'-audit')",'out=audit_output(stage,role)').replace("receipt['schema'] == 'retained1792-stream-acceptance-v1'","receipt['schema'] == 'retained1792-stream-continuation-acceptance-v1'").replace("receipt=json.loads(accepted.read_text())","receipt=json.loads(accepted.read_text())\n    require(receipt['attempt'] == (2 if role == 'd-enabled' else 1) and receipt['inherited_native'] == (role == 'd-enabled'), 'explicit new attempt/native inheritance')")
        self.assertEqual(inspect.getsource(c.verify_audit),expected)

    def test_don_native_cannot_rerun_and_later_role_requires_new_prior_acceptance(self):
        import run_continued as run
        with tempfile.TemporaryDirectory() as td:
            p={'stage':td}
            for role in ('d-enabled','d-off'):
                argv=['test','--preparation','inert','--preparation-sha256','0'*64,'--role',role,'--execute']
                if role=='d-off':argv+=['--prior-audit-sha256','1'*64]
                with mock.patch.object(sys,'argv',argv),mock.patch.object(c,'load',return_value=(p,{})),mock.patch.object(c,'verify_audit',side_effect=ValueError('no accepted attempt2')),mock.patch.object(run,'owned_run',side_effect=AssertionError('native must not run')):
                    with self.assertRaisesRegex(ValueError,'re-execution forbidden' if role=='d-enabled' else 'no accepted attempt2'):run.main()
                self.assertFalse((Path(td)/role).exists())

    def test_new_driver_defaults_do_not_execute_or_open_admission(self):
        import audit_attempt as audit
        import run_continued as run
        for module in (run,audit):
            argv=['test','--preparation','inert','--preparation-sha256','0'*64,'--role','d-enabled']
            if module is audit:argv+=['--native-sha256',c.NATIVE_SHA]
            with mock.patch.object(sys,'argv',argv),mock.patch.object(c,'load',side_effect=AssertionError('must not open admission')):
                with self.assertRaisesRegex(ValueError,'default offline'):module.main()


if __name__=='__main__':unittest.main()
