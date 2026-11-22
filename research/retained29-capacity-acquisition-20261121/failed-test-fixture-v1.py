"""Bounded synthetic collector fixtures and real local flocks; no board calls."""
import copy
from datetime import datetime,timedelta,timezone
import errno
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import uuid
import run_retained29_capacity_study as c


class Coordinator(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.common=self.root/'common.lock';self.common.touch();self.calls=[];self.mode='PASS';self.identity_override=None
        self.output=self.root/'global';self.output.mkdir()
        self.study=dict(declared_utc='2026-11-20T00:00:00+00:00')
        study=self.write(self.root/'study.json',self.study)
        self.config=dict(schema=c.SCHEMA,state='HOST_TEST_ONLY',study=study,sources=c.sources(),output_root=str(self.output),images={})
        for image in c.analysis.IMAGES:
            d=self.root/image;d.mkdir();cohort=self.write(d/'cohort.json',dict(ledger_path=str(d/'acquisition-ledger.json')))
            templates=[]
            for visit in c.p.canonical_visits():
                body=dict(schema=c.p.ADMISSION_SCHEMA,state='bound-reviewed-promoted-COST',cohort=cohort,prior_results=None,
                    session=dict(visit_id=visit['id'],plan=visit['plan']),HOST_TEST_ONLY=True)
                templates.append(self.write(d/(visit['id']+'.json'),dict(schema=c.TEMPLATE_SCHEMA,image=image,visit_id=visit['id'],admission=body)))
            self.config['images'][image]=dict(cohort=cohort,templates=templates)
        self.record=self.write(self.root/'config.json',self.config)
        self.patches=[patch.object(c,'validate',side_effect=self.valid_config),
            patch.object(c.p,'validate_admission',side_effect=lambda a:c.require(a['prior_results'] is not None,'actual priors required')),
            patch.object(c.p,'verify_sources'),patch.object(c.p,'verify_prefix',side_effect=lambda a:[]),
            patch.object(c.p,'verify_session',side_effect=self.verified_session),
            patch.object(c.p.safe,'execute',side_effect=self.fake_safe),
            patch.object(c.p.base.maintained_session,'SESSION_LOCK',self.common)]
        for item in self.patches:item.start()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()

    def write(self,path,value):c.save(path,value);return c.p.binding(path)
    def valid_config(self,config,approved=True):
        c.require(config==self.config and config['sources']==c.sources(),'test exact source/config')
        return self.study
    def ledger(self):return json.loads((self.output/'matched-capacity-attempts.json').read_text())
    def cohort_path(self,a):return Path(c.read_record(a['cohort'])['ledger_path'])
    def verified_session(self,record,cohort,prior):
        result=c.read_record(record)
        c.require(result['state']=='HOST_TEST_ONLY_PASS' and result['safe_recovery_verified'] is True,'synthetic complete recovery')
        c.require(result['cohort']==cohort,'synthetic exact image cohort')
        return dict(record=record,result=result,boot_id=result['boot_id'])

    def fake_collector(self,a,output,input_record,engine):
        self.calls.append((a,output,input_record))
        return engine(a,output,None,None,operations=lambda *args:SimpleNamespace(),admission_record=input_record)

    def fake_safe(self,a,output,contract,guest,operations,admission_record):
        # Real unchanged common reservation, isolated to a fixture inode. The
        # wrapper factory therefore executes only after actual flock acquisition.
        with c.p.base.maintained_session.reservation():
            output.mkdir();global_entry=self.ledger()['entries'][-1];n=global_entry['order']
            start=datetime(2026,11,21,tzinfo=timezone.utc)+timedelta(seconds=10*n)
            reserved=dict(safe_engine_schema=c.p.safe.ENGINE_SCHEMA,state='reserved',supervisor_admission_record=admission_record,started_utc=start.isoformat())
            self.write(output/'session.json',reserved)
            operations()
            current=self.ledger()['entries'][-1]
            self.assertEqual(current['state'],'START');self.assertTrue(current['actual_common_reservation'])
            path=self.cohort_path(a);image=c.collector.ledger_read(path,a['cohort'])
            identity=self.identity_override or str(uuid.UUID(int=n+1,version=4))
            row=dict(order=global_entry['cohort_index'],id=global_entry['visit_id'],state='running',input=admission_record,result=None,boot_id=identity)
            image['entries'].append(row);self.write(path,image)
            if self.mode=='running':raise OSError('HOST_TEST simulated process loss with running authority')
            result=dict(state='HOST_TEST_ONLY_PASS',safe_recovery_verified=True,boot_id=identity,cohort=a['cohort'],
                started_utc=start.isoformat(),release_after_recovery_utc=(start+timedelta(seconds=1)).isoformat())
            if self.mode=='FAIL':result['state']='HOST_TEST_ONLY_FAIL'
            record=self.write(output/'session.json',result)
            row.update(state=self.mode,result=record);self.write(path,image)
            if self.mode=='FAIL':raise ValueError('HOST_TEST actual failed attempt, recovery completed')
            return result

    def advance(self,execute=True):
        return c.advance(self.record,execute=execute,reconcile_only=not execute,invoke=self.fake_collector)

    def test_actual_start_precedes_target_claim_and_pass_binds_both_ledgers(self):
        self.assertEqual(self.advance(),'PASS')
        entry=self.ledger()['entries'][0]
        self.assertEqual((entry['image'],entry['visit_id'],entry['state']),('small','pilot','PASS'))
        self.assertTrue(entry['dispatches'][0]['actual_common_reservation'])
        self.assertTrue(c.read_record(entry['dispatches'][0]['dispatch_record'])['not_actual_target_attempt'])

    def test_exact_common_busy_defers_without_acquisition_then_same_slot(self):
        inode=self.common.stat().st_ino
        with self.common.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.advance(),'DEFERRED')
        first=self.ledger()['entries'][0]
        self.assertFalse(first['actual_common_reservation']);self.assertFalse(Path(first['dispatches'][0]['output']).exists())
        self.assertEqual(self.common.stat().st_ino,inode)
        self.assertEqual(self.advance(),'PASS')
        entry=self.ledger()['entries'][0];self.assertEqual(len(entry['dispatches']),2)
        self.assertEqual([d['state'] for d in entry['dispatches']],['DEFERRED','PASS'])

    def test_arbitrary_eagain_not_mislabeled_common_busy(self):
        def wrong(*args,**kwargs):raise BlockingIOError(errno.EAGAIN,'not physical reservation')
        self.assertEqual(c.advance(self.record,execute=True,invoke=wrong),'BLOCKED')
        self.assertFalse(self.ledger()['entries'][0]['actual_common_reservation'])

    def test_crash_after_dispatch_before_acquisition_blocks_without_reexecution(self):
        original=c.save;raised=[]
        def interrupted(path,value):
            original(path,value)
            if Path(path).name=='matched-capacity-attempts.json' and value['entries'][-1]['state']=='DISPATCH' and not raised:
                raised.append(True);raise OSError('HOST_TEST crash after durable dispatch')
        with patch.object(c,'save',side_effect=interrupted),self.assertRaises(OSError):self.advance()
        self.assertEqual(len(self.calls),0)
        self.assertEqual(self.advance(execute=False),'BLOCKED')
        self.assertEqual(self.advance(),'BLOCKED');self.assertEqual(len(self.calls),0)

    def test_crash_after_authoritative_pass_reconciles_no_new_collector(self):
        original=c.save;raised=[]
        def interrupted(path,value):
            if Path(path).name=='matched-capacity-attempts.json' and value['entries'][-1]['state']=='PASS' and not raised:
                raised.append(True);raise OSError('HOST_TEST lost terminal global journal')
            original(path,value)
        with patch.object(c,'save',side_effect=interrupted),self.assertRaises(OSError):self.advance()
        self.assertEqual(self.ledger()['entries'][0]['state'],'START')
        calls=len(self.calls);self.assertEqual(self.advance(execute=False),'PASS');self.assertEqual(len(self.calls),calls)

    def test_running_authority_remains_blocked_and_no_retry(self):
        self.mode='running';self.assertEqual(self.advance(),'BLOCKED');calls=len(self.calls)
        self.assertEqual(self.advance(execute=False),'BLOCKED');self.assertEqual(self.advance(),'BLOCKED')
        self.assertEqual(len(self.calls),calls)

    def test_actual_failure_stops_whole_study_with_history_preserved(self):
        self.mode='FAIL';self.assertEqual(self.advance(),'FAIL');calls=len(self.calls)
        self.assertEqual(self.advance(),'FAIL');self.assertEqual(len(self.calls),calls)
        self.assertEqual(len(self.ledger()['entries'][0]['dispatches']),1)

    def test_cross_image_duplicate_uuid_never_passes(self):
        self.assertEqual(self.advance(),'PASS')
        self.identity_override=self.ledger()['entries'][0]['boot_id']
        with self.assertRaisesRegex(ValueError,'unique'):self.advance()
        calls=len(self.calls)
        with self.assertRaisesRegex(ValueError,'unique'):self.advance(execute=False)
        self.assertEqual(len(self.calls),calls)

    def test_fixed_image_order_and_global_lock(self):
        for ignored in range(6):self.assertEqual(self.advance(),'PASS')
        self.assertEqual([e['image'] for e in self.ledger()['entries']],['small','large','small','large','large','small'])
        with (self.output/'matched-capacity-coordinator.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.advance()
        self.assertEqual(len(self.calls),6)

    def test_misordered_deferred_slot_and_copied_source_corruption_rejected(self):
        with self.common.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);self.assertEqual(self.advance(),'DEFERRED')
        value=self.ledger();value['entries'][0]['image']='large';self.write(self.output/'matched-capacity-attempts.json',value)
        with self.assertRaisesRegex(ValueError,'pending slot'):self.advance()
        value['entries'][0]['image']='small';self.write(self.output/'matched-capacity-attempts.json',value)
        path=Path(value['entries'][0]['dispatches'][0]['directory'])/'coordinator-sources/coordinator';path.write_text('HOST_TEST corruption')
        with self.assertRaisesRegex(ValueError,'source snapshot'):self.advance()
        self.assertEqual(len(self.calls),1)

    def test_source_change_prevents_dispatch_and_unbound_outcome_redirect_rejected(self):
        bad=copy.deepcopy(self.config);bad['sources']['coordinator']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source drift'):c.validate.__wrapped__(bad) if hasattr(c.validate,'__wrapped__') else self.valid_config(bad)
        self.assertFalse((self.output/'matched-capacity-attempts.json').exists())
        self.mode='running';self.assertEqual(self.advance(),'BLOCKED')
        value=self.ledger();value['entries'][0]['dispatches'][-1]['input']['path']='/untrusted/admission.json';self.write(self.output/'matched-capacity-attempts.json',value)
        with self.assertRaisesRegex(ValueError,'unsigned redirection'):self.advance(execute=False)


if __name__=='__main__':unittest.main()
