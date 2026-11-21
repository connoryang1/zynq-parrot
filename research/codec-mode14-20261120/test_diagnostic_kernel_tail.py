"""Fake low-level expect/session tests; never launch a child or board."""
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import diagnostic_kernel_tail as diag


class FakeChild(diag.KernelTailSpawn):
    def __init__(self):
        self.allowed_string_types=(str,)
        self.ignorecase=False
        self.encoding='utf-8'
        self.before='initial';self.after='initial';self.match=None;self.match_index=None
        self.logfile_read=io.StringIO();self.diagnostic_events=[];self.closed=False
    def setwinsize(self,*args):pass
    def isalive(self):return not self.closed
    def close(self,force=False):self.closed=True


class DiagnosticKernelTailTests(unittest.TestCase):
    def low_level(self,child,tail=1,error=None,original_error=None,selected=2):
        calls=[]
        matched=diag.KERNEL_FAILURE_MARKER.search('Oops: original failure')
        state=dict(before='original prefix',after='Oops:',match=matched,match_index=selected)
        def fake(instance,patterns,timeout=-1,searchwindowsize=-1,async_=False,**kw):
            calls.append(dict(patterns=patterns,timeout=timeout,searchwindowsize=searchwindowsize,async_=async_))
            if len(calls)==1 or len(calls)>2:
                if original_error is not None:raise original_error
                for k,v in state.items():setattr(instance,k,v)
                if instance.logfile_read:instance.logfile_read.write('Oops: original failure\n')
                return selected
            instance.before='Call Trace: captured extra registers\n'
            instance.after=diag.pexpect.EOF;instance.match=diag.pexpect.EOF;instance.match_index=0
            if instance.logfile_read:instance.logfile_read.write(instance.before)
            if error is not None:raise error
            return tail
        return fake,calls,state

    def assert_restored(self,child,state):
        for name,value in state.items():self.assertIs(getattr(child,name),value)

    def test_failure_returns_original_outcome_and_exact_match_identity_after_timeout(self):
        child=FakeChild();fake,calls,state=self.low_level(child)
        with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake):
            result=child.expect_list([re.compile('PASS'),re.compile('timer'),diag.KERNEL_FAILURE_MARKER],timeout=1800,searchwindowsize=77)
        self.assertEqual(result,2);self.assert_restored(child,state)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0]['timeout'],1800);self.assertEqual(calls[0]['searchwindowsize'],77)
        self.assertEqual(calls[1]['patterns'],[diag.pexpect.EOF,diag.pexpect.TIMEOUT])
        self.assertEqual(calls[1]['timeout'],20.0)
        self.assertIn('captured extra registers',child.logfile_read.getvalue())
        self.assertEqual(child.diagnostic_events[0]['end'],'timeout')

    def test_tail_eof_timeout_and_capture_errors_preserve_original_failure(self):
        for tail,error,end in [(0,None,'eof'),(1,None,'timeout'),(None,diag.pexpect.EOF('closed'),'eof-exception'),
                               (None,diag.pexpect.TIMEOUT('expired'),'timeout-exception'),(None,OSError('read failed'),'capture-error')]:
            with self.subTest(end=end):
                child=FakeChild();fake,calls,state=self.low_level(child,tail,error)
                with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake):
                    self.assertEqual(child.expect_list([None,None,diag.KERNEL_FAILURE_MARKER]),2)
                self.assert_restored(child,state);self.assertEqual(child.diagnostic_events[0]['end'],end)

    def test_original_eof_timeout_error_propagate_without_tail(self):
        for error in (diag.pexpect.EOF('closed'),diag.pexpect.TIMEOUT('late'),OSError('broken')):
            with self.subTest(error=type(error).__name__):
                child=FakeChild();fake,calls,_=self.low_level(child,original_error=error)
                with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake):
                    with self.assertRaises(type(error)) as caught:child.expect_list([diag.KERNEL_FAILURE_MARKER])
                self.assertIs(caught.exception,error);self.assertEqual(len(calls),1);self.assertEqual(child.diagnostic_events,[])

    def test_cancellation_during_tail_restores_match_and_propagates(self):
        child=FakeChild();error=KeyboardInterrupt();fake,_,state=self.low_level(child,error=error)
        with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake):
            with self.assertRaises(KeyboardInterrupt) as caught:child.expect_list([None,None,diag.KERNEL_FAILURE_MARKER])
        self.assertIs(caught.exception,error);self.assert_restored(child,state)
        self.assertEqual(child.diagnostic_events[0]['end'],'interrupted')

    def test_pass_and_other_failure_patterns_do_not_trigger_capture(self):
        for patterns in ([re.compile('PASS'),diag.KERNEL_FAILURE_MARKER],[re.compile('Oops:')]):
            with self.subTest(patterns=patterns):
                child=FakeChild();fake,calls,state=self.low_level(child,selected=0)
                with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake):self.assertEqual(child.expect_list(patterns),0)
                self.assertEqual(len(calls),1);self.assertEqual(child.diagnostic_events,[]);self.assert_restored(child,state)

    def test_only_one_twenty_second_window_per_spawn(self):
        child=FakeChild();fake,calls,state=self.low_level(child)
        with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake):
            self.assertEqual(child.expect_list([None,None,diag.KERNEL_FAILURE_MARKER]),2)
            self.assertEqual(child.expect_list([None,None,diag.KERNEL_FAILURE_MARKER]),2)
        self.assertEqual(len(calls),3);self.assertEqual(len(child.diagnostic_events),1);self.assert_restored(child,state)

    def test_unchanged_real_guard_and_runner_still_write_fail_with_tail(self):
        with tempfile.TemporaryDirectory(prefix='kernel-tail-runner-') as directory:
            root=Path(directory);nbf=root/'image.nbf';nbf.write_text('parser fixture')
            elf=root/'fake-elf';elf.write_bytes(b'host fixture, never executed')
            from emit_resume_transfer import commands
            transfer=root/'payload.transfer';transfer.write_text('\n'.join(commands(elf))+'\n')
            log=root/'failure.log';args=diag.guest.parse_args([str(nbf),str(transfer),hashlib.sha256(elf.read_bytes()).hexdigest(),str(log),'--bitstream-sha256','f'*64])
            child=FakeChild();fake,calls,state=self.low_level(child)
            with mock.patch.object(diag.BASE_SPAWN,'expect_list',new=fake),mock.patch.object(diag.guest.pexpect,'spawn',return_value=child):
                with self.assertRaisesRegex(RuntimeError,'kernel failure marker during Linux boot: Oops:'):
                    diag.guest.run(args)
            status=json.loads(log.with_suffix('.log.status.json').read_text())
            self.assertEqual(status['status'],'FAIL');self.assertIn('Oops:',status['error'])
            self.assertIn('Call Trace: captured extra registers',log.read_text())
            self.assert_restored(child,state);self.assertTrue(child.closed)

    def test_delegate_pass_unchanged_metadata_json_and_spawn_restored(self):
        with tempfile.TemporaryDirectory(prefix='kernel-tail-main-') as directory:
            output=Path(directory)/'A1-diagnostic';argv=['image','transfer','e'*64,'package',str(output),'--cell','deflate:32:futex-early']
            original=diag.guest.pexpect.spawn
            def delegate(actual):
                self.assertEqual(actual,argv)
                self.assertTrue(issubclass(diag.guest.pexpect.spawn,diag.KernelTailSpawn))
                self.assertFalse(output.exists())
                output.mkdir();(output/'fake-status.json').write_text('{"status":"PASS"}')
                return 0
            with mock.patch.object(diag.session,'main',side_effect=delegate) as main:
                self.assertEqual(diag.main(argv),0);main.assert_called_once_with(argv)
            self.assertIs(diag.guest.pexpect.spawn,original)
            path=output.with_name(output.name+'-diagnostic-host')/'diagnostic-wrapper.json'
            self.assertTrue(path.read_bytes().endswith(b'\n'));record=json.loads(path.read_text())
            self.assertTrue(record['diagnostic_only']);self.assertTrue(record['excluded_from_performance_inference'])
            self.assertEqual(record['delegate_return'],0);self.assertEqual(record['tail_events'],[])
            self.assertEqual(json.loads((output/'fake-status.json').read_text()),{'status':'PASS'})

    def test_delegate_failure_propagates_and_diagnostic_never_promotes_status(self):
        with tempfile.TemporaryDirectory(prefix='kernel-tail-main-') as directory:
            output=Path(directory)/'A1-diagnostic';argv=['image','transfer','e'*64,'package',str(output)]
            error=RuntimeError('original failure');original=diag.guest.pexpect.spawn
            def delegate(_):
                output.mkdir();(output/'fake-status.json').write_text('{"status":"FAIL"}');raise error
            with mock.patch.object(diag.session,'main',side_effect=delegate):
                with self.assertRaises(RuntimeError) as caught:diag.main(argv)
            self.assertIs(caught.exception,error);self.assertIs(diag.guest.pexpect.spawn,original)
            record=json.loads((output.with_name(output.name+'-diagnostic-host')/'diagnostic-wrapper.json').read_text())
            self.assertIn('failed',record['state']);self.assertEqual(json.loads((output/'fake-status.json').read_text()),{'status':'FAIL'})

    def test_performance_slot_or_existing_output_rejected_before_delegate(self):
        with tempfile.TemporaryDirectory(prefix='kernel-tail-main-') as directory:
            with mock.patch.object(diag.session,'main') as delegate:
                with self.assertRaisesRegex(ValueError,'diagnostic'):diag.main(['a','b','c','d',str(Path(directory)/'B1')])
                output=Path(directory)/'existing-diagnostic';output.mkdir()
                with self.assertRaises(FileExistsError):diag.main(['a','b','c','d',str(output)])
                delegate.assert_not_called()


if __name__=='__main__':unittest.main()
