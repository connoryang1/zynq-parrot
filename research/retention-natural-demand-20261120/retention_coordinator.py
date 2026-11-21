#!/usr/bin/env python3
"""Finite root-owned retention continuation; explicit launch after review only."""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import retention_operations as operations

HERE=Path(__file__).resolve().parent
PINS=HERE/'retention-coordinator-pins.json'
EXTERNAL=Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/retention-natural-demand-20261120')
ACK=Path('/home/coyang/fpga-artifacts/pynq-session-ack-linux.json')
LABELS=['pilot','R1a','R1b','F1a','F1b','F2a','F2b','R2a','R2b']
OBSERVATION_SECONDS=6*60*60
CLAIM_SECONDS=120
POLL_SECONDS=2


def now():return datetime.now(timezone.utc).isoformat()


def new_json(path,value):
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')


def proc(pid):
    try:
        stat=Path(f'/proc/{pid}/stat')
        first=stat.read_text().rsplit(') ',1)[1].split()
        argv=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        fields=stat.read_text().rsplit(') ',1)[1].split()
    except FileNotFoundError:return None
    operations.require(first[19]==fields[19],'Process PID reused during identity read')
    return dict(state=fields[0],start_ticks=int(fields[19]),argv=[v.decode() for v in argv if v])


def verify(records):
    for binding in records:
        operations.require(operations.frozen.artifact(Path(binding['path']))==binding,
                           'Coordinator dependency changed: '+binding['path'])


def load_inputs():
    pins=json.loads(PINS.read_text());verify(pins['bindings'])
    operations.require(pins['observation_seconds']==OBSERVATION_SECONDS and pins['claim_seconds']==CLAIM_SECONDS,
                       'Observation caps differ from reviewed source')
    for key in ('coordinator','producer','operations','argv_table','validator','template','launch_admission',
                'supervisor_proof','bounded_proof','pilot_launch','pilot_claim'):
        operations.require(pins[key] in pins['bindings'],'Missing coordinator binding: '+key)
    operations.require(pins['coordinator']==operations.frozen.artifact(Path(__file__)),'Coordinator source changed')
    a,p,t,slots,records=operations.inputs()
    launch=json.loads(Path(pins['pilot_launch']['path']).read_text())
    claim=json.loads(Path(pins['pilot_claim']['path']).read_text())
    admission=json.loads(Path(pins['launch_admission']['path']).read_text())
    operations.require([s['label'] for s in slots]==LABELS==admission['planned_labels'],'Fixed slot order differs')
    operations.require(pins['producer']==admission['producer'] and pins['operations']==admission['operations']
        and pins['argv_table']==admission['argv_table'] and pins['validator']==admission['frozen_validator']
        and pins['bounded_proof']==admission['bounded_unsupported_hardware_gate'],'Launch proof bindings differ')
    operations.require(admission['pilot_argv']==slots[0]['argv'] and admission['maximum_guest_executions_per_reservation']==2
        and admission['automatic_retry'] is False and admission['performance_selection'] is False,'Launch admission shape differs')
    producer_argv=['python3','-u','-B',pins['producer']['path'],'pilot']
    operations.require(launch['producer_argv']==producer_argv==admission['producer_pilot_argv']
        and launch['canonical_wrapper_argv']==slots[0]['argv'] and launch['session_manifest']==slots[0]['session_manifest']
        and launch['supervisor_receipt']==slots[0]['supervisor_receipt'] and launch['launch_admission']==pins['launch_admission']
        and launch['label']=='pilot' and launch['pid']==pins['pilot_pid']==claim['pid']
        and claim['start_ticks']==pins['pilot_start_ticks'] and claim['argv']==slots[0]['argv'],'Pilot launch/claim identity differs')
    operations.require(operations.frozen.timestamp(admission['created_utc'])<operations.frozen.timestamp(launch['started_utc']),
                       'Pilot predates launch admission')
    operations.require(Path(slots[0]['session_manifest']).parent.parent==EXTERNAL
        and all(Path(s['session_manifest']).parent==EXTERNAL/s['label'] for s in slots),'Output path differs from reviewed study root')
    records+=pins['bindings']+[pins['coordinator'],operations.frozen.artifact(PINS)]
    fast=[b for b in records if b['bytes']<100000 and Path(b['path']).suffix in ('.py','.json')]
    return dict(slots=slots,template=t,producer=pins['producer'],bounded_proof=pins['bounded_proof'],
        launch_admission=pins['launch_admission'],pilot_launch=launch,pilot_start_ticks=claim['start_ticks'],
        pilot_claim=pins['pilot_claim'],bindings=records,fast_bindings=fast,
        coordinator=operations.frozen.artifact(Path(__file__)),pins=operations.frozen.artifact(PINS))


@contextmanager
def singleton(root):
    with (root/'retention-coordinator.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


class Coordinator:
    def __init__(self,context,root=EXTERNAL,ack=ACK):
        self.c=context;self.root=root;self.ack=ack
        self.journal=root/'retention-coordinator-journal.json'
        self.acquired=[]
        self.record=dict(state='running',started_utc=now(),coordinator=context['coordinator'],pins=context['pins'],
            completed=[],active=None,acquired_bindings=self.acquired,automatic_retry=False,matched_lifecycle=operations.frozen.MATCHED)

    def save(self):
        # Only this singleton owns this new journal. Atomic replace keeps the
        # prior complete JSON if interrupted while preparing an update.
        tmp=self.journal.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(self.record,indent=2)+'\n');os.replace(tmp,self.journal)

    def ack_update(self,state,slot=None,pid=None):
        record=json.loads(self.ack.read_text())
        operations.require(record.get('worktree')==str(operations.frozen.ROOT)
            and record.get('acknowledged_reservation')=='/home/coyang/fpga-artifacts/pynq-session.lock',
            'Own ACK identity differs')
        record.update(state=state,updated_utc=now(),retention_coordinator=str(self.journal))
        if slot is not None:record['session_manifest']=slot['session_manifest']
        record['supervisor_pid']=pid
        tmp=self.ack.with_name(self.ack.name+'.retention-coordinator-tmp')
        tmp.write_text(json.dumps(record,indent=2)+'\n');os.replace(tmp,self.ack)

    def producer_argv(self,slot):return ['python3','-u','-B',self.c['producer']['path'],slot['label']]

    def claim(self,slot,pid):
        path=Path(slot['supervisor_receipt']).with_suffix('.claim')
        value=json.loads(path.read_text())
        operations.require(value['pid']==pid and type(value['start_ticks']) is int and value['start_ticks']>0
            and value['argv']==slot['argv'],'Supervisor claim identity differs')
        return value,operations.frozen.artifact(path)

    def validate_receipt(self,slot,launch,ticks,claim_binding):
        verify([claim_binding])
        receipt_path=Path(slot['supervisor_receipt'])
        operations.require(receipt_path.is_file() and not receipt_path.is_symlink(),'Supervisor missing without ending receipt')
        receipt=json.loads(receipt_path.read_text())
        operations.require(receipt.get('label')==slot['label'] and receipt.get('pid')==launch['pid']
            and receipt.get('start_ticks')==ticks and receipt.get('argv')==slot['argv']
            and receipt.get('session_manifest')==slot['session_manifest'],'Ending receipt identity differs')
        operations.require(receipt.get('state')=='complete' and receipt.get('runner_exit')==0,'Supervisor failed/busy/nonzero')
        operations.require(receipt.get('producer')==self.c['producer'] and receipt.get('bounded_absent_gate')==self.c['bounded_proof'],
                           'Ending receipt producer/compatibility provenance differs')
        return operations.frozen.artifact(receipt_path)

    def wait_supervisor(self,slot,launch,ticks,claim_binding,child=None):
        deadline=time.monotonic()+OBSERVATION_SECONDS
        while True:
            verify(self.c['fast_bindings']+self.acquired)
            state=proc(launch['pid'])
            if state is not None:
                operations.require(state['start_ticks']==ticks,'Supervisor PID reused/start identity changed')
                # Exit may empty cmdline between separate /proc reads before
                # stat reports Z. Empty argv never establishes completion; it
                # only keeps observing until absent/reaped or the same cap.
                if state['state']!='Z' and state['argv']:
                    operations.require(state['argv']==launch['producer_argv'],'Supervisor argv changed')
            # poll/wait reap our own children; a zombie must disappear before
            # operations.complete_prefix checks /proc. Adopted pilot is not
            # our child, so its owner/init must reap it; timeout is a stop.
            if child is not None and child.poll() is not None:
                code=child.wait()
                operations.require(code==0,'Producer child failed/busy/nonzero')
                operations.require(proc(launch['pid']) is None,'Reaped producer PID remains/reused')
                state=None
            if state is None:
                return self.validate_receipt(slot,launch,ticks,claim_binding)
            if time.monotonic()>=deadline:
                raise TimeoutError('Observation deadline; supervisor may remain live; do not restart or infer release')
            time.sleep(POLL_SECONDS)

    def launch(self,slot):
        verify(self.c['bindings'])
        out=Path(slot['session_manifest']).parent
        launch_path=self.root/(slot['label']+'-launch.json');log=self.root/(slot['label']+'-supervisor.log')
        claim=Path(slot['supervisor_receipt']).with_suffix('.claim')
        operations.require(not any(p.exists() for p in (out,Path(slot['supervisor_receipt']),claim,launch_path,log)),
                           'Fixed slot has prior evidence/claim/log; no retry')
        argv=self.producer_argv(slot);started=now()
        self.ack_update('launching next fixed retention reservation; no effect selection',slot)
        with log.open('xb') as stream:
            child=subprocess.Popen(argv,cwd=str(operations.frozen.ROOT),stdin=subprocess.DEVNULL,
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        self.record['active']=dict(label=slot['label'],pid=child.pid,producer_argv=argv)
        self.save()  # Preserve identity immediately, even if claim never appears.
        identity=proc(child.pid)
        if identity is None or identity['state']=='Z':
            if child.poll() is not None:child.wait()
            raise RuntimeError('Producer ended before initial identity capture; stop')
        operations.require(identity['argv']==argv,'New producer argv differs')
        deadline=time.monotonic()+CLAIM_SECONDS
        while True:
            if time.monotonic()>=deadline:raise TimeoutError('Claim deadline; producer may remain live; no restart')
            verify(self.c['fast_bindings'])
            try:value,claim_binding=self.claim(slot,child.pid)
            except (FileNotFoundError,json.JSONDecodeError):
                # The producer creates then writes its claim. An existing but
                # partial JSON file may be observed in that short interval.
                # Retry only under the original deadline and exact live PID.
                current=proc(child.pid)
                if current is None or current['state']=='Z':
                    if child.poll() is not None:child.wait()
                    raise RuntimeError('Dead producer has missing/malformed claim; no advancement')
                operations.require(current['start_ticks']==identity['start_ticks'] and current['argv']==argv,
                                   'Producer identity changed while awaiting claim')
                if time.monotonic()>=deadline:raise TimeoutError('Claim deadline; producer may remain live; no restart')
                time.sleep(min(POLL_SECONDS,.2,max(0,deadline-time.monotonic())));continue
            operations.require(value['start_ticks']==identity['start_ticks'],'Claim start identity differs from spawned producer')
            break
        launch=dict(label=slot['label'],pid=child.pid,producer_argv=argv,canonical_wrapper_argv=slot['argv'],
            session_manifest=slot['session_manifest'],supervisor_receipt=slot['supervisor_receipt'],
            launcher_log=str(log),launch_admission=self.c['launch_admission'],started_utc=started,
            coordinator=self.c['coordinator'],claim=claim_binding)
        new_json(launch_path,launch)
        self.acquired.extend([operations.frozen.artifact(launch_path),claim_binding])
        self.ack_update('observing exact retention supervisor; no next launch while live',slot,child.pid)
        return launch,value['start_ticks'],claim_binding,child

    def finish(self):
        verify(self.acquired)
        slots=self.c['slots'];completed=self.record['completed'];t=self.c['template']
        operations.require([r['label'] for r in completed]==LABELS==[s['label'] for s in slots],
                           'Final completed labels differ')
        expected=[t['pilot_session_manifest']]+[v['session_manifest'] for v in t['primary']]
        operations.require(expected==[s['session_manifest'] for s in slots]
            ==[r['session_manifest'] for r in completed],'Final template/completed path binding differs')
        acquisition=json.loads(json.dumps(t));acquisition['all_attempts_declared']=True
        operations.require(acquisition['failed_attempts']==[],'Failed attempt prevents fixed acquisition completion')
        path=self.root/'coordinator-acquisition.json';new_json(path,acquisition)
        new_json(self.root/'coordinator-audit.json',operations.frozen.audit(path))
        new_json(self.root/'coordinator-analysis.json',operations.frozen.analyze(path))
        verify(self.c['bindings'])
        self.record.update(state='complete; frozen full retention audit and analysis retained',finished_utc=now(),active=None,
            acquisition=operations.frozen.artifact(path),audit=operations.frozen.artifact(self.root/'coordinator-audit.json'),
            analysis=operations.frozen.artifact(self.root/'coordinator-analysis.json'))
        self.save();self.ack_update('fixed retention matrix complete; full frozen audit/analysis retained')

    def run(self):
        for name in ('coordinator-acquisition.json','coordinator-audit.json','coordinator-analysis.json'):
            operations.require(not (self.root/name).exists(),'Final output already exists; no restart')
        new_json(self.journal,self.record)
        try:
            for index,slot in enumerate(self.c['slots']):
                verify(self.c['bindings']+self.acquired)
                if index==0:
                    launch=self.c['pilot_launch'];ticks=self.c['pilot_start_ticks'];claim=self.c['pilot_claim'];child=None
                    self.record['active']=dict(label=slot['label'],pid=launch['pid'],producer_argv=launch['producer_argv']);self.save()
                else:launch,ticks,claim,child=self.launch(slot)
                self.ack_update('observing exact retention supervisor; no live advancement',slot,launch['pid'])
                receipt=self.wait_supervisor(slot,launch,ticks,claim,child)
                verify(self.c['bindings'])
                gate=operations.complete_prefix(slot['label'])
                wanted=self.c['slots'][index+1]['argv'] if index+1<len(self.c['slots']) else None
                operations.require(gate['next_argv']==wanted,'Frozen gate next argv differs from canonical schedule')
                gate_path=self.root/(slot['label']+'-coordinator-prefix-gate.json');new_json(gate_path,gate)
                self.acquired.extend([receipt,operations.frozen.artifact(gate_path)])
                self.record['completed'].append(dict(label=slot['label'],session_manifest=slot['session_manifest'],
                    launch_pid=launch['pid'],receipt=receipt,gate=operations.frozen.artifact(gate_path)))
                self.record['active']=None;self.save()
            self.finish();return 0
        except BaseException as error:
            self.record.update(state='stopped; no automatic retry/recovery; active supervisor may remain',error=repr(error),stopped_utc=now())
            self.save()
            try:self.ack_update('retention coordinator stopped; inspect journal/active supervisor; no restart',
                pid=(self.record['active'] or {}).get('pid'))
            except Exception as ack_error:
                self.record['ack_error']=repr(ack_error);self.save()
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-fixed-cohort',action='store_true',required=True)
    parser.parse_args(argv)
    # Only a local singleton is held by this controller. Each unchanged wrapper
    # separately acquires/releases the global NBflock and board-side runner lock.
    with singleton(EXTERNAL):
        operations.require(not (EXTERNAL/'retention-coordinator-journal.json').exists(),'Coordinator journal exists; no restart')
        context=load_inputs()
        def interrupted(*_):raise KeyboardInterrupt('SIGTERM; no child cleanup/restart')
        old=signal.signal(signal.SIGTERM,interrupted)
        try:return Coordinator(context).run()
        finally:signal.signal(signal.SIGTERM,old)


if __name__=='__main__':raise SystemExit(main())
