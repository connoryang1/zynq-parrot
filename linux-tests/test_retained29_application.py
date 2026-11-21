"""Host-only real fork/library fixtures and fake transport/reservation checks.

Production-shaped text below is explicitly synthetic. Original host outputs
retain HOST_VERIFY markers, and the strict physical parser rejects them.
"""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pexpect

import emit_resume_transfer
import retained29_application_protocol as p
import run_retained29_application_session as client
import test_retained29_benchmark as plain_host
import test_retained29_regex_benchmark as regex_host
import test_retained29_session as old_tests

HARDWARE=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',l1i_bytes=32768,l1d_bytes=32768,l2_bytes=16384,
              retained=dict(i_lines=65,d_lines=1320,set_log2=6))
RAW={}


def minimal(role='pilot-functional',workload=None,rotation=0):
    return dict(schema=p.SCHEMA,state='bound-reviewed-application-session',role=role,
        host='xilinx@192.168.4.35',runtime_ms=3600000,one_guest_boot=True,hardware=copy.deepcopy(HARDWARE),
        plan=p.plan_for(role,workload,rotation),sources=p.source_hashes(),
        legacy_sources={k:p.source_hashes()[k] for k in p.FROZEN},
        artifacts=dict(nbf=dict(path='/fixture/kernel.nbf',sha256=p.base.NBF_SHA),bit=dict(sha256='1'*64)),
        programs={k:dict(elf=dict(sha256=v)) for k,v in p.ELF_SHAS.items()})


def body(case,plan):
    # Adapt only schema fields/repeat count for performance parser fixtures;
    # this does not represent execution of the256-loop/128KiB workload.
    text=RAW[(case['kind'],case['policy'])]
    text=text.replace('RESUME_RETAINED29_REGEX_HOST_VERIFY_','RESUME_RETAINED29_REGEX_')
    text=text.replace('RESUME_RETAINED29_HOST_VERIFY_','RESUME_RETAINED29_')
    if plan['role']=='performance-acquisition':
        text=text.replace('loops=8','loops=256').replace('repeats=2','repeats=4').replace('warmup=4','warmup=16')
        text=text.replace('corpus_kib=32','corpus_kib='+str(case['kib']))
        if case['kind']=='plain':text=text.replace('workload=lookup','workload='+case['workload'])
        lines=text.splitlines();extra=[]
        for line in lines[2:-1]:
            extra.append(re.sub(r'repeat=([01])',lambda m:'repeat='+str(int(m[1])+2),line))
        text='\n'.join(lines[:-1]+extra+lines[-1:])+'\n'
    return text


def probe(a):
    g=a['hardware']['retained'];raw=(1<<63)|(3<<56)|(g['set_log2']<<48)|(g['d_lines']<<32)|(g['i_lines']<<16)
    return ('RETAINED_STORE_PROBE_STATUS raw=0x%016x i_lines=%d d_lines=%d set_log2=%d '
            'line_bytes=64 same_set_invalidation=1 busy_scope=uce_client_backend poll_limit=4096\n'
            'RETAINED_STORE_PROBE_PASS capability=present\n')%(raw,g['i_lines'],g['d_lines'],g['set_log2'])


def console(a):
    plan=a['plan'];text=old_tests.boot(a)+p.session_begin(plan)+'\n'
    text+=''.join(a['programs'][k]['elf']['sha256']+'  '+p.GUEST[k]+'\n' for k in ('probe','plain','regex'))
    text+='RETAINED29_APP_PROBE_BEGIN\n'+probe(a)+'RETAINED29_APP_EXIT case=probe rc=0\n# \nRETAINED29_APP_RETURN case=probe\n'
    for case in plan['cases']:
        text+=p.begin(case)+'\n'+body(case,plan)+'RETAINED29_APP_EXIT case='+case['id']+' rc=0\n# \nRETAINED29_APP_RETURN case='+case['id']+'\n'
    return text+'RETAINED29_APP_SESSION_END commands=6 exits=7\n# \n'+old_tests.footer()


def fixtures():
    if RAW:return
    plain_host.Retained29BenchmarkTests.setUpClass();regex_host.RegexBenchmarkTests.setUpClass()
    try:
        for kind,cls,work in (('plain',plain_host.Retained29BenchmarkTests,'lookup'),
                              ('regex',regex_host.RegexBenchmarkTests,'regex')):
            observer=object.__new__(cls)
            for policy,_ in p.POLICIES:
                argv=['8','2',policy,'4','futex','plain','32',work,'none']
                result,events=observer.run_case(arguments=argv)
                if result.returncode:raise AssertionError(result.stdout+result.stderr)
                RAW[(kind,policy)]=result.stdout
                if kind=='regex':
                    if sum(n=='regex_exec' for n,_,_ in events)!=4*2*12*64:raise AssertionError('actual64 regex calls/request')
                    if {value for name,_,value in events if name=='regex_exec'}!={0,1}:raise AssertionError('actual positive/negative calls')
                retain=os.environ.get('R29_APP_HOST_FIXTURE_DIR')
                if retain:
                    out=Path(retain);out.mkdir(parents=True,exist_ok=True);stem=kind+'-'+policy
                    (out/(stem+'.stdout')).write_text(result.stdout);(out/(stem+'.stderr')).write_text(result.stderr)
                    (out/(stem+'.events.json')).write_text(json.dumps(events)+'\n')
                    (out/(stem+'.json')).write_text(json.dumps(dict(argv=argv,returncode=result.returncode,
                        scope='Actual host protocol/library only. HOST_VERIFY markers deliberately retained; never physical evidence.'),indent=2)+'\n')
            if os.environ.get('R29_APP_HOST_FIXTURE_DIR'):
                out=Path(os.environ['R29_APP_HOST_FIXTURE_DIR']);shutil.copyfile(cls.binary,out/(kind+'-host-binary'))
                shutil.copyfile(cls.root/'mock.c',out/(kind+'-mock.c'))
    finally:
        regex_host.RegexBenchmarkTests.tearDownClass();plain_host.Retained29BenchmarkTests.tearDownClass()


class Parsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures()

    def test_actual_host_outputs_remain_rejected(self):
        a=minimal();case=a['plan']['cases'][0]
        with self.assertRaises(ValueError):p.parse_benchmark(RAW[(case['kind'],case['policy'])],case,a['plan'],a['hardware'])

    def test_six_pilot_commands_all_rotations_and_explicit_roles(self):
        for rotation in range(6):
            a=minimal(rotation=rotation);parsed=p.complete_console(console(a),a)
            self.assertEqual((parsed['complete_commands'],parsed['complete_cells'],parsed['guest_exits']),(6,24,7))
            self.assertEqual([x['case']['id'] for x in parsed['commands']],[x['id'] for x in a['plan']['cases']])
            self.assertEqual(parsed['primary'],'WHOLE');self.assertEqual(parsed['effect_selection'],'none')

    def test_plan_numeric_types_and_source_continuity_are_strict(self):
        for key,value in (('loops',8.0),('rotation',False),('warmup',4.0)):
            plan=p.plan_for('pilot-functional');plan[key]=value
            with self.assertRaises(ValueError):p.validate_plan(plan)
        a=minimal();text=console(a);case=a['plan']['cases'][1]
        start=text.index(p.begin(case));end=text.index('RETAINED29_APP_EXIT case='+case['id'])
        part=text[start:end].replace('0x0000000000000201','0x0000000000400201')
        # Every row remains internally unchanged/non-saturated, but activity
        # between command windows is still a source-none contradiction.
        with self.assertRaisesRegex(ValueError,'counter discontinuity'):
            p.complete_console(text[:start]+part+text[end:],a)

    def test_performance_schema_each_workload_and_both_sizes(self):
        for work in p.WORKLOADS:
            a=minimal('performance-acquisition',work,3);parsed=p.complete_console(console(a),a)
            self.assertEqual(parsed['complete_cells'],48)
            self.assertEqual({x['case']['kib'] for x in parsed['commands']},{32,128})
            self.assertEqual({x['case']['workload'] for x in parsed['commands']},{work})

    def test_missing_duplicate_nonpass_earlyexit_and_kind_contamination(self):
        a=minimal();text=console(a)
        changes=[('RETAINED29_APP_EXIT case=lookup-32-ordinary-i rc=0','RETAINED29_APP_EXIT case=lookup-32-ordinary-i rc=1'),
            ('RETAINED29_APP_RETURN case=probe','missing'),('RETAINED_STORE_PROBE_PASS capability=present','missing'),
            ('RESUME_RETAINED29_REGEX_PASS','RESUME_RETAINED29_PASS'),('RESUME_RETAINED29_SCOPE','PIPE_HINT_SCOPE'),
            ('RESUME_RETAINED29_WHOLE','MISSING_WHOLE'),('minor_faults=16','minor_faults=-1'),
            ('cleanup=mode0','cleanup=sticky'),('requested=9','requested=1'),('corpus_kib=32','corpus_kib=64'),
            ('new_activity=0','new_activity=1'),('after=0x0000000000000201','after=0x0000000000400201')]
        for old,new in changes:
            with self.subTest(old=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):p.complete_console(text.replace(old,new),a)
        for extra in ('Oops: NULL\n','BP_REPLAY_TIMER_GUARD\n','RESUME_RETAINED29_HOST_VERIFY_PASS\n',
                      old_tests.footer(),'RETAINED29_APP_RETURN case=probe\n','RUNNER_CLEANUP_SYNC_FAILED\n'):
            with self.assertRaises(ValueError):p.complete_console(text+extra,a)
        for marker in ('RETAINED29_APP_SESSION_END commands=6 exits=7\n','INFO:    CORE[0] PASS\n',
                       'INFO:    BSG PASS\n','BOARD_RUNNER_SOURCE_SHA256='+p.base.HELPER_SHA+'\n'):
            with self.assertRaises(ValueError):p.complete_console(text.replace(marker,''),a)

    def test_hash_bounds_geometry_counter_saturation_and_cell_order(self):
        a=minimal();text=console(a)
        for old,new in (('47104K','65536K'),('82dfffff','83ffffff'),('mem=46M','mem=64M'),
            ('size 48234496','size 67108864'),('i_lines=65','i_lines=64'),('repeat=1 order=0 enabled=1','repeat=1 order=1 enabled=1'),
            ('before=0x0000000000000201','before=0x0000003fffc00201'),
            ('before=0x0c00000000000000','before=0x8c00000000000000')):
            with self.subTest(old=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):p.complete_console(text.replace(old,new),a)
        target=a['programs']['regex']['elf']['sha256']+'  '+p.GUEST['regex']
        with self.assertRaises(ValueError):p.complete_console(text.replace(target,'0'*64+'  '+p.GUEST['regex']),a)


class FakeChild:
    def __init__(self,a,bad_hash=None,bad_case=None,bad_probe=False,ending='\n',exitstatus=0):
        self.a=a;self.bad_hash=bad_hash;self.bad_case=bad_case;self.bad_probe=bad_probe;self.ending=ending
        self.commands=[];self.pending=old_tests.boot(a)+'# ';self.live=True;self.exitstatus=exitstatus;self.signalstatus=None
    def setwinsize(self,*args):pass
    def sendline(self,command):
        self.commands.append(command);plan=self.a['plan']
        if command.startswith('/bin/busybox sha256sum '):
            kind=next(k for k,v in p.GUEST.items() if command.endswith(v))
            self.pending=('0'*64 if kind==self.bad_hash else self.a['programs'][kind]['elf']['sha256'])+'  '+p.GUEST[kind]+'\n# '
        elif command.startswith('echo ') and ';' not in command:self.pending=command[5:]+'\n# '
        elif command==p.probe_command():
            self.pending='RETAINED29_APP_PROBE_BEGIN\n'+('' if self.bad_probe else probe(self.a))+'RETAINED29_APP_EXIT case=probe rc=0\n# '
        elif command=='poweroff -f':self.pending=old_tests.footer()
        elif command in [p.command(plan,c) for c in plan['cases']]:
            case=next(c for c in plan['cases'] if command==p.command(plan,c))
            self.pending=p.begin(case)+'\n'+body(case,plan)+'RETAINED29_APP_EXIT case='+case['id']+' rc='+('1' if case['id']==self.bad_case else '0')+'\n# '
        else:self.pending='# '
        self.pending=('\n'+self.pending).replace('\n',self.ending)
    def expect(self,patterns,timeout):
        if patterns is pexpect.EOF:return 0
        patterns=patterns if isinstance(patterns,list) else [patterns]
        self.logfile_read.write(self.pending);self.logfile_read.flush()
        matches=[(match.start(),i,match) for i,pattern in enumerate(patterns) if (match:=pattern.search(self.pending))]
        if not matches:raise pexpect.TIMEOUT('mock no match '+repr(self.pending[-100:]))
        _,index,self.match=min(matches,key=lambda row:(row[0],row[1]));self.pending=self.pending[self.match.end():]
        return index
    def close(self,force=False):self.live=False
    def isalive(self):return self.live


class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures()

    def run_fake(self,a=None,clock=None,**options):
        a=a or minimal();child=FakeChild(a,**options)
        with tempfile.TemporaryDirectory() as tmp,patch.object(client,'verify_sources'),patch.object(client,'verify_artifacts'),\
                patch.object(p,'transfer_commands',side_effect=lambda a,k:['validated-transfer-'+k]):
            kwargs={} if clock is None else dict(clock=clock)
            result=client.run_guest(a,Path(tmp)/'console.log',{},spawn=lambda *args,**kw:child,**kwargs)
        return child,result

    def test_all_hashes_then_probe_then_six_commands_and_fullreturn(self):
        for ending in ('\n','\r\n','\r\r\r\n'):
            child,result=self.run_fake(ending=ending)
            self.assertEqual(result['complete_cells'],24)
            first=child.commands.index(p.probe_command())
            self.assertTrue(all(child.commands.index('/bin/busybox sha256sum '+p.GUEST[k])<first for k in p.GUEST))
            self.assertEqual(child.commands[-1],'poweroff -f')
            self.assertEqual(result['executed_case_ids'],[c['id'] for c in minimal()['plan']['cases']])

    def test_wrong_last_hash_executes_nothing(self):
        a=minimal();child=FakeChild(a,bad_hash='regex')
        with tempfile.TemporaryDirectory() as tmp,patch.object(client,'verify_sources'),patch.object(client,'verify_artifacts'),patch.object(p,'transfer_commands',return_value=[]):
            with self.assertRaisesRegex(ValueError,'actual guest ELF hash mismatch'):
                client.run_guest(a,Path(tmp)/'console.log',{},spawn=lambda *args,**kw:child)
        self.assertNotIn(p.probe_command(),child.commands);self.assertFalse(child.live)

    def test_probe_or_third_command_failure_never_starts_later_case(self):
        a=minimal()
        for options in (dict(bad_probe=True),dict(bad_case=a['plan']['cases'][2]['id'])):
            child=FakeChild(a,**options)
            with tempfile.TemporaryDirectory() as tmp,patch.object(client,'verify_sources'),patch.object(client,'verify_artifacts'),patch.object(p,'transfer_commands',return_value=[]):
                with self.assertRaises(ValueError):client.run_guest(a,Path(tmp)/'console.log',{},spawn=lambda *args,**kw:child)
            self.assertNotIn(p.command(a['plan'],a['plan']['cases'][3]),child.commands)
            self.assertNotIn('poweroff -f',child.commands);self.assertFalse(child.live)

    def test_fixed_total_budget_and_runner_abnormal_exit_fail(self):
        for kwargs in (dict(clock=iter([0,3601]).__next__),dict(exitstatus=1)):
            with self.assertRaises(ValueError):self.run_fake(**kwargs)

    def test_composition_delegates_only_stage_recovery_identity_never_old_guest(self):
        a=minimal();stage_base={'role':'probe-present','genuine_fixture':True}
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'prior_capability',return_value=({},stage_base)),\
             patch.object(client.stage_client,'Operations') as stage,patch.object(client,'run_guest',return_value='new-role') as guest:
            out=Path(tmp);op=client.Operations(a,out,{})
            op.stage();op.recover('initial');op.remote_identity();self.assertEqual(op.guest(),'new-role');op.recover('final')
            stage.assert_called_once_with(stage_base,out,{})
            self.assertEqual(stage.return_value.recover.call_args_list[0].args,('initial',))
            self.assertEqual(stage.return_value.recover.call_args_list[1].args,('final',))
            stage.return_value.guest.assert_not_called()
            self.assertEqual(guest.call_args.args[0]['role'],'pilot-functional')


class Admission(unittest.TestCase):
    def setUp(self):
        self.old=old_tests.Admission(methodName='test_exact_bound_admission_and_rejections');self.old.setUp()
        self.addCleanup(self.old.doCleanups);self.root=self.old.root
        fixed_admission,gate,path,_=self.old.benchmark_gate()
        fixed_log=self.root/'fixed-functional.log';fixed_log.write_text(old_tests.console(fixed_admission))
        fixed=copy.deepcopy(gate);fixed.update(role='benchmark-functional',admission=fixed_admission,
            guest=dict(runner_exit=0,runner_signal=None,guest_exit=0,shell_return=True,console=p.binding(fixed_log)))
        fixed_path=self.root/'fixed-functional.json';fixed_path.write_text(json.dumps(fixed))
        stage=self.root/'stage.json';stage.write_text('{}')
        self.a=minimal();self.a.update(hardware=copy.deepcopy(gate['hardware']),
            runner_sha256=p.base.RUNNER_SHA,board_helper_sha256=p.base.HELPER_SHA,
            artifacts={k:v for k,v in gate['artifacts'].items() if k not in ('elf','transfer')},
            programs={k:dict(elf=gate['artifacts']['elf'],transfer=gate['artifacts']['transfer']) for k in p.ELF_SHAS},
            capability_gate=p.binding(path),functional_gate=p.binding(fixed_path),stage_admission=p.binding(stage))
        self.gate,self.gate_path=gate,path
        self.cap_patch=patch.object(p.stage_client,'validate_outer',return_value=({},gate['admission']))
        self.cap_patch.start();self.addCleanup(self.cap_patch.stop)
        elf_patch=patch.object(p,'ELF_SHAS',{k:gate['artifacts']['elf']['sha256'] for k in p.ELF_SHAS})
        elf_patch.start();self.addCleanup(elf_patch.stop)
        plan=self.root/'plan.json';plan.write_text(json.dumps(dict(schema=p.PLAN_SCHEMA,state='predeclared-reviewed',plan=self.a['plan'],sources=self.a['sources'],
            elf_sha256=p.ELF_SHAS,declared_utc='2026-11-21T00:00:00+00:00',primary='WHOLE',secondary='steady',effect_selection='none')))
        self.a['plan_record']=p.binding(plan)

    def test_bound_fixture_and_actual_capability_provenance_failures(self):
        p.validate_admission(self.a)
        for key,value in (('state','DRAFT-UNLAUNCHABLE'),('runtime_ms',7200000),('role','benchmark-functional'),
                          ('legacy_sources',{}),('runner_sha256','0'*64)):
            a=copy.deepcopy(self.a);a[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_admission(a)
        for key,value in (('state','FAIL'),('role','probe-absent'),('recovery','FAILED'),('guest_boots',2)):
            g=copy.deepcopy(self.gate);g[key]=value;self.gate_path.write_text(json.dumps(g));self.a['capability_gate']=p.binding(self.gate_path)
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_admission(self.a)

    def test_plan_not_effect_selected_and_wrong_program_or_bit_refused(self):
        for mutate in ('case','metric','program','bit'):
            a=copy.deepcopy(self.a)
            if mutate=='case':a['plan']['cases'].reverse()
            if mutate=='program':a['programs']['regex']['elf']=dict(a['programs']['regex']['elf'],sha256='0'*64)
            if mutate=='bit':a['artifacts']['bit']=dict(a['artifacts']['bit'],sha256='0'*64)
            if mutate=='metric':
                target=Path(a['plan_record']['path']);data=json.loads(target.read_text());data['primary']='steady';target.write_text(json.dumps(data));a['plan_record']=p.binding(target)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):p.validate_admission(a)

    def test_fixed_functional_first_gate_cannot_be_skipped_or_substituted(self):
        target=Path(self.a['functional_gate']['path']);original=json.loads(target.read_text())
        for key,value in (('state','FAIL'),('role','probe-present'),('recovery','FAILED')):
            changed=copy.deepcopy(original);changed[key]=value;target.write_text(json.dumps(changed))
            self.a['functional_gate']=p.binding(target)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'functional first gate'):
                p.validate_admission(self.a)

    def test_default_draft_does_no_validation_operations_or_execution(self):
        path=self.root/'draft.json';path.write_text(json.dumps(dict(schema=p.SCHEMA,state='DRAFT-UNLAUNCHABLE',plan=self.a['plan'])))
        with patch.object(client,'execute') as execute,patch.object(p,'validate_admission') as validate:
            self.assertEqual(client.main([str(path)]),0);execute.assert_not_called();validate.assert_not_called()
        with patch.object(p.base.maintained_session,'reservation') as lock:
            with self.assertRaisesRegex(ValueError,'UNLAUNCHABLE'):client.execute(json.loads(path.read_text()),self.root/'never')
            lock.assert_not_called()


class Lifecycle(unittest.TestCase):
    def lifecycle(self,fail=None,busy=False,drift=False,bad_request=False):
        calls=[]
        def record(label):
            with lock.open('r') as competing:
                with self.assertRaises(BlockingIOError):fcntl.flock(competing,fcntl.LOCK_EX|fcntl.LOCK_NB)
            calls.append(label)
        class Ops:
            def __init__(self,*args):self.final_calls=0
            def requires_recovery(self):return fail!='no-mutation'
            def stage(self):
                record('stage')
                if fail in ('stage','no-mutation'):raise RuntimeError('stage failure')
            def recover(self,label):
                record(label)
                if label=='final':self.final_calls+=1
                if label=='final' and fail=='signal-live-child':
                    child=subprocess.Popen(['/bin/cat'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL)
                    try:
                        if child.poll() is not None:raise AssertionError('host recovery child must be active')
                        os.kill(os.getpid(),signal.SIGTERM)
                        if child.poll() is not None:raise AssertionError('deferred signal affected owned child')
                        record('final-child-still-owned')
                        child.communicate(b'',timeout=2)
                    finally:
                        if child.poll() is None:child.kill();child.wait()
                if fail==label and (label!='final' or self.final_calls==1):raise RuntimeError('failure '+label)
            def remote_identity(self):
                record('identity')
                if fail=='identity':raise RuntimeError('identity failure')
            def final_identity(self):
                record('final-identity')
                if fail=='final-identity' and self.final_calls==1:raise RuntimeError('runner identity mismatch')
            def guest(self):
                record('guest')
                if fail=='guest':raise RuntimeError('guest failure')
                if fail=='interrupt':raise KeyboardInterrupt('mock signal')
                return {'mock_only':True}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);lock=root/'existing.lock';lock.touch();inode=lock.stat().st_ino;out=root/'output'
            a=minimal();plan=root/'plan';plan.write_text(json.dumps(dict(declared_utc='2026-11-21T00:00:00+00:00')));a['plan_record']=p.binding(plan)
            gate=dict(release_after_recovery_utc='2026-11-21T00:00:00+00:00')
            fixed=root/'fixed';fixed.write_text(json.dumps(gate));a['functional_gate']=p.binding(fixed)
            waits=[]
            def recovery_request(wait):
                self.assertEqual(wait,10);waits.append(wait)
                state=json.loads((out/'session.json').read_text())
                self.assertEqual(state['state'],'recovery-required-reservation-held')
                self.assertNotIn('reservation_release_utc',state)
                self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_IGN)
                with lock.open('r') as competitor:
                    with self.assertRaises(BlockingIOError):fcntl.flock(competitor,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if bad_request and len(waits)==1:
                    client.journal(out/'recovery-request.json',dict(schema='bp-retained29-recovery-request-v1',
                        action='run-benchmark',token=state['recovery_token'],attempt=state['recovery_attempts']+1))
                else:client.main(['--request-recovery',str(out)])
            with lock.open('r') as held:
                if busy:fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(p.base.maintained_session,'SESSION_LOCK',lock),patch.object(p,'validate_admission'),\
                    patch.object(p,'prior_capability',return_value=(gate,{})),patch.object(client,'verify_artifacts'),\
                    patch.object(client.maintained,'environment',return_value={}),\
                    patch.object(client,'verify_sources',side_effect=([None,ValueError('source drift'),None] if drift else None)):
                    try:state=client.execute(a,out,operations=Ops,recovery_wait=recovery_request)
                    except (BlockingIOError,RuntimeError,ValueError,KeyboardInterrupt):state=json.loads((out/'session.json').read_text()) if out.exists() else None
                self.assertEqual(lock.stat().st_ino,inode)
                if busy:self.assertFalse(out.exists());self.assertEqual(calls,[])
            with lock.open('r') as released:fcntl.flock(released,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return calls,state

    def test_busy_lock_has_no_output_or_operations_and_inode_preserved(self):self.lifecycle(busy=True)
    def test_whole_session_order_final_recovery_and_release(self):
        calls,state=self.lifecycle();self.assertEqual(calls,['stage','initial','identity','guest','final','final-identity'])
        self.assertEqual(state['state'],'PASS-complete-recovered-application-session');self.assertEqual(state['guest_boots'],1)
        self.assertFalse(state['performance_accepted'])
    def test_failure_and_drift_stop_once_and_always_recover_before_unlock(self):
        for fail in ('stage','initial','identity','guest','interrupt','final'):
            calls,state=self.lifecycle(fail=fail);self.assertEqual(state['state'],'FAIL');self.assertEqual(calls[-1],'final-identity')
            self.assertLessEqual(calls.count('guest'),1)
            if fail=='final':
                self.assertEqual(calls.count('final'),2)
                self.assertEqual(state['recovery_attempts'],2)
                self.assertIn('release_after_recovery_utc',state)
                self.assertNotIn('released_without_confirmed_recovery',state)
        calls,state=self.lifecycle(drift=True);self.assertEqual(state['state'],'FAIL');self.assertEqual(calls[-1],'final-identity')
    def test_readonly_preflight_failure_never_blindly_recovers_unbound_overlay(self):
        calls,state=self.lifecycle(fail='no-mutation');self.assertEqual(calls,['stage'])
        self.assertEqual(state['state'],'FAIL');self.assertEqual(state['recovery'],'no board mutation or guest began')

    def test_failed_recovery_stays_locked_rejects_other_actions_and_explicitly_continues(self):
        calls,state=self.lifecycle(fail='final',bad_request=True)
        self.assertEqual(calls.count('guest'),1);self.assertEqual(calls.count('final'),2)
        self.assertEqual(state['recovery_attempts'],2);self.assertEqual(len(state['rejected_recovery_requests']),1)
        self.assertEqual(state['recovery'],'complete before reservation release');self.assertEqual(state['state'],'FAIL')

    def test_identity_failure_also_holds_and_signal_cannot_release_active_recovery_child(self):
        calls,state=self.lifecycle(fail='final-identity')
        self.assertEqual(calls.count('final'),2);self.assertEqual(state['recovery_attempts'],2)
        original=signal.getsignal(signal.SIGTERM)
        calls,state=self.lifecycle(fail='signal-live-child')
        self.assertIn('final-child-still-owned',calls)
        self.assertEqual(state['state'],'PASS-complete-recovered-application-session')
        self.assertEqual(signal.getsignal(signal.SIGTERM),original)


if __name__=='__main__':unittest.main()
