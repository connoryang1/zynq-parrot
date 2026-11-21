#!/usr/bin/env python3
"""Default-offline COST promotion wrapper; reuse safe engine and exact old guest."""
import argparse
import fcntl
import json
import signal
import time
from pathlib import Path

import retained29_cost_cohort_protocol as p
import run_retained29_cost_session as guest_client


def ledger_read(path,cohort):
    if path.exists():
        value=json.loads(path.read_text())
        p.require(value['schema']=='bp-retained29-cost-acquisition-ledger-v1' and value['cohort']==cohort,'existing ledger identity')
        return value
    return dict(schema='bp-retained29-cost-acquisition-ledger-v1',cohort=cohort,entries=[])


class Operations(p.safe.Operations):
    def __init__(self,a,core,output,env,sources,guest_handler,input_record):
        self.input_record=input_record;self.ledger_lock=None;self.ledger=None;self.entry=None
        super().__init__(a,core,output,env,sources,guest_handler)

    def stage(self):
        # This hook runs only AFTER the safe engine acquires the common board
        # reservation. A busy reservation never records/consumes a target slot.
        _,cohort,visit=p.static_admission(self.wrapper)
        self.ledger_path=Path(cohort['ledger_path'])
        self.ledger_lock=self.ledger_path.with_name('acquisition-ledger.lock').open('a+')
        fcntl.flock(self.ledger_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.ledger=ledger_read(self.ledger_path,self.wrapper['cohort'])
        entries=self.ledger['entries']
        p.require(len(entries)==visit['order'] and all(e['state']=='PASS' for e in entries),'earlier failure/running attempt or retry forbidden')
        p.require([e['result'] for e in entries]==self.wrapper['prior_results'],'ledger exact prior-slot acceptance')
        p.require(all(e['order']==n and e['id']==p.canonical_visits()[n]['id'] for n,e in enumerate(entries)),'ledger fixed prior-slot order')
        self.entry=dict(order=visit['order'],id=visit['id'],state='running',input=self.input_record,
                        started_utc=p.safe.now(),result=None,boot_id=None)
        entries.append(self.entry)
        p.safe.journal(self.ledger_path,self.ledger)
        # No physical operation may precede the durable single-attempt claim.
        return super().stage()

    def guest(self):
        preflight=self.inspect()['preflight']
        previous={e['boot_id'] for e in self.ledger['entries'][:-1]}
        self.entry['boot_id']=p.validate_fresh_boot(preflight,previous)
        p.safe.journal(self.ledger_path,self.ledger)
        path=self.output/'console.log'
        self.own_guest=dict(local_log=str(path),preflight=preflight)
        self.record(state='bound old2dd kernel helper starts after unique acquisition boot proof')
        result=self.guest_handler(self.wrapper,self.admission,path,self.env,self.scripts/'run_pynq_interactive.sh')
        self.own_guest=None;self.record(state='complete guest normal return')
        return result

    def finish_attempt(self,success,result=None,error=None):
        if self.entry is not None:
            self.entry.update(state='PASS' if success else 'FAIL',result=result,error=error,closed_utc=p.safe.now())
            p.safe.journal(self.ledger_path,self.ledger)

    def close_ledger(self):
        if self.ledger_lock is not None:self.ledger_lock.close();self.ledger_lock=None


def guest(a,core,path,env,runner):
    return guest_client.run_guest(a['session'],path,env,runner=runner)


def persist_failed_attempt(ops,error,record,wait):
    # Physical recovery has already completed in the unchanged safe engine.
    # Keep cohort authority until FAIL is durably recorded, even if a PASS
    # replace succeeded before fsync raised. Only local reporting is retried.
    handlers={sig:signal.signal(sig,signal.SIG_IGN) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    try:
        while True:
            try:ops.finish_attempt(False,result=record,error=repr(error));return
            except OSError:
                try:wait(10)
                except OSError:pass
    finally:
        for sig,handler in handlers.items():signal.signal(sig,handler)


def execute(a,output,input_record,engine=p.safe.execute,failure_wait=time.sleep):
    holders=[]
    def interrupted(sig,frame):raise KeyboardInterrupt('cohort wrapper interrupted signal '+str(sig))
    handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    def factory(*args):
        ops=Operations(*args,input_record=input_record);holders.append(ops);return ops
    try:
        result=engine(a,output,p,guest,operations=factory,admission_record=input_record)
        record=p.binding(output/'session.json')
        p.verify_session(record,a['cohort'],p.verify_prefix(a))
        p.require(holders and holders[0].entry is not None,'actual claimed cohort slot')
        holders[0].finish_attempt(True,result=record)
        return result
    except BaseException as error:
        if holders:
            # If this write fails, the durable running entry remains and blocks
            # every subsequent slot. Verified recovery is handled by safe engine.
            try:record=p.binding(output/'session.json') if (output/'session.json').is_file() else None
            except OSError:record=None
            persist_failed_attempt(holders[0],error,record,failure_wait)
        raise
    finally:
        for ops in holders:ops.close_ledger()
        for sig,handler in handlers.items():signal.signal(sig,handler)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('admission',type=Path,nargs='?')
    parser.add_argument('--execute',type=Path)
    parser.add_argument('--request-recovery',type=Path)
    parser.add_argument('--verify-complete',type=Path)
    parser.add_argument('--cohort',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args(argv)
    if args.request_recovery is not None:
        p.require(args.admission is None and args.execute is None and args.verify_complete is None,'fixed recovery-only action')
        p.safe.request_recovery(args.request_recovery);return
    if args.verify_complete is not None:
        p.require(args.admission is None and args.execute is None and args.cohort is not None and args.out is not None and not args.out.exists(),'new complete-cohort proof only')
        proof=p.verify_complete(p.binding(args.cohort),p.binding(args.verify_complete))
        p.safe.journal(args.out,proof);return
    p.require(args.admission is not None,'promotion admission required')
    a=json.loads(args.admission.read_text())
    if args.execute is not None:execute(a,args.execute,p.binding(args.admission))
    elif a.get('state')=='DRAFT-UNLAUNCHABLE':print('RETAINED29_COST_PROMOTION_DRAFT_UNLAUNCHABLE=1')
    else:p.validate_admission(a);print('RETAINED29_COST_PROMOTION_OFFLINE_ADMISSION_OK=1')


if __name__=='__main__':main()
