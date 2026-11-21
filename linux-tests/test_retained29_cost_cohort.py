"""Synthetic closed-session/qualification and local-ledger tests; no board calls."""
import copy
import fcntl
from contextlib import contextmanager
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import retained29_cost_cohort_protocol as p
import run_retained29_cost_cohort as client
import test_retained29_cost_protocol as old


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')
    return p.binding(path)


def idle(value):
    return dict(boot_id=value,guard=None,control_sha256=p.base.RUNNER_SHA,helper_sha256=p.base.HELPER_SHA,
                active_control=[],active_script=[],active_helper=[])


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.hardware=copy.deepcopy(old.HARDWARE)
        self.artifacts={n:write(self.root/(n+'.json'),{'HOST_VERIFY':n}) for n in ('nbf','package','bit','fit','kernel_verification')}
        self.source=write(self.root/'observer-source.json',{'HOST_VERIFY':'source only'})
        self.execution=write(self.root/'observer-execution.json',{'HOST_VERIFY':'synthetic runtime execution'})
        self.runtime=dict(profile='HOST_VERIFY-SYNTHETIC-OBSERVER',runner_sha256='9'*64,source_proof=self.source,execution_proof=self.execution)
        clocks=write(self.root/'clocks.json',dict(scope='actual-FPGA-clock-topology',bit_sha256=self.artifacts['bit']['sha256'],
            core_hz=1,axi_hz=2,l1i_bytes=32768,l1d_bytes=32768,l1_sets=64,l1_ways=8,line_bytes=64,l2_bytes=16384,HOST_VERIFY=True))
        self.q=dict(schema='bp-retained29-physical-capacity-qualification-v1',state='PASS root-reviewed actual physical capacity/source/clock qualification',
            platform='FPGA',closed_utc='2026-11-20T23:00:00+00:00',HOST_VERIFY=True,hardware=self.hardware,artifacts=self.artifacts,observer_runtime=self.runtime,
            canonical_fullcore=self.source,source_bridge=self.source,clock_topology=clocks,cases=[])
        for role in ('d-enabled','d-off','i-enabled'):
            n=self.hardware['retained'][role[0]+'_lines'];values=([0,n,0,n,0,8*n] if role[0]=='d' else [n,0,n,0,8*n,0]) if role!='d-off' else [0]*6
            self.q['cases'].append(dict(role=role,lines=n,counter_words=values,complete=True,all_payloads_checked=True,
                observer_stable=True,saturated=False,recovery_verified=True,primary_use_rejected=role=='d-off',
                receipt=self.execution,fixture=self.source,checker=self.source))
        self.qpath=self.root/'physical.json';self.qrecord=write(self.qpath,self.q)
    def tearDown(self):self.tmp.cleanup()
    @contextmanager
    def approvals(self):
        with patch.dict(p.APPROVED_PHYSICAL_QUALIFICATIONS,{self.artifacts['bit']['sha256']:self.qrecord['sha256']},clear=True),patch.dict(p.APPROVED_OBSERVER_RUNTIMES,{self.runtime['profile']:{k:self.runtime[k] for k in ('runner_sha256','source_proof','execution_proof')}},clear=True):yield


class Physical(Fixture):
    def test_production_allowlists_empty_and_missing_qualification_rejected(self):
        self.assertEqual(p.APPROVED_PHYSICAL_QUALIFICATIONS,{})
        self.assertEqual(p.APPROVED_OBSERVER_RUNTIMES,{})
        with self.assertRaises(ValueError):p.physical_qualification(None,self.hardware,self.artifacts)
        with self.assertRaisesRegex(ValueError,'allowlist'):p.physical_qualification(self.qrecord,self.hardware,self.artifacts)
    def test_complete_synthetic_qualification_only_under_explicit_test_allowlists(self):
        with self.approvals():p.physical_qualification(self.qrecord,self.hardware,self.artifacts)
    def test_wrong_image_capacity_instability_or_unexecuted_profile_rejected(self):
        original=copy.deepcopy(self.q)
        changes=[lambda q:q['hardware'].update(l2_bytes=4096),lambda q:q['cases'][0]['counter_words'].__setitem__(1,1),
            lambda q:q['cases'][0].update(observer_stable=False),lambda q:q.update(observer_runtime=None),
            lambda q:q['observer_runtime'].update(runner_sha256=p.base.RUNNER_SHA),lambda q:q['cases'][1].update(primary_use_rejected=False)]
        for change in changes:
            self.q=copy.deepcopy(original);change(self.q);self.qrecord=write(self.qpath,self.q)
            with self.approvals(),self.assertRaises(ValueError):p.physical_qualification(self.qrecord,self.hardware,self.artifacts)


class Plan(Fixture):
    def make(self,index=0):
        visits=p.canonical_visits();legacy=write(self.root/'legacy-cohort.json',dict(visits=visits))
        cohort=dict(schema=p.COHORT_SCHEMA,state='predeclared-reviewed',declared_utc='2026-11-21T00:00:00+00:00',
            sources=p.source_hashes(),cost_sources=p.cost.source_hashes(),program_sha256=p.cost.ELF_SHAS,
            artifacts=self.artifacts,hardware=self.hardware,visits=visits,application_runtime=p.APPLICATION_RUNTIME,
            legacy_cohort=legacy,ledger_path=str(self.root/'acquisition-ledger.json'),physical_qualification=self.qrecord)
        record=write(self.root/'cohort.json',cohort)
        inner=dict(visit_id=visits[index]['id'],plan=visits[index]['plan'],sources=p.cost.source_hashes(),
            artifacts=self.artifacts,hardware=self.hardware,cohort_record=legacy)
        a=dict(schema=p.ADMISSION_SCHEMA,state='bound-reviewed-promoted-COST',sources=p.source_hashes(),session=inner,cohort=record,prior_results=[])
        return a,cohort
    def test_fixed15_order_and_three_rotations(self):
        visits=p.canonical_visits();self.assertEqual(len(visits),16)
        self.assertEqual([v['plan']['rotation'] for v in visits[1:]], [0]*5+[2]*5+[4]*5)
        self.assertEqual([v['id'] for v in visits[1:6]],['r0-'+w for w in p.ORDERS[0]])
        self.assertTrue(all(sum(v['plan']['workload']==w for v in visits[1:])==3 for w in p.cost.WORKLOADS))
    def test_later_physical_qualification_cannot_become_prior_prerequisite(self):
        self.q['closed_utc']='2026-11-22T00:00:00+00:00';self.qrecord=write(self.qpath,self.q)
        a,cohort=self.make()
        with self.approvals(),self.assertRaisesRegex(ValueError,'prerequisite closes before'):p.cohort_record(a)

    def test_wrong_cohort_order_or_missing_passed_pilot_cannot_promote(self):
        a,cohort=self.make(1)
        with self.approvals(),patch.object(p.cost,'validate_admission',return_value={}),patch.object(p,'verify_artifacts'):
            with self.assertRaisesRegex(ValueError,'prior-slot prefix'):p.static_admission(a)
            cohort['visits'][1],cohort['visits'][2]=cohort['visits'][2],cohort['visits'][1]
            a['cohort']=write(self.root/'cohort.json',cohort)
            with self.assertRaisesRegex(ValueError,'fixed pilot plus15'):p.cohort_record(a)


class Ledger(Fixture):
    def ops(self,index,prior):
        ops=object.__new__(client.Operations)
        ops.wrapper=dict(cohort=self.qrecord,prior_results=prior)
        ops.input_record=self.source;ops.ledger_lock=None;ops.ledger=None;ops.entry=None
        self.cohort=dict(ledger_path=str(self.root/'acquisition-ledger.json'))
        return ops,dict(order=index,id=p.canonical_visits()[index]['id'])
    def test_durable_claim_before_stage_and_failure_blocks_retry_nextslot(self):
        ops,visit=self.ops(0,[])
        def stage():
            disk=json.loads(Path(self.cohort['ledger_path']).read_text())
            self.assertEqual(disk['entries'][0]['state'],'running')
        with patch.object(p,'static_admission',return_value=({},self.cohort,visit)),patch.object(p.safe.Operations,'stage',side_effect=stage) as called:
            try:ops.stage();called.assert_called_once();ops.finish_attempt(False,error='HOST_VERIFY injected failure')
            finally:ops.close_ledger()
        for index in (0,1):
            other,visit=self.ops(index,[])
            with patch.object(p,'static_admission',return_value=({},self.cohort,visit)),patch.object(p.safe.Operations,'stage') as called:
                try:
                    with self.assertRaises(ValueError):other.stage()
                    called.assert_not_called()
                finally:other.close_ledger()
    def test_failed_pass_fsync_keeps_cohort_lock_until_fail_durable(self):
        ops,visit=self.ops(0,[])
        with patch.object(p,'static_admission',return_value=({},self.cohort,visit)),patch.object(p.safe.Operations,'stage'):
            ops.stage()
        calls=[];waits=[]
        actual=ops.finish_attempt
        def injected(success,*args,**kwargs):
            calls.append(success)
            if success:
                actual(success,*args,**kwargs)
                raise OSError('HOST_VERIFY PASS replaced but fsync failed')
            if calls.count(False)==1:raise OSError('HOST_VERIFY FAIL reporting also unavailable')
            return actual(success,*args,**kwargs)
        def wait(seconds):
            waits.append(seconds)
            with (self.root/'acquisition-ledger.lock').open('a+') as other:
                with self.assertRaises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            ops.finish_attempt=injected
            try:
                ops.finish_attempt(True,result=self.execution)
            except OSError as error:client.persist_failed_attempt(ops,error,self.execution,wait)
            self.assertEqual(calls,[True,False,False]);self.assertEqual(waits,[10])
            self.assertEqual(json.loads((self.root/'acquisition-ledger.json').read_text())['entries'][0]['state'],'FAIL')
        finally:ops.close_ledger()
        with (self.root/'acquisition-ledger.lock').open('a+') as other:fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_reused_actual_uuid_refused_before_guest_handler(self):
        value=str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError,'reused'):p.validate_fresh_boot(idle(value),{value})
        self.assertEqual(p.validate_fresh_boot(idle(value),set()),value)
    def test_actual_catchable_signal_records_fail_in_bounded_host_child(self):
        script=r"""
import json,os,signal,tempfile
from pathlib import Path
from unittest.mock import patch
import retained29_cost_cohort_protocol as p
import run_retained29_cost_cohort as c
with tempfile.TemporaryDirectory() as td:
 root=Path(td);ops=object.__new__(c.Operations)
 ops.entry=dict(order=0,id='pilot',state='running');ops.ledger=dict(entries=[ops.entry])
 ops.ledger_path=root/'ledger.json';ops.ledger_lock=(root/'ledger.lock').open('a+')
 p.safe.journal(ops.ledger_path,ops.ledger)
 def engine(a,out,protocol,guest,operations,admission_record):
  operations();os.kill(os.getpid(),signal.SIGTERM)
 with patch.object(c,'Operations',return_value=ops):
  try:c.execute({},root,{},engine=engine,failure_wait=lambda n:None)
  except KeyboardInterrupt:pass
  else:raise AssertionError('SIGTERM not propagated as failure')
 assert json.loads(ops.ledger_path.read_text())['entries'][0]['state']=='FAIL'
 print('HOST_ONLY_COHORT_SIGTERM_PASS')
"""
        result=subprocess.run([sys.executable,'-c',script],cwd=p.base.ROOT/'linux-tests',
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=8)
        self.assertEqual(result.returncode,0,result.stdout.decode())
        self.assertIn(b'HOST_ONLY_COHORT_SIGTERM_PASS',result.stdout)

    def test_busy_reservation_never_constructs_operations_or_claims_slot(self):
        def busy(*args,**kwargs):raise BlockingIOError('HOST_VERIFY common reservation busy')
        with patch.object(client,'Operations') as construct:
            with self.assertRaises(BlockingIOError):client.execute({},self.root/'no-output',self.source,engine=busy)
            construct.assert_not_called();self.assertFalse((self.root/'acquisition-ledger.json').exists())


class Complete(unittest.TestCase):
    @classmethod
    def setUpClass(cls):old.fixtures()
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.cohort=write(self.root/'cohort.json',{'HOST_VERIFY':True});self.accepted=[]
    def tearDown(self):self.tmp.cleanup()
    def static(self,a):
        visit=next(v for v in p.canonical_visits() if v['id']==a['session']['visit_id'])
        return {},dict(declared_utc='2026-11-21T00:00:00+00:00'),visit
    def session(self,index):
        visit=p.canonical_visits()[index];plan=visit['plan'];inner=old.minimal(plan['role'],plan['workload'],plan['rotation'])
        inner.update(sources={},legacy_sources={},cohort_record={},visit_id=visit['id'])
        outer=dict(session=inner,sources={},cohort=self.cohort,prior_results=[x['record'] for x in self.accepted])
        out=self.root/visit['id'];out.mkdir()
        input_record=write(out/'input.json',outer);console=out/'console.log';console.write_text(old.console(inner))
        value=str(uuid.UUID(int=index+1,version=4))
        identity=out/'0001-remote-identity.log';identity.write_text('HOST_VERIFY synthetic identity\n')
        guard=write(out/'0002-guard-probe.log',idle(value))
        publication=write(out/'safe-publication.json',dict(state='verified old2dd/helper/overlay/operating recovery',label='final',power_pending=None,own_guest=None,inventory={'HOST_VERIFY':True}))
        result=dict(schema=p.SCHEMA,state=p.SUCCESS_STATE,safe_engine_schema=p.safe.ENGINE_SCHEMA,safe_recovery_verified=True,
            recovery='complete before reservation release',guest_boots=1,performance_accepted=False,supervisor_admission=outer,
            admission={},supervisor_sources={},supervisor_admission_record=input_record,
            guest=dict(p.cost.complete_console(console.read_text(),inner),runner_exit=0,guest_exit=0,runner_signal=None,shell_return=True,
                console=p.binding(console),executed_case_ids=[c['id'] for c in plan['cases']]),
            started_utc='2026-11-21T%02d:00:00+00:00'%index,release_after_recovery_utc='2026-11-21T%02d:01:00+00:00'%index,
            reservation_release_utc='2026-11-21T%02d:01:00+00:00'%index,operation_logs={identity.name:p.binding(identity),'0002-guard-probe.log':guard},
            operation_journal=publication,**p.result_metadata(outer,{}))
        return write(out/'session.json',result),result,value
    def build(self,n=16):
        for index in range(n):
            record,result,value=self.session(index)
            self.accepted.append(dict(record=record,result=result,boot_id=value,visit=p.canonical_visits()[index]))
        entries=[dict(order=i,id=x['visit']['id'],state='PASS',result=x['record'],boot_id=x['boot_id']) for i,x in enumerate(self.accepted)]
        return write(self.root/'ledger.json',dict(schema='bp-retained29-cost-acquisition-ledger-v1',cohort=self.cohort,entries=entries))
    def verify(self,ledger):
        with patch.object(p,'static_admission',side_effect=self.static),patch.object(p.cost,'acquisition_ready'):
            return p.verify_complete(self.cohort,ledger)
    def test_all16_actual_console_rows_boots_and_recovery_required(self):
        ledger=self.build();proof=self.verify(ledger)
        self.assertTrue(proof['primary_analysis_ready']);self.assertEqual(proof['performance_boots'],15)
        self.assertEqual(len(set(proof['acquisition_boot_ids'])),16)
    def test_passing_subset_rejected_without_primary_admission(self):
        with self.assertRaisesRegex(ValueError,'all16'):self.verify(self.build(15))
    def test_earlier_failed_result_wrongorder_and_reused_uuid_rejected(self):
        ledger=self.build();original=copy.deepcopy(json.loads(Path(ledger['path']).read_text()))
        for change in (lambda x:x['entries'][0].update(state='FAIL'),lambda x:x['entries'].reverse()):
            bad=copy.deepcopy(original);change(bad);rec=write(Path(ledger['path']),bad)
            with self.assertRaises(ValueError):self.verify(rec)
        write(Path(ledger['path']),original)
        second=self.accepted[1];path=Path(second['record']['path']).parent/'0002-guard-probe.log'
        raw=idle(self.accepted[0]['boot_id']);record=write(path,raw)
        result=copy.deepcopy(second['result']);result['operation_logs'][path.name]=record
        changed=write(Path(second['record']['path']),result)
        with patch.object(p,'static_admission',side_effect=self.static),patch.object(p.cost,'acquisition_ready'):
            with self.assertRaisesRegex(ValueError,'reused actual acquisition'):p.verify_session(changed,self.cohort,self.accepted[:1])
    def test_missing_recovery_or_whole_row_rejects_complete_session(self):
        record,result,_=self.session(0)
        for change in (lambda x:x.update(safe_recovery_verified=False),lambda x:x.update(state='FAIL')):
            bad=copy.deepcopy(result);change(bad);changed=write(Path(record['path']),bad)
            with patch.object(p,'static_admission',side_effect=self.static),patch.object(p.cost,'acquisition_ready'),self.assertRaises(ValueError):p.verify_session(changed,self.cohort,[])
        console=Path(result['guest']['console']['path']);text=console.read_text();console.write_text('\n'.join(s for s in text.splitlines() if '_WHOLE ' not in s)+'\n')
        result['guest']['console']=p.binding(console);changed=write(Path(record['path']),result)
        with patch.object(p,'static_admission',side_effect=self.static),patch.object(p.cost,'acquisition_ready'),self.assertRaises(ValueError):p.verify_session(changed,self.cohort,[])


if __name__=='__main__':unittest.main()
