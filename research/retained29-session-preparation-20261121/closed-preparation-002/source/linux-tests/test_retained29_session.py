"""Offline refusal/console/lifecycle checks. No test invokes a board helper.

Artifact unit fixtures deliberately replace pinned hashes and the local package
verifier; the separately retained real offline admission supplies artifact proof.
"""
import copy
import fcntl
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pexpect

import emit_resume_transfer
import retained29_protocol as p
import run_retained29_session as s


HARDWARE=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',l1i_bytes=32768,l1d_bytes=32768,
              l2_bytes=16384,retained=dict(i_lines=64,d_lines=64,set_log2=6))
STATUS=(1<<63)|(3<<56)|(6<<48)|(64<<32)|(64<<16)


def admission(role='benchmark-functional'):
    return dict(role=role,host='xilinx@192.168.4.35',hardware=copy.deepcopy(HARDWARE),
                runtime_ms=3600000,sources=p.source_hashes(),artifacts=dict(
                    nbf=dict(path='/fixture/test.nbf',sha256=p.NBF_SHA),
                    bit=dict(sha256='1'*64),elf=dict(sha256=p.ELF_SHAS[role])))


def boot(a):
    return ('CONTROL_PROGRAM_SHA256='+p.RUNNER_SHA+'\nNBF_SHA256='+p.NBF_SHA+
            '\nBITSTREAM_SHA256='+a['artifacts']['bit']['sha256']+
            '\nallocating owned DRAM buffer with size 48234496\n'
            'allocate_dram() called with size 48234496 bytes\n'
            'Domain0 Next Arg1 : 0x0000000082200000\n'
            'Kernel command line: earlycon rdinit=/bin/sh mem=46M\n'
            'Memory limited to 46MB\nMemory: 32100K/47104K available\n'
            'DMA32 [mem 0x0000000080000000-0x0000000082dfffff]\n')


def guest(a):
    if a['role']=='probe-absent':return 'RETAINED_STORE_PROBE_PASS capability=absent\n'
    if a['role']=='probe-present':
        return (f'RETAINED_STORE_PROBE_STATUS raw=0x{STATUS:016x} i_lines=64 d_lines=64 set_log2=6 '
                'line_bytes=64 same_set_invalidation=1 busy_scope=uce_client_backend poll_limit=4096\n'
                'RETAINED_STORE_PROBE_PASS capability=present\n')
    rows=['RESUME_RETAINED29_CONFIG loops=8 repeats=2 warmup=4 policy=ordinary-joint enabled_mask=15 '
          'sync=futex profile=plain corpus_kib=32 workload=lookup advisory_source=none task_preview_mode=0 '
          'i_lines=64 d_lines=64 set_log2=6 line_bytes=64 same_set_invalidation=1 poll_limit=4096',
          'RESUME_RETAINED29_SCOPE version=29 mode=cell activation=before-allocation cleanup=mode0 '
          'busy=uce_client_backend matched_lifecycle=1 advisory_source=none']
    for repeat,order,enabled in ((0,0,0),(0,1,1),(1,0,1),(1,1,0)):
        key=f' repeat={repeat} order={order} enabled={enabled}'
        rows += ['RESUME_RETAINED29_RESULT'+key+' cycles=100 loops=8',
                 'RESUME_RETAINED29_WHOLE'+key+' cycles=200 loops=8',
                 'RESUME_RETAINED29_CONTROL'+key+f' requested={15*enabled} active_raw=0x{STATUS|15*enabled:016x} '
                 f'reset_raw=0x{STATUS:016x} busy_scope=uce_client_backend',
                 'RESUME_RETAINED29_RESOURCE'+key+' minor_faults=5 major_faults=0 user_us=1 system_us=2 voluntary_switches=8 involuntary_switches=0',
                 'RESUME_RETAINED29_PREFIX'+key+' before=0x0000000000000000 after=0x0000000000000000 new_activity=0 advisory_source=none',
                 'RESUME_RETAINED29_REPLAY'+key+' before=0x0000000000000000 after=0x0000000000000000 new_activity=0 advisory_source=none']
    return '\n'.join(rows+['RESUME_RETAINED29_PASS'])+'\n'


def footer():
    return ('INFO:    CORE[0] PASS\nINFO:    Returning from ps_main with RC: 0\n'
            'INFO:    BSG PASS\nBOARD_RUNNER_SOURCE_SHA256='+p.HELPER_SHA+'\n')


def console(a):return boot(a)+guest(a)+'RETAINED29_EXIT rc=0\n# \n'+footer()


class Protocol(unittest.TestCase):
    def test_all_three_complete_roles(self):
        for role in p.ELF_SHAS:
            a=admission(role);p.complete_console(console(a),a)

    def test_hash_bounds_and_kernel_failures(self):
        a=admission();text=console(a)
        changes=[(p.RUNNER_SHA,'0'*64),(p.NBF_SHA,'0'*64),('BITSTREAM_SHA256='+'1'*64,'BITSTREAM_SHA256='+'0'*64),
                 ('size 48234496','size 67108864'),('48234496 bytes','67108864 bytes'),('46MB','64MB'),
                 ('47104K','65536K'),('82dfffff','83ffffff'),('82200000','82201000'),('mem=46M','mem=64M')]
        for old,new in changes:
            with self.subTest(old=old),self.assertRaises(ValueError):p.complete_console(text.replace(old,new),a)
        for failure in ('Oops: NULL\n','BP_REPLAY_TIMER_GUARD\n','RESUME_RETAINED29_HOST_VERIFY_PASS\n'):
            with self.subTest(failure=failure),self.assertRaises(ValueError):p.complete_console(text+failure,a)

    def test_every_completion_gate_required(self):
        a=admission();text=console(a)
        for line in ('RESUME_RETAINED29_PASS\n','RETAINED29_EXIT rc=0\n','INFO:    CORE[0] PASS\n',
                     'INFO:    Returning from ps_main with RC: 0\n','INFO:    BSG PASS\n',
                     'BOARD_RUNNER_SOURCE_SHA256='+p.HELPER_SHA+'\n'):
            with self.subTest(line=line),self.assertRaises(ValueError):p.complete_console(text.replace(line,''),a)
        with self.assertRaises(ValueError):p.complete_console(text.replace('rc=0','rc=1'),a)
        with self.assertRaises(ValueError):p.complete_console(text+footer(),a)
        with self.assertRaises(ValueError):p.complete_console(footer()+boot(a)+guest(a)+'RETAINED29_EXIT rc=0\n',a)

    def test_cells_source_cleanup_geometry_and_order(self):
        a=admission();text=console(a)
        mutations=[('ordinary-joint','retention-rr'),('advisory_source=none','advisory_source=matched'),
                   ('cycles=200','cycles=99'),('requested=15','requested=3'),('i_lines=64','i_lines=128'),
                   (f'reset_raw=0x{STATUS:016x}',f'reset_raw=0x{STATUS|0x100:016x}'),
                   ('minor_faults=5','minor_faults=-1'),('new_activity=0','new_activity=1'),
                   ('after=0x0000000000000000','after=0x0000000000400000'),
                   ('before=0x0000000000000000','before=0x0000003fffc00000'),
                   ('repeat=1 order=0 enabled=1','repeat=1 order=1 enabled=1')]
        for old,new in mutations:
            with self.subTest(old=old),self.assertRaises(ValueError):p.complete_console(text.replace(old,new),a)
        with self.assertRaises(ValueError):p.complete_console(text.replace('RESUME_RETAINED29_RESOURCE','PIPE_HINT_RESOURCE'),a)

    def test_transfer_remap_preserves_bytes_and_globals(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf=Path(tmp)/'elf';elf.write_bytes(b'actual payload\x00'*20)
            transfer=Path(tmp)/'transfer';transfer.write_text('\n'.join(emit_resume_transfer.commands(elf))+'\n')
            a=admission('probe-absent');a['artifacts'].update(transfer=p.binding(transfer),elf=p.binding(elf))
            commands=p.transfer_commands(a)
            self.assertTrue(all(p.transport.GUEST_ELF not in row for row in commands))
            self.assertIn('/tmp/bp-retained29-probe',commands[-1])
            self.assertEqual(p.transport.GUEST_ELF,'/tmp/scheduler_pipe_hint_benchmark_dynamic')
            transfer.write_text(transfer.read_text()+'echo injected\n')
            with self.assertRaises(ValueError):p.transfer_commands(a)


class FakeChild:
    def __init__(self,a,wrong_hash=False,nonzero=False,missing_pass=False,exitstatus=0,failure=None):
        self.a=a;self.wrong_hash=wrong_hash;self.nonzero=nonzero;self.missing_pass=missing_pass
        self.exitstatus=exitstatus;self.signalstatus=None;self.failure=failure
        self.commands=[];self.pending=boot(a)+'# ';self.live=True;self.match=None
    def setwinsize(self,*args):pass
    def sendline(self,command):
        self.commands.append(command)
        if command.startswith('/bin/busybox sha256sum '):
            self.pending=('0'*64 if self.wrong_hash else self.a['artifacts']['elf']['sha256'])+'  '+p.GUEST[self.a['role']]+'\n# '
        elif command==p.guest_command(self.a['role']):
            self.pending=(guest(self.a) if not self.missing_pass else '')+f'RETAINED29_EXIT rc={1 if self.nonzero else 0}\n# '
        elif command=='poweroff -f':self.pending=footer()
        else:self.pending='# '
        self.pending='\n'+self.pending
    def expect(self,patterns,timeout):
        if patterns is pexpect.EOF:return 0
        if self.failure:raise self.failure('simulated transport interruption')
        patterns=patterns if isinstance(patterns,list) else [patterns]
        self.logfile_read.write(self.pending);self.logfile_read.flush()
        for i,pattern in enumerate(patterns):
            match=pattern.search(self.pending)
            if match:
                self.match=match;self.pending=self.pending[match.end():];return i
        raise AssertionError('fake no match '+repr(self.pending))
    def close(self,force=False):self.live=False
    def isalive(self):return self.live


class GuestProtocol(unittest.TestCase):
    def run_child(self,**options):
        a=admission('probe-present');child=FakeChild(a,**options)
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'transfer_commands',return_value=['fixed validated transfer']):
            result=s.run_guest(a,Path(tmp)/'console.log',{},spawn=lambda *args,**kw:child)
        return child,result

    def test_real_client_command_order_and_return(self):
        child,result=self.run_child()
        self.assertEqual(result['runner_exit'],0)
        self.assertLess(child.commands.index('/bin/busybox sha256sum /tmp/bp-retained29-probe'),child.commands.index(p.guest_command('probe-present')))
        self.assertEqual(child.commands[-1],'poweroff -f')

    def test_wrong_actual_hash_never_executes(self):
        a=admission('probe-present');child=FakeChild(a,wrong_hash=True)
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'transfer_commands',return_value=[]):
            with self.assertRaisesRegex(ValueError,'actual guest ELF hash'):
                s.run_guest(a,Path(tmp)/'console.log',{},spawn=lambda *args,**kw:child)
        self.assertNotIn(p.guest_command(a['role']),child.commands);self.assertFalse(child.live)

    def test_failures_never_poweroff_as_pass(self):
        for options in ({'nonzero':True},{'missing_pass':True},{'exitstatus':1},
                        {'failure':pexpect.EOF},{'failure':pexpect.TIMEOUT}):
            with self.subTest(options=options),self.assertRaises((ValueError,pexpect.EOF,pexpect.TIMEOUT)):
                self.run_child(**options)


class Admission(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.artifacts={}
        for key in ('nbf','elf','package','bit'):
            path=self.root/('test.nbf' if key=='nbf' else key);path.write_bytes(('fixture '+key).encode())
            self.artifacts[key]=p.binding(path)
        transfer=self.root/'transfer';transfer.write_text('\n'.join(emit_resume_transfer.commands(Path(self.artifacts['elf']['path'])))+'\n')
        self.artifacts['transfer']=p.binding(transfer)
        proof=self.root/'proof.json';proof.write_text(json.dumps(dict(
            state='PASS offline actual-linked-kernel and bounded-NBF verification; runtime pending',
            load_bound=dict(allocation_bytes=48234496,all_write_tails_within_allocation=True))))
        self.artifacts['kernel_verification']=p.binding(proof)
        fit=self.root/'fit.json';fit.write_text(json.dumps(dict(state='routed-fit-and-package-PASS',
            bit_sha256=self.artifacts['bit']['sha256'],package_sha256=self.artifacts['package']['sha256'],
            cfg=HARDWARE['cfg'])))
        self.artifacts['fit']=p.binding(fit)
        self.a=admission('probe-present');self.a.update(schema='bp-retained29-functional-session-v1',
            state='bound-functional-only',guest_argv=p.argv_for('probe-present'),one_guest_boot=True,
            performance_inference=False,runner_sha256=p.RUNNER_SHA,board_helper_sha256=p.HELPER_SHA,
            artifacts=self.artifacts)
        for name,value in [('NBF_SHA',self.artifacts['nbf']['sha256']),
                           ('KERNEL_PROOF_SHA',self.artifacts['kernel_verification']['sha256']),
                           ('ELF_SHAS',{key:self.artifacts['elf']['sha256'] for key in p.ELF_SHAS})]:
            patcher=patch.object(p,name,value);patcher.start();self.addCleanup(patcher.stop)
        # Unit package fixture only. Real package admission is run independently.
        patcher=patch.object(p.subprocess,'run',return_value=SimpleNamespace(returncode=0,
            stdout='PACKAGE_OK=1\nPACKAGE_SHA256='+self.artifacts['package']['sha256']+'\n'))
        patcher.start();self.addCleanup(patcher.stop)

    def test_exact_bound_admission_and_rejections(self):
        p.validate_admission(self.a)
        for key,value in [('runtime_ms',1),('one_guest_boot',False),('performance_inference',True),
                          ('host','other@host'),('runner_sha256','0'*64),('board_helper_sha256','0'*64),
                          ('guest_argv',['/tmp/arbitrary','present'])]:
            a=copy.deepcopy(self.a);a[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_admission(a)
        Path(self.artifacts['nbf']['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'):p.validate_admission(self.a)

    def test_no_synthesis_or_estimate_substituted_for_routed_fit(self):
        fit=Path(self.artifacts['fit']['path']);obj=json.loads(fit.read_text());obj['state']='synthesis-estimate-PASS'
        fit.write_text(json.dumps(obj));self.a['artifacts']['fit']=p.binding(fit)
        with self.assertRaisesRegex(ValueError,'routed fit'):p.validate_admission(self.a)

    def benchmark_gate(self):
        log=self.root/'probe.log';log.write_text(console(self.a))
        gate=dict(state='PASS-complete-recovered-functional-session',role='probe-present',guest_boots=1,
            recovery='complete before reservation release',release_after_recovery_utc='2026-11-21T00:00:00+00:00',
            performance_inference=False,hardware=self.a['hardware'],artifacts=self.a['artifacts'],
            admission=copy.deepcopy(self.a),sources=self.a['sources'],guest=dict(runner_exit=0,runner_signal=None,
                guest_exit=0,shell_return=True,console=p.binding(log)))
        path=self.root/'gate.json';path.write_text(json.dumps(gate))
        a=copy.deepcopy(self.a);a.update(role='benchmark-functional',guest_argv=p.argv_for('benchmark-functional'),capability_gate=p.binding(path))
        return a,gate,path,log

    def test_benchmark_requires_complete_matching_recovered_probe(self):
        a,gate,path,log=self.benchmark_gate();p.validate_admission(a)
        for key,value in [('recovery','FAILED'),('guest_boots',2),('state','FAIL'),('role','probe-absent')]:
            changed=copy.deepcopy(gate);changed[key]=value;path.write_text(json.dumps(changed));a['capability_gate']=p.binding(path)
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_admission(a)
        path.write_text(json.dumps(gate));a['capability_gate']=p.binding(path);log.write_text(log.read_text().replace('INFO:    BSG PASS','missing'))
        with self.assertRaisesRegex(ValueError,'artifact changed'):p.validate_admission(a)


class Lifecycle(unittest.TestCase):
    def test_common_lock_busy_no_output_no_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=Path(tmp)/'existing.lock';lock.touch();output=Path(tmp)/'output'
            with lock.open('r') as held:
                fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(p.maintained_session,'SESSION_LOCK',lock),patch.object(p,'validate_admission'),patch.object(s,'environment') as env:
                    with self.assertRaises(BlockingIOError):s.execute(admission(),output)
                    self.assertFalse(output.exists());env.assert_not_called()

    def lifecycle(self,fail=None,drift=False):
        calls=[]
        class Ops:
            def __init__(self,*args):pass
            def stage(self):calls.append('stage')
            def recover(self,label):
                calls.append(label)
                if fail==label:raise RuntimeError('failed '+label)
            def remote_identity(self):
                calls.append('identity')
                if fail=='identity':raise RuntimeError('helper drift')
            def guest(self):
                calls.append('guest')
                if fail=='guest':raise RuntimeError('guest failed')
                return {'fixture_only':True}
        with tempfile.TemporaryDirectory() as tmp:
            lock=Path(tmp)/'existing.lock';lock.touch();out=Path(tmp)/'output';a=admission()
            with patch.object(p.maintained_session,'SESSION_LOCK',lock),patch.object(p,'validate_admission'),patch.object(s,'verify_artifacts'),patch.object(s,'environment',return_value={}),patch.object(s,'verify_sources',side_effect=([None,ValueError('source drift'),None] if drift else None)):
                try:result=s.execute(a,out,operations=Ops)
                except (RuntimeError,ValueError):result=json.loads((out/'session.json').read_text())
            with lock.open('r') as descriptor:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return calls,result

    def test_success_one_boot_and_recovery_before_release(self):
        calls,result=self.lifecycle()
        self.assertEqual(calls,['stage','initial','identity','guest','final'])
        self.assertEqual(result['state'],'PASS-complete-recovered-functional-session');self.assertEqual(result['guest_boots'],1)
        self.assertEqual(result['recovery'],'complete before reservation release')

    def test_failure_drift_and_recovery_failure_fail_closed(self):
        for failure in ('initial','identity','guest','final'):
            calls,result=self.lifecycle(fail=failure)
            self.assertEqual(result['state'],'FAIL');self.assertEqual(calls[-1],'final');self.assertLessEqual(calls.count('guest'),1)
        calls,result=self.lifecycle(drift=True)
        self.assertEqual(result['state'],'FAIL');self.assertEqual(calls[-1],'final')

    def test_draft_and_source_drift_refused_before_lock(self):
        a=admission();a.update(schema='bp-retained29-functional-session-v1',state='DRAFT-unlaunchable')
        with self.assertRaisesRegex(ValueError,'draft'):p.validate_admission(a)
        a.update(state='bound-functional-only',guest_argv=p.argv_for(a['role']),one_guest_boot=True,
                 performance_inference=False,runner_sha256=p.RUNNER_SHA,board_helper_sha256=p.HELPER_SHA)
        a['sources']['linux-tests/run_retained29_session.py']='0'*64
        with self.assertRaisesRegex(ValueError,'source identity'):p.validate_admission(a)


if __name__=='__main__':unittest.main()
