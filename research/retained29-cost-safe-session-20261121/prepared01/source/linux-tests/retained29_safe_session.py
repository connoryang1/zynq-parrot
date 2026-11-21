"""Shared old2dd safe session operations; no legacy execute/unlock delegation."""
import hashlib
import json
from pathlib import Path
import re
import signal
import os
import sys
import tempfile
import time

import retained29_protocol as p
import retained29_safe_guard as guard
import retained29_stage_v2 as stage
import run_retained29_session as maintained
import run_retained29_session_v2 as stage_client
from run_retained29_application_session import journal,now

ENGINE_SCHEMA='bp-retained29-safe-engine-v1'
REQUEST_SCHEMA='bp-retained29-safe-recovery-request-v1'

class BoardUnreachable(ValueError):pass


class Operations(stage_client.Operations):
    def __init__(self,a,core,output,env,sources,guest_handler):
        self.a=core;self.wrapper=a;self.sources=sources;self.guest_handler=guest_handler
        self.token=hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()[:16]
        self.power_pending=None;self.own_guest=None;self.guard_witness=None;self.guard_cleanup=None;self.steps=0
        super().__init__(core,output,env)

    def save(self):journal(self.output/'stage-v2-receipt.json',self.receipt)

    def record(self,**values):
        values.update(token=self.token,power_pending=self.power_pending,own_guest=self.own_guest,
            guard_witness=self.guard_witness,guard_cleanup=self.guard_cleanup,
            mutation_started=self.mutation_started,stage_complete=self.stage_complete)
        journal(self.output/'safe-publication.json',values)

    def step(self,name,argv,timeout=600):
        self.steps+=1
        for relative,expected in self.sources.items():
            p.require(p.binding(self.output/'host-sources'/relative)['sha256']==expected,'immutable safe source snapshot drift')
        return super().step('%04d-%s'%(self.steps,name),argv,timeout)

    def inspect(self,expected=p.RUNNER_SHA):
        return dict(preflight=guard.idle(self.probe(),expected))

    def stage(self):
        self.inspect()
        return super().stage()

    def requires_recovery(self):return self.mutation_started or self.stage_complete or self.power_pending is not None or self.own_guest is not None

    def _maintained_power(self,label,expected):
        for name in ('power_cycle_pynq','wait_pynq_ready','load_pynq_overlay'):
            text=self.step(label+'-'+name,[str(self.scripts/(name+'.sh')),self.admission['host']])
        p.require('LOADING_BIT_SHA256='+expected in text and 'REMOTE_FPGA_STATE_OK=1' in text
            and 'REMOTE_OVERLAY_LOAD_OK=1' in text,'actual safe power/readiness/overlay/operating')

    def context(self):
        p.require(self.own_guest is not None,'no started own Linux helper')
        path=Path(self.own_guest['local_log']);p.require(path.is_file(),'no own helper start output')
        lines=p.clean_lines(path.read_text(errors='replace'));image=Path(self.admission['artifacts']['nbf']['path']).name
        for key,value in [('CONTROL_PROGRAM_SHA256',p.RUNNER_SHA),('NBF_SHA256',p.NBF_SHA),('BITSTREAM_SHA256',self.expected_bit())]:
            p.require([s for s in lines if s.startswith(key+'=')]==[key+'='+value],'bound started helper '+key)
        logs=[s[4:] for s in lines if s.startswith('LOG=')]
        pattern=r'/home/xilinx/bp-logs/'+re.escape(image[:-4])+r'-interactive-[0-9]{8}T[0-9]{6}Z-([1-9][0-9]*)\.log'
        p.require(len(logs)==1 and re.fullmatch(pattern,logs[0]),'exact own kernel/helper/PID log')
        return dict(token=self.token,image=image,pid=int(re.fullmatch(pattern,logs[0])[1]),log=logs[0],
            bit_sha256=self.expected_bit(),preflight=self.own_guest['preflight'])

    def expected_bit(self):
        if self.stage_complete:return self.admission['artifacts']['bit']['sha256']
        p.require(self.original is not None,'no verified prior overlay for partial stage')
        return self.original['bit']['sha256']

    def recover(self,label):
        expected=self.expected_bit()
        if label=='final':
            self.resolve_idle_for_final(expected)
            if not self.stage_complete and self.mutation_started:self.restore_original()
            self.own_guest=None
        self.power(label,expected);self.inspect()
        after=self.audit(label+'-full-inventory')
        if self.stage_complete:
            decision=stage.plan(self.admission,self.outer['package_bundle'],self.outer['load_stem'],after)
            p.require(decision['action']=='reuse-complete','recovered full package/NBF/collateral identity')
        else:
            for suffix,record in self.original.items():
                actual=after['files']['load.'+suffix]
                p.require(not actual['missing'] and all(actual[k]==record[k] for k in ('bytes','sha256')),'recovered prior collateral')
        self.record(state='verified old2dd/helper/overlay/operating recovery',label=label,inventory=after)

    def guest(self):
        preflight=self.inspect()['preflight'];path=self.output/'console.log'
        self.own_guest=dict(local_log=str(path),preflight=preflight)
        self.record(state='bound old2dd kernel helper starts after absent-guard idle preflight')
        result=self.guest_handler(self.wrapper,self.admission,path,self.env,self.scripts/'run_pynq_interactive.sh')
        self.own_guest=None;self.record(state='complete guest normal return')
        return result

    def guard_rpc(self,action,context=None,witness=None):
            try:text=self.step('guard-'+action,guard.command(self.a['host'],action,context,witness),60)
            except ValueError as error:
                # The fixed Python RPC never exits255. SSH uses255 for connection
                # failure; assertion/identity/process failures remain refused.
                if str(error).endswith(' failed rc=255'):raise BoardUnreachable(str(error))
                raise
            return json.loads(text)

    def probe(self):return self.guard_rpc('probe')

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
            self._maintained_power(label,expected)
            after=self.probe()
            p.require(after['boot_id']!=authority['preflight']['boot_id'],'actual new boot required after own power')
            if after['active_control'] or after['active_script'] or after['active_helper'] or (not allow_owned_guard and after['guard'] is not None):
                # A newly booted foreign actor/guard must not inherit our previous
                # interrupted-power reset authority if transport later disappears.
                self.power_pending=None
            if allow_owned_guard:
                p.require(after['control_sha256']==p.RUNNER_SHA and after['helper_sha256']==p.HELPER_SHA
                    and not after['active_control'] and not after['active_script'] and not after['active_helper'],'post-reboot known idle processes before guard cleanup')
            else:guard.idle(after,p.RUNNER_SHA)
            self.record(state='own power/new-boot/overlay verified',post_power=after)
            self.power_pending=None
            return after

    def power(self,label,expected):
            snapshot=self.inspect(p.RUNNER_SHA)['preflight']
            return self._power(label,expected,dict(kind='verified-idle-preflight',preflight=snapshot))

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


def request_recovery(output):
    state=json.loads((output/'session.json').read_text())
    p.require(state['safe_engine_schema']==ENGINE_SCHEMA and state['state']=='recovery-required-reservation-held','live held diagnostic recovery required')
    intent=dict(schema=REQUEST_SCHEMA,action='recover-only',token=state['recovery_token'],attempt=state['recovery_attempts']+1)
    with tempfile.NamedTemporaryFile(mode='w',dir=output,prefix='.recover-',delete=False) as stream:
        temp=Path(stream.name);json.dump(intent,stream);stream.flush();os.fsync(stream.fileno())
    try:os.link(temp,output/'recovery-request.json')
    finally:temp.unlink()
    descriptor=os.open(str(output),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)

def execute(a,output,contract,guest_handler,operations=Operations,recovery_wait=time.sleep,admission_record=None):
    core=contract.validate_admission(a);sources=contract.bound_sources(a)
    contract.acquisition_ready(a,now())
    p.require(admission_record is not None,'exact safe wrapper input binding required')
    p.verify_binding(admission_record)
    p.require(json.loads(Path(admission_record['path']).read_text())==a,'safe wrapper input changed')
    p.require(not output.exists(),'new safe output required')
    with p.maintained_session.reservation():
        output.mkdir(parents=True)
        for relative in sources:
            src=p.ROOT/relative;target=output/'host-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(src.read_bytes());target.chmod(src.stat().st_mode&0o777)
        state=dict(schema=contract.SCHEMA,safe_engine_schema=ENGINE_SCHEMA,state='reserved',started_utc=now(),
            supervisor_pid=os.getpid(),admission=core,supervisor_admission=a,supervisor_sources=sources,
            supervisor_admission_record=admission_record,
            guest_boots=0,performance_accepted=False,safe_recovery_verified=False,recovery_attempts=0,recovery_history=[],
            recovery_token=hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest())
        state.update(contract.result_metadata(a,core))
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
            try:print('RETAINED29_SAFE_RECOVERY_HELD_IO_ERROR='+repr(error),file=sys.stderr,flush=True)
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
            ops=operations(a,core,output,maintained.environment(core),sources,guest_handler);contract.verify_sources(a);contract.verify_artifacts(a)
            ops.stage();ops.recover('initial');ops.remote_identity()
            state['guest_boots']=1;save();state['guest']=ops.guest();contract.verify_sources(a);contract.verify_artifacts(a)
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
                                p.require(set(intent)=={'schema','action','token','attempt'} and intent['schema']==REQUEST_SCHEMA
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
                    state['recovery']='complete before reservation release';state['safe_recovery_verified']=True
                    state['recovery_history'].append(dict(attempt=state['recovery_attempts'],state='verified',utc=now()));break
            else:state['recovery']='no mutation or target began'
            try:contract.verify_sources(a)
            except BaseException as error:
                if failure is None:failure=error
                state.update(state='FAIL',error=repr(error))
            # Physical recovery is verified (or no mutation ever occurred).
            # Terminal reporting failure may now close FAIL, never false PASS.
            try:
                state['operation_logs']={path.name:p.binding(path) for path in sorted(output.glob('*.log'))}
                if (output/'safe-publication.json').is_file():state['operation_journal']=p.binding(output/'safe-publication.json')
            except OSError as error:
                if failure is None:failure=error
                state['terminal_io_error']=repr(error)
            state['state']=contract.SUCCESS_STATE if failure is None else 'FAIL'
            state['reservation_release_utc']=now()
            if state['safe_recovery_verified']:state['release_after_recovery_utc']=state['reservation_release_utc']
            try:
                try:save()
                except OSError as error:
                    if failure is None:failure=error
                    state.update(state='FAIL',terminal_io_error=repr(error))
                    try:save()
                    except OSError:
                        try:print('RETAINED29_SAFE_FAIL_AFTER_VERIFIED_RECOVERY_REPORT_IO',file=sys.stderr,flush=True)
                        except OSError:pass
            finally:
                for sig,handler in handlers.items():signal.signal(sig,handler)
        if failure is not None:raise failure
    return state
