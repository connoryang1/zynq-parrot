#!/usr/bin/env python3
"""Fresh768 protocol on the unchanged V3 lock/atomic install/held-recovery lifecycle."""
import argparse,hashlib,json,os,re,signal,sys,tempfile,time
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,'/home/coyang/zynq-parrot-linux-capacity/linux-tests')
import pexpect
import protocol as p
import recovery as guard
import run_retained_capacity_diagnostic_v3 as qualified
from run_retained29_application_session import journal,now
maintained=qualified.maintained
BoardUnreachable=qualified.BoardUnreachable
verify_files=p.verify_files

def verify_sources(a):p.require(p.source_hashes()==a['sources'],'new exact768 runtime source drift')

def run_case(a,role,path,env,runner,spawn=pexpect.spawn):
    child=None;environment=dict(env,PYNQ_CONTROL_PROGRAM_SHA256=p.RUNNER,PYNQ_CONTROL_PROGRAM_TIMEOUT_MS='300000',
        PYNQ_BITSTREAM_SHA256=a['artifacts']['bit']['sha256'])
    try:
        child=spawn(str(runner),[a['host'],a['programs'][role]['path']],env=environment,encoding='utf-8',timeout=420)
        child.setwinsize(50,180)
        with path.open('w') as log:
            child.logfile_read=log;child.expect(pexpect.EOF,timeout=420)
        child.close();p.require(child.exitstatus==0 and child.signalstatus is None,'actual physical helper/program exit must be0')
        result=p.parse_console(path.read_text(errors='replace'),role,a['artifacts']['bit']['sha256'])
        return dict(result,actual_exit=0,signal=None,console=p.binding(path))
    finally:
        if child is not None and child.isalive():child.close(force=True)


class Operations(qualified.Operations):
    def guard_rpc(self,action,context=None,witness=None):
        try:text=self.step('guard-'+action,guard.command(self.a['host'],action,context,witness),60)
        except ValueError as error:
            # The fixed Python RPC never exits255. SSH uses255 for connection
            # failure; assertion/identity/process failures remain refused.
            if str(error).endswith(' failed rc=255'):raise BoardUnreachable(str(error))
            raise
        return json.loads(text)

    def context(self):
        p.require(self.own_guest is not None,'no started own guest')
        source=Path(self.own_guest['local_log']);p.require(source.is_file(),'no bound helper start output')
        lines=p.base.clean_lines(source.read_text(errors='replace'));role=self.own_guest['role']
        for key,value in [('CONTROL_PROGRAM_SHA256',p.RUNNER),('NBF_SHA256',p.NBFS[role]),
            ('BITSTREAM_SHA256',self.a['artifacts']['bit']['sha256'])]:
            p.require([s for s in lines if s.startswith(key+'=')]==[key+'='+value],'bound started helper '+key)
        logs=[s[4:] for s in lines if s.startswith('LOG=')]
        pattern=r'/home/xilinx/bp-logs/retained-capacity768-'+role+r'-interactive-[0-9]{8}T[0-9]{6}Z-([1-9][0-9]*)\.log'
        p.require(len(logs)==1 and re.fullmatch(pattern,logs[0]),'exact own helper/NBF/PID log')
        return dict(token=self.token,role=role,pid=int(re.fullmatch(pattern,logs[0])[1]),log=logs[0],
            bit_sha256=self.a['artifacts']['bit']['sha256'],preflight=self.own_guest['preflight'])

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
            src=p.SOURCE_PATHS[relative];target=output/'host-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
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
