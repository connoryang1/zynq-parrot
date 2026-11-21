"""Real host fork/regex text plus synthetic physical framing; never board data."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import pexpect
import retained29_cost_protocol as p
import retained29_application_protocol as old
import run_retained29_cost_session as client
import test_retained29_cost_benchmark as host
import test_retained29_session as original

RAW={}
HARDWARE=copy.deepcopy(original.HARDWARE)
HARDWARE['retained']=dict(i_lines=65,d_lines=1320,set_log2=6)


def fixtures():
    if RAW:return
    factory=tempfile.TemporaryDirectory
    with patch.object(host.tempfile,'TemporaryDirectory',side_effect=lambda **kw:factory(prefix=kw.get('prefix','cost-'),dir='/tmp')):
        host.TriggerCostTests.setUpClass()
    observer=host.TriggerCostTests(methodName='test_all_workloads_and_lanes_charge_controls_only_to_enabled_cells')
    try:
        for work in p.WORKLOADS:
            for policy,mask in p.POLICIES:
                result,events=observer.run_case(work,policy)
                if result.returncode:raise AssertionError(result.stderr)
                if [v for n,_,v in events if n=='r29_control']!=[mask,0,mask,0]:raise AssertionError('actual enabled-only control calls')
                for field,value in host.EXPECTED.items():
                    if len(re.findall(r'\b'+field+'='+str(value)+r'\b',result.stdout))!=4:raise AssertionError('independent resource arithmetic')
                if work=='regex':
                    if sum(n=='regex_exec' for n,_,_ in events)!=4*2*5*64:raise AssertionError('actual64 POSIX calls/request')
                    if {v for n,_,v in events if n=='regex_exec'}!={0,1}:raise AssertionError('positive/negative cases')
                RAW[(work,policy)]=result.stdout
                if os.environ.get('R29_COST_HOST_FIXTURE_DIR'):
                    out=Path(os.environ['R29_COST_HOST_FIXTURE_DIR']);out.mkdir(parents=True,exist_ok=True);stem=work+'-'+policy
                    (out/(stem+'.stdout')).write_text(result.stdout);(out/(stem+'.stderr')).write_text(result.stderr)
                    (out/(stem+'.events.json')).write_text(json.dumps(events)+'\n')
        if os.environ.get('R29_COST_HOST_FIXTURE_DIR'):
            out=Path(os.environ['R29_COST_HOST_FIXTURE_DIR'])
            for kind,binary in host.TriggerCostTests.binaries.items():
                shutil.copyfile(binary,out/(kind+'-host-binary'));shutil.copyfile(binary.parent/(kind+'-mock.c'),out/(kind+'-mock.c'))
            (out/'scope.json').write_text(json.dumps(dict(HOST_VERIFY=True,
                actual_argv='3 2 POLICY 2 futex plain 32 WORKLOAD none',
                parser_framing='Synthetic only: plan loops/sizes/repeats/framing adapted; raw HOST_VERIFY outputs retained.',
                actual_geometry=HARDWARE['retained'],physical_actions=0),indent=2)+'\n')
    finally:host.TriggerCostTests.tearDownClass()


def minimal(role='cost-pilot-functional',workload=None,rotation=0):
    return dict(role=role,host='xilinx@192.168.4.35',plan=p.plan_for(role,workload,rotation),hardware=copy.deepcopy(HARDWARE),
        artifacts=dict(nbf=dict(path='/synthetic/kernel.nbf',sha256=p.base.NBF_SHA),bit=dict(sha256='1'*64)),
        programs={k:dict(elf=dict(sha256=v)) for k,v in p.ELF_SHAS.items()})


def body(case,plan):
    text=RAW[(case['workload'],case['policy'])].replace('_HOST_VERIFY_','_')
    text=text.replace('loops=3','loops='+str(plan['loops'])).replace('warmup=2','warmup='+str(plan['warmup']))
    text=text.replace('corpus_kib=32','corpus_kib='+str(case['kib']))
    if plan['repeats']==4:
        lines=text.splitlines();extra=[re.sub(r'repeat=([01])',lambda m:'repeat='+str(int(m[1])+2),s) for s in lines[2:-1]]
        text='\n'.join(lines[:-1]+extra+lines[-1:])+'\n';text=text.replace('repeats=2','repeats=4')
    return text


def probe(a):
    r=a['hardware']['retained'];raw=(1<<63)|(3<<56)|(r['set_log2']<<48)|(r['d_lines']<<32)|(r['i_lines']<<16)
    return ('RETAINED_STORE_PROBE_STATUS raw=0x%016x i_lines=%d d_lines=%d set_log2=%d line_bytes=64 same_set_invalidation=1 busy_scope=uce_client_backend poll_limit=4096\nRETAINED_STORE_PROBE_PASS capability=present\n')%(raw,r['i_lines'],r['d_lines'],r['set_log2'])


def console(a):
    plan=a['plan'];text=original.boot(a)+p.session_begin(plan)+'\n'
    text+=''.join(a['programs'][k]['elf']['sha256']+'  '+p.GUEST[k]+'\n' for k in p.GUEST)
    text+='RETAINED29_COST_APP_PROBE_BEGIN\n'+probe(a)+'RETAINED29_COST_APP_EXIT case=probe rc=0\n# \nRETAINED29_COST_APP_RETURN case=probe\n'
    for case in plan['cases']:
        text+=p.begin(case)+'\n'+body(case,plan)+'RETAINED29_COST_APP_EXIT case='+case['id']+' rc=0\n# \nRETAINED29_COST_APP_RETURN case='+case['id']+'\n'
    return text+'RETAINED29_COST_APP_SESSION_END commands=6 exits=7\n# \n'+original.footer()


class Parsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures()
    def test_actual_host_programs_remain_ineligible(self):
        a=minimal();case=a['plan']['cases'][0]
        with self.assertRaises(ValueError):p.parse_benchmark(RAW[('lookup',case['policy'])],case,a['plan'],a['hardware'])
    def test_all15_real_host_work_policy_fixtures_parse_with_exact_cost_scope(self):
        for work in p.WORKLOADS:
            a=minimal('cost-performance-acquisition',work)
            parsed=p.complete_console(console(a),a);self.assertEqual(parsed['complete_cells'],48)
            self.assertTrue(all(c['control']['retained_control_writes']==str(2*c['enabled']) for x in parsed['commands'] for c in x['cells']))
    def test_all_six_pilot_rotations_complete(self):
        for rotation in range(6):
            a=minimal(rotation=rotation);self.assertEqual(p.complete_console(console(a),a)['complete_cells'],24)
    def test_old_controller_scope_or_wrong_declared_writes_rejected(self):
        a=minimal();text=console(a)
        for old_text,new in [('version=29-cost','version=29'),('retained_control_writes=0','retained_control_writes=2'),
            ('retained_control_writes=2','retained_control_writes=0'),(' baseline=mode0-no-retained-control',''),
            (' retained_control_writes=0',''),('RESUME_RETAINED29_COST_','RESUME_RETAINED29_')]:
            with self.subTest(old=old_text),self.assertRaises(ValueError):p.complete_console(text.replace(old_text,new),a)
        with self.assertRaises(ValueError):old.parse_commands(text,a)
    def test_missing_whole_resource_nonpass_hash_counter_and_order_rejected(self):
        a=minimal();text=console(a)
        lines=text.splitlines();whole=next(x for x in lines if x.startswith('RESUME_RETAINED29_COST_WHOLE'))
        mutations=[text.replace(whole+'\n','',1),text.replace('RESUME_RETAINED29_COST_RESOURCE','MISSING_RESOURCE',1),
            text.replace('rc=0','rc=1',1),text.replace(a['programs']['regex']['elf']['sha256'],'0'*64),
            text.replace('new_activity=0','new_activity=1',1),text.replace('order=0 enabled=0','order=1 enabled=0',1),
            text+'RETAINED29_APP_SESSION_END commands=6 exits=7\n',text.replace('47104K','65536K'),
            text.replace('INFO:    CORE[0] PASS\n',''),text.replace('BOARD_RUNNER_SOURCE_SHA256='+p.base.HELPER_SHA,'')]
        for changed in mutations:
            with self.assertRaises(ValueError):p.complete_console(changed,a)
    def test_complete_result_rebinds_console_input_and_actual_final_recovery(self):
        # Only admission hardware prerequisites are mocked. The NEW result
        # verifier still reparses all real-host-derived synthetic framed rows.
        a=minimal();a.update(sources={},legacy_sources={},cohort_record={},visit_id='HOST_VERIFY')
        core=dict(HOST_VERIFY=True)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);input_path=root/'input.json';input_path.write_text(json.dumps(a))
            path=root/'console.log';path.write_text(console(a))
            receipt=root/'safe-publication.json';receipt.write_text(json.dumps(dict(
                state='verified old2dd/helper/overlay/operating recovery',label='final',power_pending=None,own_guest=None)))
            result=dict(schema=p.SCHEMA,state=p.SUCCESS_STATE,safe_engine_schema=p.safe_functional.session.ENGINE_SCHEMA,
                safe_recovery_verified=True,recovery='complete before reservation release',guest_boots=1,performance_accepted=False,
                supervisor_admission=a,admission=core,supervisor_sources={},supervisor_admission_record=p.binding(input_path),
                guest=dict(p.complete_console(path.read_text(),a),runner_exit=0,guest_exit=0,runner_signal=None,shell_return=True,
                    console=p.binding(path),executed_case_ids=[c['id'] for c in a['plan']['cases']]),
                started_utc='2026-11-21T00:00:00+00:00',release_after_recovery_utc='2026-11-21T00:10:00+00:00',
                reservation_release_utc='2026-11-21T00:10:00+00:00',operation_logs={},operation_journal=p.binding(receipt),
                **p.result_metadata(a,core))
            target=root/'session.json'
            def check():target.write_text(json.dumps(result));return p.verify_result(p.binding(target))
            with patch.object(p,'validate_admission',return_value=core),patch.object(p,'acquisition_ready'):
                check();result['guest']['complete_cells']-=1
                with self.assertRaises(ValueError):check()
                result['guest']['complete_cells']+=1;receipt.write_text('{}')
                with self.assertRaises(ValueError):check()


class FakeChild:
    def __init__(self,a,bad_hash=None,bad_case=None,bad_probe=False,exitstatus=0):
        self.a=a;self.bad_hash=bad_hash;self.bad_case=bad_case;self.bad_probe=bad_probe;self.exitstatus=exitstatus
        self.signalstatus=None;self.commands=[];self.pending=original.boot(a)+'# ';self.live=True
    def setwinsize(self,*args):pass
    def sendline(self,command):
        self.commands.append(command);plan=self.a['plan']
        if command.startswith('/bin/busybox sha256sum '):
            kind=next(k for k,v in p.GUEST.items() if command.endswith(v));self.pending=('0'*64 if kind==self.bad_hash else self.a['programs'][kind]['elf']['sha256'])+'  '+p.GUEST[kind]+'\n# '
        elif command.startswith('echo ') and ';' not in command:self.pending=command[5:]+'\n# '
        elif command==p.probe_command():self.pending='RETAINED29_COST_APP_PROBE_BEGIN\n'+('' if self.bad_probe else probe(self.a))+'RETAINED29_COST_APP_EXIT case=probe rc=0\n# '
        elif command=='poweroff -f':self.pending=original.footer()
        elif command in [p.command(plan,c) for c in plan['cases']]:
            case=next(c for c in plan['cases'] if command==p.command(plan,c))
            self.pending=p.begin(case)+'\n'+body(case,plan)+'RETAINED29_COST_APP_EXIT case='+case['id']+' rc='+('1' if case['id']==self.bad_case else '0')+'\n# '
        else:self.pending='# '
        self.pending='\r\r\n'+self.pending.replace('\n','\r\r\n')
    def expect(self,patterns,timeout):
        if patterns is pexpect.EOF:return 0
        patterns=patterns if isinstance(patterns,list) else [patterns];self.logfile_read.write(self.pending);self.logfile_read.flush()
        found=[(m.start(),i,m) for i,pattern in enumerate(patterns) if (m:=pattern.search(self.pending))]
        if not found:raise pexpect.TIMEOUT(self.pending[-100:])
        _,index,self.match=min(found,key=lambda x:(x[0],x[1]));self.pending=self.pending[self.match.end():];return index
    def close(self,force=False):self.live=False
    def isalive(self):return self.live


class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures()
    def run_fake(self,**options):
        a=minimal();child=FakeChild(a,**options)
        with tempfile.TemporaryDirectory() as tmp,patch.object(client,'verify_sources'),patch.object(client,'verify_artifacts'),patch.object(p,'transfer_commands',return_value=[]):
            result=client.run_guest(a,Path(tmp)/'console.log',{},spawn=lambda *a,**kw:child)
        return child,result
    def test_all_hashes_precede_probe_and_six_commands_then_full_terminal(self):
        child,result=self.run_fake();self.assertEqual(result['complete_cells'],24);index=child.commands.index(p.probe_command())
        self.assertTrue(all(child.commands.index('/bin/busybox sha256sum '+p.GUEST[k])<index for k in p.GUEST));self.assertEqual(child.commands[-1],'poweroff -f')
    def test_wrong_last_hash_executes_nothing(self):
        a=minimal();child=FakeChild(a,bad_hash='regex')
        with tempfile.TemporaryDirectory() as tmp,patch.object(client,'verify_sources'),patch.object(client,'verify_artifacts'),patch.object(p,'transfer_commands',return_value=[]):
            with self.assertRaises(ValueError):client.run_guest(a,Path(tmp)/'log',{},spawn=lambda *a,**kw:child)
        self.assertNotIn(p.probe_command(),child.commands);self.assertFalse(child.live)
    def test_probe_failure_third_command_failure_or_abnormal_exit_refused(self):
        for options in (dict(bad_probe=True),dict(bad_case=minimal()['plan']['cases'][2]['id']),dict(exitstatus=1)):
            with self.assertRaises(ValueError):self.run_fake(**options)


if __name__=='__main__':unittest.main()
