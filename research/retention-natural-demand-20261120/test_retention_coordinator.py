"""Real local fake children exercise controller lifecycle; never invoke hardware."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import retention_coordinator as module


FAKE_PRODUCER=r'''
import json,os,pathlib,sys,time
root=pathlib.Path(__file__).parent
label=sys.argv[1]
c=json.loads((root/'fake-config.json').read_text())
slot=next(s for s in c['slots'] if s['label']==label)
if c.get('mode')=='noclaim':time.sleep(10)
ticks=int(pathlib.Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()[19])
receipt=pathlib.Path(slot['supervisor_receipt'])
claim=dict(pid=os.getpid(),start_ticks=ticks,argv=slot['argv'])
if c.get('mode')=='badclaim':claim['argv']=['wrong']
if c.get('mode') in ('partialclaim','partialhang','deadbadclaim'):
 receipt.with_suffix('.claim').write_text('{')
 time.sleep(.03)
 if c['mode']=='deadbadclaim':sys.exit(1)
 if c['mode']=='partialhang':time.sleep(10)
receipt.with_suffix('.claim').write_text(json.dumps(claim))
if c.get('mode')=='hang':time.sleep(10)
time.sleep(.02)
r=dict(label=label,pid=os.getpid(),start_ticks=ticks,argv=slot['argv'],session_manifest=slot['session_manifest'],
 state='complete',runner_exit=0,producer=c['producer'],bounded_absent_gate=c['bounded_proof'])
if c.get('mode')=='busy':r.update(state='failed',runner_exit=1)
if c.get('mode')!='missing':receipt.write_text('{' if c.get('mode')=='malformed' else json.dumps(r))
sys.exit(r['runner_exit'])
'''


class RetentionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='retention-controller-host-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);producer=self.root/'fake_producer.py';producer.write_text(FAKE_PRODUCER)
        artifact=module.operations.frozen.artifact
        self.bound=self.root/'bounded-proof.json';self.bound.write_text('{}')
        slots=[dict(label=v,argv=['NEVER_EXECUTE_WRAPPER',v],session_manifest=str(self.root/v/'session.json'),
                    supervisor_receipt=str(self.root/(v+'-supervisor.json'))) for v in module.LABELS]
        self.c=dict(slots=slots,producer=artifact(producer),bounded_proof=artifact(self.bound),launch_admission=artifact(self.bound),
            template=dict(pilot_session_manifest=slots[0]['session_manifest'],primary=[dict(label=s['label'],session_manifest=s['session_manifest']) for s in slots[1:]],
                all_attempts_declared=False,failed_attempts=[]),coordinator=artifact(Path(module.__file__)),pins=artifact(self.bound),
            bindings=[artifact(producer),artifact(self.bound)],fast_bindings=[artifact(producer),artifact(self.bound)])
        self.ack=self.root/'ack.json';self.ack.write_text(json.dumps(dict(worktree=str(module.operations.frozen.ROOT),
            acknowledged_reservation='/home/coyang/fpga-artifacts/pynq-session.lock',preserve_me=True)))
        slot=slots[0];pid=123456789;ticks=9876
        self.c.update(pilot_launch=dict(label='pilot',pid=pid,producer_argv=['python3','-u','-B',str(producer),'pilot']),pilot_start_ticks=ticks)
        claim=Path(slot['supervisor_receipt']).with_suffix('.claim');claim.write_text(json.dumps(dict(pid=pid,start_ticks=ticks,argv=slot['argv'])))
        self.c['pilot_claim']=artifact(claim)
        Path(slot['supervisor_receipt']).write_text(json.dumps(dict(label='pilot',pid=pid,start_ticks=ticks,argv=slot['argv'],
            session_manifest=slot['session_manifest'],state='complete',runner_exit=0,producer=self.c['producer'],bounded_absent_gate=self.c['bounded_proof'])))
        self.config('normal');self.ctl=module.Coordinator(self.c,self.root,self.ack)
        self.gates=[];self.children=[]
        self.popen=subprocess.Popen
        def tracked(*args,**kwargs):
            child=self.popen(*args,**kwargs);self.children.append(child);return child
        patch=mock.patch.object(module.subprocess,'Popen',side_effect=tracked);patch.start();self.addCleanup(patch.stop)
        self.addCleanup(self.cleanup_children)
        for name,value in [('POLL_SECONDS',.005),('CLAIM_SECONDS',1),('OBSERVATION_SECONDS',2)]:
            patch=mock.patch.object(module,name,value);patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(module.operations,'complete_prefix',side_effect=self.gate)
        patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(module.operations.frozen,'audit',side_effect=lambda p:dict(state='fake audit',acquisition=json.loads(p.read_text())))
        patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(module.operations.frozen,'analyze',return_value=dict(state='fake analysis'))
        patch.start();self.addCleanup(patch.stop)

    def cleanup_children(self):
        for child in self.children:
            if child.poll() is None:child.kill()  # TEST-ONLY local fake children.
            child.wait()

    def config(self,mode):
        (self.root/'fake-config.json').write_text(json.dumps(dict(mode=mode,slots=self.c['slots'],producer=self.c['producer'],bounded_proof=self.c['bounded_proof'])))

    def gate(self,label):
        # This assertion specifically catches the zombie/Popen-reaping trap.
        for child in self.children:self.assertIsNone(module.proc(child.pid),'prefix gate reached before child reaped')
        self.gates.append(label);i=module.LABELS.index(label)
        return dict(state='fake no-effect gate',next_argv=self.c['slots'][i+1]['argv'] if i<8 else None)

    def test_all_fixed_children_reaped_before_gates_and_final_paths_exact(self):
        self.assertEqual(self.ctl.run(),0);self.assertEqual(len(self.children),8);self.assertEqual(self.gates,module.LABELS)
        self.assertEqual([p.args[-1] for p in self.children],module.LABELS[1:])
        acq=json.loads((self.root/'coordinator-acquisition.json').read_text())
        self.assertTrue(acq['all_attempts_declared']);self.assertEqual(acq['failed_attempts'],[])
        self.assertEqual(acq['primary'],self.c['template']['primary'])
        self.assertTrue(json.loads(self.ack.read_text())['preserve_me'])
        self.assertTrue(all(p.returncode==0 and module.proc(p.pid) is None for p in self.children))
        with self.assertRaisesRegex(ValueError,'already exists'):module.Coordinator(self.c,self.root,self.ack).run()

    def test_busy_failure_never_advances_or_retries(self):
        self.config('busy')
        with self.assertRaisesRegex(ValueError,'failed/busy/nonzero'):self.ctl.run()
        self.assertEqual(self.gates,['pilot']);self.assertEqual(len(self.children),1)
        self.assertFalse((self.root/'R1b-launch.json').exists());self.assertIsNone(module.proc(self.children[0].pid))
        self.assertIn('stopped',json.loads(self.ctl.journal.read_text())['state'])

    def test_observation_timeout_leaves_live_child_and_never_runs_next_gate(self):
        self.config('hang')
        with mock.patch.object(module,'OBSERVATION_SECONDS',.03):
            with self.assertRaisesRegex(TimeoutError,'may remain live'):self.ctl.run()
        self.assertIsNone(self.children[0].poll());self.assertEqual(self.gates,['pilot'])
        self.assertEqual(len(self.children),1)
        self.assertIn('may remain',json.loads(self.ctl.journal.read_text())['state'])

    def test_claim_timeout_also_leaves_live_producer_and_stops(self):
        self.config('noclaim')
        with mock.patch.object(module,'CLAIM_SECONDS',.03):
            with self.assertRaisesRegex(TimeoutError,'producer may remain live'):self.ctl.run()
        self.assertIsNone(self.children[0].poll());self.assertEqual(self.gates,['pilot'])
        self.assertEqual(json.loads(self.ctl.journal.read_text())['active']['pid'],self.children[0].pid)

    def test_partial_claim_retries_only_while_same_producer_live(self):
        self.config('partialclaim');self.ctl.journal.write_text('{}')
        launch,ticks,claim,child=self.ctl.launch(self.c['slots'][1])
        self.ctl.wait_supervisor(self.c['slots'][1],launch,ticks,claim,child)
        self.assertIsNone(module.proc(child.pid));self.assertEqual(child.returncode,0)

    def test_dead_malformed_claim_refuses_and_partial_claim_keeps_original_deadline(self):
        self.config('deadbadclaim');self.ctl.journal.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'Dead producer.*malformed claim'):self.ctl.launch(self.c['slots'][1])
        self.assertIsNone(module.proc(self.children[0].pid));self.assertEqual(self.gates,[])

    def test_live_partial_claim_timeout_never_restarts_or_kills(self):
        self.config('partialhang')
        with mock.patch.object(module,'CLAIM_SECONDS',.04):
            with self.assertRaisesRegex(TimeoutError,'producer may remain live'):self.ctl.run()
        self.assertEqual(len(self.children),1);self.assertIsNone(self.children[0].poll())
        self.assertEqual(self.gates,['pilot'])

    def test_real_child_exit_without_receipt_stops_after_reap(self):
        self.config('missing')
        with self.assertRaisesRegex(ValueError,'missing without ending receipt'):self.ctl.run()
        self.assertEqual(self.gates,['pilot']);self.assertEqual(len(self.children),1)
        self.assertIsNone(module.proc(self.children[0].pid))

    def test_changed_retained_launch_stops_before_gate_and_does_not_kill(self):
        self.config('hang');self.ctl.journal.write_text('{}')
        launch,ticks,claim,child=self.ctl.launch(self.c['slots'][1])
        (self.root/'R1a-launch.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'dependency changed'):
            self.ctl.wait_supervisor(self.c['slots'][1],launch,ticks,claim,child)
        self.assertIsNone(child.poll());self.assertEqual(self.gates,[])

    def test_missing_malformed_or_failed_adopted_supervisor_stops_before_spawn(self):
        path=Path(self.c['slots'][0]['supervisor_receipt']);original=path.read_text()
        for value in (None,'{',original.replace('"complete"','"failed"')):
            with self.subTest(value=value):
                if value is None:path.unlink()
                else:path.write_text(value)
                with self.assertRaises(ValueError):self.ctl.wait_supervisor(self.c['slots'][0],self.c['pilot_launch'],self.c['pilot_start_ticks'],self.c['pilot_claim'])
                self.assertEqual(self.children,[])
                path.write_text(original)

    def test_future_malformed_receipt_or_bad_claim_stops_at_first_child(self):
        for mode,pattern in [('malformed','Expecting'),('badclaim','claim identity')]:
            # Independent roots are created by fresh setUp in ordinary cases;
            # exercise each mode through launch/wait without a cohort journal.
            self.config(mode);slot=self.c['slots'][1];self.ctl.journal.write_text('{}')
            if mode=='badclaim':
                with self.assertRaisesRegex(ValueError,pattern):self.ctl.launch(slot)
                self.assertEqual(len(self.children),2);return
            launch,ticks,claim,child=self.ctl.launch(slot)
            with self.assertRaisesRegex(ValueError,pattern):self.ctl.wait_supervisor(slot,launch,ticks,claim,child)
            for suffix in ('-launch.json','-supervisor.log','-supervisor.json','-supervisor.claim'):
                (self.root/('R1a'+suffix)).unlink()
            self.ctl.acquired.clear()

    def test_wrong_live_start_ticks_or_argv_refuses_without_killing(self):
        child=self.popen([sys.executable,'-c','import time;time.sleep(10)']);self.children.append(child)
        state=module.proc(child.pid);launch=dict(pid=child.pid,producer_argv=state['argv'])
        for ticks,argv,pattern in [(state['start_ticks']+1,state['argv'],'start identity'),(state['start_ticks'],['wrong'],'argv changed')]:
            launch['producer_argv']=argv
            with self.assertRaisesRegex(ValueError,pattern):self.ctl.wait_supervisor(self.c['slots'][0],launch,ticks,self.c['pilot_claim'])
            self.assertIsNone(child.poll())

    def test_empty_exit_transition_argv_is_not_completion_or_changed_live_command(self):
        state=dict(state='R',start_ticks=self.c['pilot_start_ticks'],argv=[])
        observations=[]
        def observed(pid):
            observations.append(pid);return state if len(observations)==1 else None
        original=self.ctl.validate_receipt
        def receipt(*args):
            self.assertEqual(len(observations),2);return original(*args)
        with mock.patch.object(module,'proc',side_effect=observed),mock.patch.object(self.ctl,'validate_receipt',side_effect=receipt):
            self.ctl.wait_supervisor(self.c['slots'][0],self.c['pilot_launch'],self.c['pilot_start_ticks'],self.c['pilot_claim'])
        self.assertEqual(self.children,[])

    def test_claim_and_dependency_changes_stop_without_next_launch(self):
        self.bound.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'dependency changed'):self.ctl.run()
        self.assertEqual(self.children,[])

    def test_changed_prefix_gate_next_command_cannot_select_another_slot(self):
        with mock.patch.object(module.operations,'complete_prefix',return_value={'next_argv':['wrong']}):
            with self.assertRaisesRegex(ValueError,'next argv differs'):self.ctl.run()
        self.assertEqual(self.children,[])

    def test_final_completed_manifest_must_equal_frozen_template(self):
        self.ctl.record['completed']=[dict(label=s['label'],session_manifest=s['session_manifest']) for s in self.c['slots']]
        self.ctl.record['completed'][3]['session_manifest']='wrong'
        with self.assertRaisesRegex(ValueError,'path binding'):self.ctl.finish()
        self.assertFalse((self.root/'coordinator-acquisition.json').exists())

    def test_prior_claim_refuses_duplicate_producer_before_popen(self):
        Path(self.c['slots'][1]['supervisor_receipt']).with_suffix('.claim').write_text('{}')
        with self.assertRaisesRegex(ValueError,'prior evidence/claim/log'):self.ctl.run()
        self.assertEqual(self.children,[])

    def test_duplicate_coordinator_refuses_before_journal_or_input_read(self):
        with (self.root/'retention-coordinator.lock').open('a') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with mock.patch.object(module,'EXTERNAL',self.root),mock.patch.object(module,'load_inputs') as load:
                with self.assertRaises(BlockingIOError):module.main(['--run-fixed-cohort'])
                load.assert_not_called()
            self.assertFalse(self.ctl.journal.exists())

    def test_help_or_missing_explicit_run_flag_cannot_acquire_lock_or_launch(self):
        with mock.patch.object(module,'singleton') as lock:
            for argv in ([],['--help']):
                with self.assertRaises(SystemExit):module.main(argv)
            lock.assert_not_called();self.assertEqual(self.children,[])


class RetentionCoordinatorPinsTests(unittest.TestCase):
    def test_actual_source_and_launch_metadata_pins_without_target_transcript(self):
        context=module.load_inputs()
        self.assertEqual([s['label'] for s in context['slots']],module.LABELS)
        self.assertEqual(context['pilot_launch']['pid'],592242)
        self.assertEqual(context['pilot_start_ticks'],84884232)
        self.assertEqual(context['producer']['sha256'],'0c8829b2882cb2db0f2e156bff95b41e990c3e91e99125450e5149e26d752f18')

    def test_changed_pilot_claim_binding_fails_before_any_launch(self):
        real=module.operations.frozen.artifact
        pins=json.loads(module.PINS.read_text());path=Path(pins['pilot_claim']['path'])
        def changed(candidate):
            value=real(candidate)
            return dict(value,sha256='0'*64) if candidate==path else value
        with mock.patch.object(module.operations.frozen,'artifact',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'dependency changed'):module.load_inputs()


if __name__=='__main__':unittest.main()
