"""Offline fixed old2dd RPC and real-flock fault tests; no board calls."""
import copy
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import retained29_protocol as p
import retained29_safe_guard as guard
import retained29_safe_session as s
import retained29_safe_functional_protocol as functional
import retained29_cost_protocol as cost
import run_retained29_safe_functional as fclient
import run_retained29_cost_session as cclient
import test_retained_capacity_recovery_v3 as prior

BIT='a'*64

def idle(boot=prior.BOOT_A):
    return dict(boot_id=boot,guard=None,control_sha256=p.RUNNER_SHA,helper_sha256=p.HELPER_SHA,
                active_control=[],active_script=[],active_helper=[])


class GuardRPC(prior.ActualGuardRPC):
    """Reuse only inert temp-proc setup; execute the NEW fixed old2dd RPC."""
    def setUp(self):
        super().setUp()
        self.code=guard.RPC
        for before,after in [("pathlib.Path('/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq')",self.board),
            ("pathlib.Path('/home/xilinx/bp-logs')",self.logs),("pathlib.Path('/proc')",self.proc)]:
            self.code=self.code.replace(before,'pathlib.Path('+repr(str(after))+')')
        # Inert NBF bytes keep this fixture small. ONLY the RPC's expected NBF
        # literal is substituted; old2dd/helper checks use their actual bytes.
        image=self.board/'kernel29.nbf';image.write_bytes(b'HOST_VERIFY inert kernel NBF\n')
        self.nbf=p.binding(image)['sha256'];self.code=self.code.replace(p.NBF_SHA,self.nbf)
        accepted=json.loads((p.ROOT/'research/retained-capacity-physical-diagnostic-20261121/prepared03/diagnostic.DRAFT.json').read_text())
        rollback=accepted['rollback_runner'];(self.board/'control-program').write_bytes(Path(rollback['path']).read_bytes())
        rc,self.preflight=self.rpc('probe');self.assertEqual(rc.returncode,0,rc.stderr)
        self.context=dict(token='1234567890abcdef',image='kernel29.nbf',pid=1359,
            log=str(self.logs/'kernel29-interactive-20261121T130000Z-1359.log'),bit_sha256=BIT,preflight=self.preflight)
    def create(self,pid=1359,live=True):
        self.lock.mkdir();(self.lock/'owner').write_text(str(pid)+'\n')
        if live:
            self.active_helper.write_text(str(pid)+'\n');where=self.proc/str(pid);where.mkdir()
            argv=['bash',str(self.board/'run-blackparrot-interactive'),'kernel29.nbf',self.nbf,p.RUNNER_SHA,'3600000',BIT]
            (where/'cmdline').write_bytes(b'\0'.join(s.encode() for s in argv)+b'\0');(where/'status').write_text('PPid:\t77\n')
    def test_live_bash_helper_before_guard_is_not_idle(self):
        self.create();(self.lock/'owner').unlink();self.lock.rmdir()
        rc,value=self.rpc('probe');self.assertEqual(rc.returncode,0)
        with self.assertRaisesRegex(ValueError,'helper'):guard.idle(value)
    def test_owned_oldboot_guard_and_descendants_removed_only_after_newboot(self):
        self.create();witness=self.witness();self.reboot();rc,value=self.rpc('remove-owned-stale',self.context,witness)
        self.assertEqual(rc.returncode,0,rc.stderr);self.assertTrue(value['removed']);self.assertTrue(value['durable'])
        self.assertEqual(p.binding(self.board/'control-program')['sha256'],p.RUNNER_SHA)
    def test_wrong_bound_helper_argv_or_helper_hash_refused(self):
        self.create();path=self.proc/'1359/cmdline';path.write_bytes(path.read_bytes().replace(b'3600000',b'300000'))
        rc,_=self.rpc('witness',self.context);self.assertNotEqual(rc.returncode,0)
        (self.board/'run-blackparrot-interactive').write_bytes(b'changed')
        rc,_=self.rpc('witness',self.context);self.assertNotEqual(rc.returncode,0)
    def test_observer_runner_refused(self):
        candidate=json.loads((p.ROOT/'research/retained-capacity-physical-diagnostic-20261121/prepared03/diagnostic.DRAFT.json').read_text())
        (self.board/'control-program').write_bytes(Path(candidate['runner']['path']).read_bytes())
        rc,probe=self.rpc('probe');self.assertEqual(rc.returncode,0)
        with self.assertRaises(ValueError):guard.idle(probe)


class Engine(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.output=self.root/'session'
        self.lock=self.root/'common.lock';self.lock.write_text('agreed inode');self.inode=self.lock.stat().st_ino
        self.events=[];self.a=dict(role='unit-HOST_VERIFY');self.admission=self.root/'input.json';self.admission.write_text(json.dumps(self.a))
        self.core=dict(host='xilinx@192.168.4.35',sources={},artifacts=dict(bit=dict(sha256=BIT)))
        self.contract=SimpleNamespace(SCHEMA='HOST_VERIFY-safe-session',SUCCESS_STATE='PASS-HOST_VERIFY',
            validate_admission=lambda a:self.core,bound_sources=lambda a:{},acquisition_ready=lambda *a:None,
            verify_sources=lambda a:None,verify_artifacts=lambda a:None,result_metadata=lambda *a:dict(role='HOST_VERIFY'))
        self.patches=[patch.object(p.maintained_session,'SESSION_LOCK',self.lock),patch.object(s.maintained,'environment',lambda a:{})]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()
    def busy(self):
        with self.lock.open('r') as stream:
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return True
            fcntl.flock(stream,fcntl.LOCK_UN);return False
    def run_session(self,factory=None,wait=None):
        if wait is None:wait=lambda _:self.fail('unexpected held recovery in host fixture; bounded test stop')
        return s.execute(self.a,self.output,self.contract,lambda *a:None,operations=factory or self.factory(),
                         recovery_wait=wait,admission_record=p.binding(self.admission))
    def factory(self,fail_final=False,fail_guest=False):
        outer=self
        class Fake:
            def __init__(self,*args):self.changed=False;self.finals=0
            def stage(self):outer.assertTrue(outer.busy());outer.events.append('stage');self.changed=True
            def remote_identity(self):outer.assertTrue(outer.busy());outer.events.append('old2dd/de54')
            def requires_recovery(self):return self.changed
            def recover(self,label):
                outer.assertTrue(outer.busy());outer.events.append(label)
                if label=='final':
                    self.finals+=1
                    if fail_final and self.finals==1:raise ValueError('unconfirmed final recovery')
            def guest(self):
                outer.assertTrue(outer.busy());outer.events.append('guest')
                if fail_guest:raise ValueError('guest failure')
                return dict(HOST_VERIFY=True)
        return Fake
    def test_success_full_order_inode_and_release(self):
        result=self.run_session();self.assertEqual(result['state'],'PASS-HOST_VERIFY')
        self.assertEqual(self.events,['stage','initial','old2dd/de54','guest','final']);self.assertFalse(self.busy())
        self.assertEqual(self.lock.stat().st_ino,self.inode);self.assertTrue(result['safe_recovery_verified'])
    def test_busy_lock_creates_no_output_or_operations(self):
        with self.lock.open('r') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises((ValueError,BlockingIOError)):self.run_session()
        self.assertFalse(self.output.exists());self.assertEqual(self.events,[])
    def test_failed_final_holds_until_explicit_recovery_no_guest_retry(self):
        def wait(seconds):
            self.assertTrue(self.busy());self.assertLessEqual(seconds,30)
            state=json.loads((self.output/'session.json').read_text())
            self.assertEqual(state['state'],'recovery-required-reservation-held');self.assertNotIn('reservation_release_utc',state)
            s.request_recovery(self.output)
        with self.assertRaisesRegex(ValueError,'unconfirmed'):self.run_session(self.factory(fail_final=True),wait)
        state=json.loads((self.output/'session.json').read_text());self.assertEqual(state['state'],'FAIL')
        self.assertTrue(state['safe_recovery_verified']);self.assertEqual(self.events.count('guest'),1)
        self.assertEqual(self.events.count('final'),2);self.assertFalse(self.busy())
    def test_journal_enospc_keeps_lock_until_repair_and_request(self):
        real=s.journal;fault={'on':True};waits=[]
        def journal(path,value):
            if path.name=='session.json' and value['state'].startswith('recovery-') and fault['on']:raise OSError('synthetic ENOSPC')
            return real(path,value)
        def wait(seconds):
            self.assertTrue(self.busy());self.assertNotIn('final',self.events);waits.append(seconds)
            if len(waits)==1:fault['on']=False
            else:s.request_recovery(self.output)
        with patch.object(s,'journal',side_effect=journal),self.assertRaises(OSError):self.run_session(wait=wait)
        state=json.loads((self.output/'session.json').read_text());self.assertEqual(state['state'],'FAIL')
        self.assertEqual(self.events.count('guest'),1);self.assertEqual(self.events.count('final'),1);self.assertFalse(self.busy())
    def request_fault(self,operation):
        read=Path.read_text;replace=Path.replace;fault={'used':False};waits=[]
        def read_text(path,*args,**kwargs):
            if operation=='read' and path.name=='recovery-request.json' and not fault['used']:
                fault['used']=True;raise OSError('synthetic request read EIO')
            return read(path,*args,**kwargs)
        def replace_path(path,target):
            if operation=='rename' and path.name=='recovery-request.json' and not fault['used']:
                fault['used']=True;raise OSError('synthetic request rename EIO')
            return replace(path,target)
        def wait(seconds):
            self.assertTrue(self.busy());self.assertEqual(self.events.count('final'),1);waits.append(seconds)
            if not (self.output/'recovery-request.json').exists():s.request_recovery(self.output)
        with patch.object(Path,'read_text',read_text),patch.object(Path,'replace',replace_path),self.assertRaises(ValueError):
            self.run_session(self.factory(fail_final=True),wait)
        self.assertTrue(fault['used']);self.assertGreaterEqual(len(waits),2);self.assertFalse(self.busy())
    def test_request_read_eio_holds_reservation(self):self.request_fault('read')
    def test_request_rename_eio_holds_reservation(self):self.request_fault('rename')
    def test_verified_recovery_terminal_journal_error_is_fail(self):
        real=s.journal;fault={'used':False}
        def journal(path,value):
            if value.get('state')=='PASS-HOST_VERIFY' and not fault['used']:
                fault['used']=True;raise OSError('terminal write failure')
            return real(path,value)
        with patch.object(s,'journal',side_effect=journal),self.assertRaises(OSError):self.run_session()
        state=json.loads((self.output/'session.json').read_text());self.assertEqual(state['state'],'FAIL')
        self.assertTrue(state['safe_recovery_verified']);self.assertIn('final',self.events);self.assertFalse(self.busy())
    def test_failed_guest_recovers_then_closes_fail_without_retry(self):
        with self.assertRaisesRegex(ValueError,'guest failure'):self.run_session(self.factory(fail_guest=True))
        state=json.loads((self.output/'session.json').read_text());self.assertEqual(state['state'],'FAIL')
        self.assertTrue(state['safe_recovery_verified']);self.assertEqual(self.events.count('guest'),1)
        self.assertEqual(self.events.count('final'),1);self.assertFalse(self.busy())


class ActualPower(unittest.TestCase):
    setUp=Engine.setUp
    tearDown=Engine.tearDown
    busy=Engine.busy
    def factory(self,partial=False,unknown=False):
        outer=self
        class Fake(s.Operations):
            def __init__(self,a,core,output,env,sources,guest):
                self.a=core;self.admission=core;self.wrapper=a;self.output=output;self.env=env;self.sources=sources
                self.token='1234567890abcdef';self.power_pending=None;self.own_guest=None;self.guard_witness=None;self.guard_cleanup=None
                self.mutation_started=False;self.stage_complete=False;self.original=None;self.powers=0;self.off=False;self.current=idle()
                self.outer=dict(package_bundle={},load_stem='blackparrot_bd_1')
            def probe(self):
                outer.assertTrue(outer.busy())
                if self.off:raise s.BoardUnreachable('synthetic SSH off after own power')
                current=copy.deepcopy(self.current)
                if unknown:current['active_helper']=[999]
                return current
            def stage(self):self.inspect();self.stage_complete=True
            def remote_identity(self):outer.events.append('old2dd/de54')
            def audit(self,label):return {}
            def _maintained_power(self,label,expected):
                outer.assertTrue(outer.busy());outer.assertIsNotNone(self.power_pending)
                receipt=json.loads((self.output/'safe-publication.json').read_text())
                outer.assertEqual(receipt['power_pending']['authority']['kind'],'verified-idle-preflight')
                self.powers+=1;outer.events.append(label)
                if partial and self.powers==1:self.off=True;raise ValueError('own initial power partial failure')
                self.off=False;self.current=idle('%08d-0000-0000-0000-000000000000'%self.powers)
            def guest(self):outer.events.append('guest');return dict(HOST_VERIFY=True)
        return Fake
    def run_session(self,factory=None,wait=None):
        with patch.object(s.stage,'plan',return_value=dict(action='reuse-complete')):
            return Engine.run_session(self,factory,wait)
    # Avoid re-running Engine cases with different internal order expectations.
    def test_success_full_order_inode_and_release(self):
        result=self.run_session();self.assertTrue(result['safe_recovery_verified']);self.assertFalse(self.busy())
    def test_initial_partial_power_before_guest_recovers_before_unlock(self):
        with self.assertRaisesRegex(ValueError,'initial power'):self.run_session(self.factory(partial=True))
        state=json.loads((self.output/'session.json').read_text());self.assertEqual(state['state'],'FAIL')
        self.assertTrue(state['safe_recovery_verified']);self.assertNotIn('guest',self.events)
        self.assertIn('resume-owned-interrupted-power',self.events);self.assertIn('final',self.events);self.assertFalse(self.busy())
    def test_live_helper_before_guard_preflight_gains_no_power_authority(self):
        with self.assertRaisesRegex(ValueError,'helper'):self.run_session(self.factory(unknown=True))
        self.assertEqual(self.events,[]);self.assertFalse(self.busy())
    def test_undurable_witness_or_host_journal_never_authorizes_power(self):
        op=self.factory()(self.a,self.core,self.root,{}, {},None)
        op.guard_witness=dict(guard_durable=False,sync_complete=False)
        with patch.object(op,'_maintained_power') as power:
            with self.assertRaisesRegex(ValueError,'durable'):op._power('quiesce',BIT,dict(kind='bound-own-helper-witness',preflight=idle()))
            power.assert_not_called()
        with patch.object(op,'record',side_effect=OSError('fsync error')),patch.object(op,'_maintained_power') as power:
            with self.assertRaises(OSError):op._power('initial',BIT,dict(kind='verified-idle-preflight',preflight=idle()))
            self.assertIsNone(op.power_pending);power.assert_not_called()
    def test_unreachable_without_own_power_and_reachable_unknown_guard_not_reset(self):
        op=self.factory()(self.a,self.core,self.root,{}, {},None)
        with patch.object(op,'probe',side_effect=s.BoardUnreachable('unowned')),patch.object(op,'_power') as power:
            with self.assertRaisesRegex(ValueError,'without our interrupted'):op.resolve_idle_for_final(BIT)
            power.assert_not_called()
        current=idle();current['guard']=dict(pid=999)
        with patch.object(op,'probe',return_value=current),patch.object(op,'_power') as power:
            with self.assertRaisesRegex(ValueError,'no started own'):op.resolve_idle_for_final(BIT)
            power.assert_not_called()


class Wrappers(unittest.TestCase):
    def test_functional_guest_delegates_only_unchanged_transport(self):
        core=dict(HOST_VERIFY=True)
        with patch.object(fclient.original,'run_guest',return_value='ok') as guest,patch.object(fclient.original,'execute') as unsafe:
            self.assertEqual(fclient.guest({},core,Path('/tmp/not-created'),{},Path('/tmp/inert')),'ok')
            guest.assert_called_once_with(core,Path('/tmp/not-created'),{},runner=Path('/tmp/inert'));unsafe.assert_not_called()
    def test_both_new_drivers_call_only_safe_engine(self):
        for client,contract in ((fclient,functional),(cclient,cost)):
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'input.json';path.write_text('{}');output=Path(tmp)/'never'
                with patch.object(s,'execute') as execute,patch.object(s.maintained,'execute') as unsafe:
                    client.main([str(path),'--execute',str(output)])
                    self.assertIs(execute.call_args[0][2],contract);unsafe.assert_not_called()
                    self.assertFalse(output.exists())
    def test_unconfirmed_or_legacy_completion_never_qualifies_safe_gate(self):
        for changes in (dict(schema='bp-retained29-functional-session-v2'),dict(safe_recovery_verified=False),
                        dict(state='FAIL'),dict(recovery='unconfirmed'),dict(safe_engine_schema='legacy')):
            result=dict(schema=functional.SCHEMA,safe_engine_schema=s.ENGINE_SCHEMA,state=functional.SUCCESS_STATE,
                role='probe-present',safe_recovery_verified=True,recovery='complete before reservation release',
                guest_boots=1,performance_inference=False,performance_accepted=False)
            result.update(changes)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'result.json';path.write_text(json.dumps(result))
                with self.assertRaises(ValueError):functional.verify_result(p.binding(path),'probe-present')


if __name__=='__main__':unittest.main()
