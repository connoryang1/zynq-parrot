#!/usr/bin/env python3
"""V3 offline capacity diagnostic; keep reservation through recoverable I/O faults."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import tempfile
import time
import sys

import retained_capacity_diagnostic_v3 as p
import retained_capacity_recovery_v3 as guard
import run_retained_capacity_diagnostic as legacy
from run_retained29_application_session import journal,now

maintained=legacy.maintained
verify_files=legacy.verify_files
run_case=legacy.run_case


def verify_sources(a):p.require(p.source_hashes()==a['sources'],'v3 runtime source drift')


class BoardUnreachable(ValueError):pass


class Operations(legacy.Operations):
    """Keep reviewed atomic install/staging; add explicit power/guard authority."""
    def __init__(self,*args):
        super().__init__(*args)
        self.power_pending=None;self.own_guest=None;self.guard_witness=None;self.guard_cleanup=None

    def record(self,**values):
        values.update(power_pending=self.power_pending,own_guest=self.own_guest,
            guard_witness=self.guard_witness,guard_cleanup=self.guard_cleanup)
        values.update(token=self.token,original=self.original,original_overlay=self.original_overlay,
            mutation_started=self.mutated,stage_complete=self.staged,installed=self.installed,guest_started=self.guest_started)
        # Publication remains strict: a failed durable witness/authority write
        # must prevent the following power operation, not silently authorize it.
        journal(self.output/'publication.json',values)

    def guard_rpc(self,action,context=None,witness=None):
        try:text=self.step('guard-'+action,guard.command(self.a['host'],action,context,witness),60)
        except ValueError as error:
            # The fixed Python RPC never exits255. SSH uses255 for connection
            # failure; assertion/identity/process failures remain refused.
            if str(error).endswith(' failed rc=255'):raise BoardUnreachable(str(error))
            raise
        return json.loads(text)

    def probe(self):return self.guard_rpc('probe')

    def inspect(self,expected=None):
        snapshot=guard.idle(self.probe(),expected)
        result=super().inspect(expected);result['preflight']=snapshot
        return result

    def _power(self,label,expected,authority,allow_owned_guard=False):
        p.require(authority['kind'] in ('verified-idle-preflight','bound-own-helper-witness'),'own power authority required')
        if authority['kind']=='bound-own-helper-witness':
            p.require(self.guard_witness is not None and self.guard_witness['guard_durable'] is True
                and self.guard_witness['sync_complete'] is True,'board-side durable own witness required')
        previous=self.power_pending
        self.power_pending=dict(label=label,expected_bit=expected,authority=authority)
        try:self.record(state='own power provenance recorded before maintained helper')
        except BaseException:
            self.power_pending=previous
            raise
        # No new reset/halt mechanism: run the exact maintained sequence.
        super().power(label,expected)
        after=self.probe()
        p.require(after['boot_id']!=authority['preflight']['boot_id'],'actual new boot required after own power')
        if after['active_control'] or after['active_script'] or after['active_helper'] or (not allow_owned_guard and after['guard'] is not None):
            # A newly booted foreign actor/guard must not inherit our previous
            # interrupted-power reset authority if transport later disappears.
            self.power_pending=None
        if allow_owned_guard:
            p.require(after['control_sha256'] in (p.OLD,p.RUNNER) and after['helper_sha256']==p.HELPER
                and not after['active_control'] and not after['active_script'] and not after['active_helper'],'post-reboot known idle processes before guard cleanup')
        else:guard.idle(after,p.RUNNER if self.installed else p.OLD)
        self.record(state='own power/new-boot/overlay verified',post_power=after)
        self.power_pending=None
        return after

    def power(self,label,expected):
        snapshot=self.inspect(p.RUNNER if self.installed else p.OLD)['preflight']
        return self._power(label,expected,dict(kind='verified-idle-preflight',preflight=snapshot))

    def context(self):
        p.require(self.own_guest is not None,'no started own guest')
        source=Path(self.own_guest['local_log']);p.require(source.is_file(),'no bound helper start output')
        lines=p.base.clean_lines(source.read_text(errors='replace'));role=self.own_guest['role']
        for key,value in [('CONTROL_PROGRAM_SHA256',p.RUNNER),('NBF_SHA256',p.NBFS[role]),
            ('BITSTREAM_SHA256',self.a['artifacts']['bit']['sha256'])]:
            p.require([s for s in lines if s.startswith(key+'=')]==[key+'='+value],'bound started helper '+key)
        logs=[s[4:] for s in lines if s.startswith('LOG=')]
        pattern=r'/home/xilinx/bp-logs/retained-capacity1280-'+role+r'-interactive-[0-9]{8}T[0-9]{6}Z-([1-9][0-9]*)\.log'
        p.require(len(logs)==1 and re.fullmatch(pattern,logs[0]),'exact own helper/NBF/PID log')
        return dict(token=self.token,role=role,pid=int(re.fullmatch(pattern,logs[0])[1]),log=logs[0],
            bit_sha256=self.a['artifacts']['bit']['sha256'],preflight=self.own_guest['preflight'])

    def resolve_idle_for_final(self,expected):
        try:current=self.probe()
        except BoardUnreachable:
            pending=self.power_pending
            p.require(pending is not None,'unreachable board without our interrupted power sequence')
            authority=pending['authority']
            if authority['kind']=='bound-own-helper-witness':
                p.require(self.guard_witness is not None and self.guard_witness['context']==authority['context']
                    and self.own_guest is not None,'recorded own guard witness required for interrupted quiesce')
                self._power('resume-owned-interrupted-quiesce',expected,authority,allow_owned_guard=True)
                return self.resolve_idle_for_final(expected)
            p.require(authority['kind']=='verified-idle-preflight' and self.own_guest is None,
                'unreachable board without our interrupted idle power sequence')
            # This authority was recorded before our power helper. A failed
            # preflight never reaches it; a reachable unknown guard is refused.
            self._power('resume-owned-interrupted-power',expected,authority)
            return guard.idle(self.probe())
        if current['guard'] is None and not current['active_control'] and not current['active_script'] and not current['active_helper']:
            return guard.idle(current)
        context=self.context()
        if self.guard_witness is not None and current['boot_id']!=self.guard_witness['old_boot_id']:
            witness=self.guard_witness
        else:
            witness=self.guard_rpc('witness',context)
            self.guard_witness=witness
            self.record(state='actual own guard/old boot witness recorded before quiesce power')
            self._power('quiesce-bound-own-helper',expected,
                dict(kind='bound-own-helper-witness',preflight=context['preflight'],context=context),allow_owned_guard=True)
        self.guard_cleanup=self.guard_rpc('remove-owned-stale',context,witness)
        p.require(self.guard_cleanup['state']=='PASS own-session stale guard recovery after verified reboot'
            and self.guard_cleanup['durable'] is True,'actual own stale guard removal/absence proof')
        self.record(state='only same proven own stale guard removed after verified new boot')
        return guard.idle(self.probe())

    def recover(self,label):
        if label!='final':
            self.power(label,self.a['artifacts']['bit']['sha256'])
            self.inspect(p.RUNNER if self.installed else p.OLD)
            p.require(self.matched(self.inventory()),'post-power complete stage identity')
            return
        expected=self.a['artifacts']['bit']['sha256'] if self.staged else self.a['rollback_overlay']['bit']['sha256']
        self.resolve_idle_for_final(expected)
        self.restore_runner()
        if not self.staged and self.mutated:self.restore_overlay()
        # Reset provenance from the failed guest is no longer authority to run
        # it again. Final recovery still freshly verifies idle and absent guard.
        self.own_guest=None
        self.power('final',expected);self.inspect(p.OLD)
        final=self.inventory()
        if self.staged:p.require(self.matched(final),'final complete requested collateral readback')
        else:
            for suffix,record in self.a['rollback_overlay'].items():
                actual=final['files']['load.'+suffix]
                p.require(not actual['missing'] and all(actual[k]==record[k] for k in ('bytes','sha256')),'final reviewed prior overlay collateral')
        self.record(state='accepted2dd/helper/overlay/operating recovered before unlock')

    def guest(self):
        self.install_runner();results=[]
        for index,role in enumerate(p.ROLES):
            if index:self.recover('between-'+role)
            self.phase='case-'+role;preflight=self.inspect(p.RUNNER)['preflight'];verify_sources(self.a);verify_files(self.a)
            self.guest_started=True;self.guard_witness=None;self.guard_cleanup=None
            path=self.output/(role+'.log');self.own_guest=dict(role=role,local_log=str(path),preflight=preflight)
            self.record(state='bound own fixture begins after verified idle/absent guard',role=role)
            result=run_case(self.a,role,path,self.env,self.scripts/'run_pynq_interactive.sh')
            results.append(result);self.own_guest=None
            self.record(state='fixture completed',role=role,complete_cases=[r['role'] for r in results])
        return results


def request_recovery(output):
    state=json.loads((output/'session.json').read_text())
    p.require(state['schema']==p.SCHEMA and state['state']=='recovery-required-reservation-held','live held diagnostic recovery required')
    intent=dict(schema='bp-capacity-recovery-request-v3',action='recover-only',token=state['recovery_token'],attempt=state['recovery_attempts']+1)
    with tempfile.NamedTemporaryFile(mode='w',dir=output,prefix='.recover-',delete=False) as stream:
        temp=Path(stream.name);json.dump(intent,stream);stream.flush();os.fsync(stream.fileno())
    try:os.link(temp,output/'recovery-request.json')
    finally:temp.unlink()
    descriptor=os.open(str(output),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)

def execute(a,output,operations=Operations,recovery_wait=time.sleep):
    p.validate(a);p.require(not output.exists(),'new diagnostic output required')
    with p.base.maintained_session.reservation():
        output.mkdir(parents=True)
        for relative in p.SOURCE_FILES:
            src=p.ROOT/relative;target=output/'host-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(src.read_bytes());target.chmod(src.stat().st_mode&0o777)
        state=dict(schema=p.SCHEMA,state='reserved',started_utc=now(),supervisor_pid=os.getpid(),admission=a,
            sources=a['sources'],schedule=list(p.ROLES),performance_inference=False,recovery_attempts=0,recovery_history=[],
            recovery_token=hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest())
        path=output/'session.json'
        def save():journal(path,state)
        def io_failure(error):
            # Once mutation occurred, reporting/intent I/O cannot unwind the
            # reservation. Keep the failure in memory and retry only local I/O
            # while awaiting the fixed recovery-only request.
            nonlocal failure
            if failure is None:failure=error
            state['state']='recovery-required-reservation-held'
            state['recovery']='unconfirmed'
            state['local_io_error']=repr(error)
            try:print('CAPACITY_V3_RECOVERY_HELD_IO_ERROR='+repr(error),file=sys.stderr,flush=True)
            except OSError:pass
        def best_effort_save():
            try:save();return True
            except OSError as error:io_failure(error);return False
        def wait_short():
            try:recovery_wait(10)
            except OSError as error:io_failure(error)
        save();ops=None;failure=None
        def interrupted(sig,frame):raise KeyboardInterrupt('interrupted signal '+str(sig))
        handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
        try:
            ops=operations(a,output,maintained.environment(a));verify_sources(a);verify_files(a)
            ops.stage();ops.recover('initial');state['cases']=ops.guest();verify_sources(a);verify_files(a)
        except BaseException as error:failure=error;state.update(state='FAIL',error=repr(error))
        finally:
            for sig in handlers:signal.signal(sig,signal.SIG_IGN)
            if ops is not None and ops.requires_recovery():
                while True:
                    state['recovery_attempts']+=1;state['state']='recovery-in-progress-reservation-held'
                    try:
                        save()
                        ops.recover('final')
                    except BaseException as error:
                        if failure is None:failure=error
                        state.update(state='recovery-required-reservation-held',recovery='unconfirmed',recovery_error=repr(error))
                        state['recovery_history'].append(dict(attempt=state['recovery_attempts'],error=repr(error),utc=now()))
                        best_effort_save()
                        request=output/'recovery-request.json'
                        while True:
                            # Repair/reporting failures never authorize another
                            # physical attempt. Only a valid explicit intent can.
                            best_effort_save()
                            try:
                                if not request.exists():wait_short();continue
                                intent=json.loads(request.read_text())
                                p.require(set(intent)=={'schema','action','token','attempt'} and intent['schema']=='bp-capacity-recovery-request-v3'
                                    and intent['action']=='recover-only' and intent['token']==state['recovery_token']
                                    and type(intent['attempt']) is int and intent['attempt']==state['recovery_attempts']+1,'invalid fixed recovery request')
                            except (ValueError,TypeError,KeyError) as error:
                                count=len(state.setdefault('rejected_recovery_requests',[]))+1
                                try:
                                    kept=output/('recovery-request-rejected-%04d.json'%count);request.replace(kept)
                                    state['rejected_recovery_requests'].append(dict(request=p.binding(kept),error=repr(error)))
                                    best_effort_save()
                                except OSError as fault:io_failure(fault);wait_short()
                                continue
                            except OSError as error:io_failure(error);wait_short();continue
                            try:request.replace(output/('recovery-request-attempt-%04d.json'%intent['attempt']))
                            except OSError as error:io_failure(error);wait_short();continue
                            break
                        continue
                    state['recovery']='accepted2dd restored and overlay/operating/helper verified before unlock'
                    state['recovery_history'].append(dict(attempt=state['recovery_attempts'],state='verified',utc=now()));break
            else:state['recovery']='no mutation or target began'
            try:verify_sources(a)
            except BaseException as error:
                if failure is None:failure=error
                state.update(state='FAIL',error=repr(error))
            # Physical recovery is verified (or no mutation ever occurred).
            # Terminal reporting failure may now close FAIL, never false PASS.
            try:
                state['operation_logs']={path.name:p.binding(path) for path in sorted(output.glob('*.log'))}
                if (output/'publication.json').is_file():state['operation_journal']=p.binding(output/'publication.json')
            except OSError as error:
                if failure is None:failure=error
                state['terminal_io_error']=repr(error)
            state['state']='PASS-complete-rolled-back-capacity-diagnostic' if failure is None else 'FAIL'
            state['reservation_release_utc']=now()
            if state['recovery'].startswith('accepted2dd restored'):state['release_after_recovery_utc']=state['reservation_release_utc']
            try:
                try:save()
                except OSError as error:
                    if failure is None:failure=error
                    state.update(state='FAIL',terminal_io_error=repr(error))
                    try:save()
                    except OSError:
                        try:print('CAPACITY_V3_FAIL_AFTER_VERIFIED_RECOVERY_REPORT_IO',file=sys.stderr,flush=True)
                        except OSError:pass
            finally:
                for sig,handler in handlers.items():signal.signal(sig,handler)
        if failure is not None:raise failure
    return state

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('admission',type=Path,nargs='?')
    parser.add_argument('--execute',type=Path);parser.add_argument('--request-recovery',type=Path);args=parser.parse_args(argv)
    if args.request_recovery is not None:
        p.require(args.admission is None and args.execute is None,'fixed recovery-only request has no guest/admission arguments')
        request_recovery(args.request_recovery);print('CAPACITY_DIAGNOSTIC_RECOVERY_ONLY_REQUESTED=1');return
    p.require(args.admission is not None,'admission required');a=json.loads(args.admission.read_text())
    if args.execute is not None:execute(a,args.execute)
    elif a.get('state')=='DRAFT-UNLAUNCHABLE':print('CAPACITY_DIAGNOSTIC_DRAFT_UNLAUNCHABLE=1')
    else:p.validate(a);print('CAPACITY_DIAGNOSTIC_OFFLINE_ADMISSION_OK=1')


if __name__=='__main__':main()
