#!/usr/bin/env python3
"""Default-offline fixed physical capacity diagnostic; no performance inference."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import tempfile
import time

import pexpect

import retained_capacity_diagnostic as p
import retained_capacity_install as install
import run_retained29_session as maintained
from run_retained29_application_session import journal,now

REMOTE=p.stage.REMOTE_ZYNQ


def verify_sources(a):p.require(p.source_hashes()==a['sources'],'diagnostic runtime source drift')


def verify_files(a):
    for key in ('runner','rollback_runner','compile_gate','elf','build_gate','model_preparation'):
        p.verify_binding(a[key])
    for group in ('programs','model_audits','artifacts','rollback_overlay'):
        for record in a[group].values():p.verify_binding(record)
    p.verify_binding(a['candidate_bridge'])
    bridge=json.loads(Path(a['candidate_bridge']['path']).read_text())
    for record in bridge['evidence'].values():p.verify_binding(record)


class Operations(maintained.Operations):
    """Reuse maintained child handling/scripts; never call an old guest role."""
    def __init__(self,a,output,env):
        super().__init__(a,output,env)
        self.a=a;self.token=hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()[:16]
        self.phase='initial';self.steps=0;self.original=None;self.original_overlay=False
        self.mutated=False;self.staged=False;self.installed=False;self.guest_started=False

    def record(self,**values):
        path=self.output/'publication.json'
        values.update(token=self.token,original=self.original,original_overlay=self.original_overlay,
            mutation_started=self.mutated,stage_complete=self.staged,installed=self.installed,guest_started=self.guest_started)
        journal(path,values)

    def step(self,name,argv,timeout=600):
        self.steps+=1
        return super().step('%04d-%s-%s'%(self.steps,self.phase,name),argv,timeout)

    def rpc(self,action):
        return json.loads(self.step('runner-'+action,install.command(self.a['host'],action,self.token,
            None if action=='inspect' else self.original),60))

    def inspect(self,expected=None):
        value=self.rpc('inspect')
        if expected is not None:p.require(value['before']['sha256']==expected,'actual installed runner mismatch')
        return value

    def inventory(self):
        a=self.a;stem=self.bundle['stem']
        paths=dict(package=p.stage.REMOTE_BASE+'/'+Path(a['artifacts']['package']['path']).name,
            **{side+'.'+suffix:REMOTE+'/'+name+'.'+suffix for side,name in (('actual',stem),('load','blackparrot_bd_1'))
                for suffix in ('bit','hwh','map')},
            **{'nbf.'+role:REMOTE+'/'+Path(a['programs'][role]['path']).name for role in p.ROLES})
        text=self.step('inventory',['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',a['host'],
            'python3 -c '+shlex.quote(p.stage.REMOTE_AUDIT)+' '+shlex.quote(json.dumps(paths,sort_keys=True))],180)
        result=json.loads(text);p.require(set(result['files'])==set(paths),'complete route/NBF inventory')
        for key,path in paths.items():
            row=result['files'][key];p.require(row['path']==path and str(row['device']) in result['filesystems'],'inventory path/filesystem')
        return result

    def matched(self,inventory):
        expected=dict(package=self.a['artifacts']['package'],
            **{side+'.'+suffix:self.bundle['members'][suffix] for side in ('actual','load') for suffix in ('bit','hwh','map')},
            **{'nbf.'+role:self.a['programs'][role] for role in p.ROLES})
        return all(not inventory['files'][name]['missing']
            and all(inventory['files'][name][key]==record[key] for key in ('bytes','sha256')) for name,record in expected.items())

    def stage(self):
        self.phase='stage';identity=self.inspect(p.OLD);self.original=identity['original'];self.record(state='accepted runner metadata captured')
        self.bundle=p.stage.local_bundle(dict(artifacts=dict(package=self.a['artifacts']['package'],bit=self.a['artifacts']['bit'])))
        text=self.step('loader-dryrun',['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',self.a['host'],
            'cd '+REMOTE+' && make -n load_bitstream BOARDNAME=pynqz2 VIVADO_VERSION=2024.2 VIVADO_MODE=batch'],30)
        p.require(re.findall(r'Overlay\("([A-Za-z0-9_-]+)\.bit"\)',text)==['blackparrot_bd_1'],'actual maintained privileged loader stem')
        before=self.inventory()
        for suffix,record in self.a['rollback_overlay'].items():
            actual=before['files']['load.'+suffix]
            p.require(not actual['missing'] and all(actual[k]==record[k] for k in ('bytes','sha256')),'actual reviewed prior overlay triplet')
        self.original_overlay=True
        reuse=self.matched(before)
        # Reserve all new images, extracted aliases and rollback temporaries
        # before any write. Conservative rather than reclaiming unknown files.
        bundle_bytes=sum(v['bytes'] for v in self.bundle['members'].values())
        payload=(0 if reuse else self.a['artifacts']['package']['bytes']
            +bundle_bytes*(1 if self.bundle['stem']=='blackparrot_bd_1' else 2)
            +sum(v['bytes'] for v in self.a['programs'].values())
            +sum(v['bytes'] for v in self.a['rollback_overlay'].values()))
        payload+=self.a['runner']['bytes']+self.a['rollback_runner']['bytes']
        budget=[]
        for fs in before['filesystems'].values():
            unit=fs['allocation_unit'];required=math.ceil(payload/unit)*unit+16*1024*1024
            p.require(fs['available_bytes']>=required and fs['available_inodes']>=32,'full stage/runner/rollback/log peak reserve')
            budget.append(dict(device=fs['device'],required_bytes=required,available_bytes=fs['available_bytes'],required_inodes=32))
        self.record(state='stage budget accepted',inventory=before,budget=budget,reuse=reuse)
        if reuse:self.step('sync-reused-stage',['ssh','-o','BatchMode=yes',self.a['host'],'sync'],60)
        else:
            self.mutated=True;self.record(state='stage mutation begins')
            text=self.step('maintained-stage',[str(self.scripts/'stage_pynq_artifacts.sh'),self.a['artifacts']['package']['path'],
                self.a['host'],*[self.a['programs'][role]['path'] for role in p.ROLES]])
            p.require('STAGE_OK=1' in text and 'STAGE_DURABLE_SYNC_OK=1' in text,'maintained durable full stage')
        p.require(self.matched(self.inventory()),'complete staged triplet/package/three-NBF readback')
        self.staged=True;self.record(state='durable exact stage complete')

    def power(self,label,expected):
        self.phase=label
        for name in ('power_cycle_pynq','wait_pynq_ready','load_pynq_overlay'):
            text=self.step(name,[str(self.scripts/(name+'.sh')),self.a['host']])
        p.require('LOADING_BIT_SHA256='+expected in text and 'REMOTE_FPGA_STATE_OK=1' in text
            and 'REMOTE_OVERLAY_LOAD_OK=1' in text,'actual power/readiness/overlay/operating recovery')

    def install_runner(self):
        self.phase='install';self.inspect(p.OLD);self.mutated=True;self.record(state='private runner staging begins')
        for key,kind in (('runner','new'),('rollback_runner','old')):
            p.verify_binding(self.a[key]);self.step('upload-'+kind,['scp','-o','BatchMode=yes','--',self.a[key]['path'],
                self.a['host']+':'+install.temporary(self.token,kind)],60)
        result=self.rpc('install');p.require(result['after']['sha256']==p.RUNNER and result['durable'] is True,'atomic durable private runner install')
        self.installed=True;self.record(state='private runner atomically installed',install=result)

    def restore_runner(self):
        self.phase='restore-runner';current=self.inspect()
        p.require(current['original']==self.original,'original mode/owner preserved')
        if current['before']['sha256']!=p.OLD:
            p.verify_binding(self.a['rollback_runner'])
            self.step('upload-reviewed2dd',['scp','-o','BatchMode=yes','--',self.a['rollback_runner']['path'],
                self.a['host']+':'+install.temporary(self.token,'old')],60)
        result=self.rpc('restore');p.require(result['after']['sha256']==p.OLD and result['durable'] is True,'verified durable2dd rollback')
        self.installed=False;self.record(state='accepted2dd atomically restored',rollback=result)

    def restore_overlay(self):
        self.phase='restore-overlay';request={}
        for suffix,record in self.a['rollback_overlay'].items():
            p.verify_binding(record);path=REMOTE+'/.bp-capacity-'+self.token+'-rollback.'+suffix
            self.step('upload-'+suffix,['scp','-o','BatchMode=yes','--',record['path'],self.a['host']+':'+path],60)
            request[suffix]=dict(path=path,sha256=record['sha256'])
        code=r'''
import hashlib,json,os,pathlib,sys
r=json.loads(sys.argv[1]);assert set(r)=={'bit','hwh','map'}
root=pathlib.Path('/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq')
for suffix,b in r.items():
 p=pathlib.Path(b['path']);assert p.parent==root and p.name.startswith('.bp-capacity-') and p.name.endswith('-rollback.'+suffix)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==b['sha256']
for suffix,b in r.items():os.replace(b['path'],str(root/('blackparrot_bd_1.'+suffix)))
fd=os.open(str(root),os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(fd)
finally:os.close(fd)
os.sync()
for suffix,b in r.items():assert hashlib.sha256((root/('blackparrot_bd_1.'+suffix)).read_bytes()).hexdigest()==b['sha256']
print('REVIEWED_PRIOR_OVERLAY_RESTORED=1')
'''
        text=self.step('publish-original-overlay',['ssh','-o','BatchMode=yes',self.a['host'],
            'python3 -c '+shlex.quote(code)+' '+shlex.quote(json.dumps(request))],60)
        p.require('REVIEWED_PRIOR_OVERLAY_RESTORED=1' in text,'original triplet restore readback')

    def requires_recovery(self):return self.mutated or self.staged

    def recover(self,label):
        if label!='final':
            self.power(label,self.a['artifacts']['bit']['sha256'])
            self.inspect(p.RUNNER if self.installed else p.OLD)
            p.require(self.matched(self.inventory()),'post-power complete stage identity')
            return
        expected=self.a['artifacts']['bit']['sha256'] if self.staged else self.a['rollback_overlay']['bit']['sha256']
        try:self.inspect()
        except BaseException:
            # Only our already-started guest authorizes this extra quiescing
            # recovery. Unknown preexisting programs are never killed here.
            if not self.guest_started:raise
            self.power('quiesce-owned-guest-before-rollback',expected);self.inspect()
        self.restore_runner()
        if not self.staged and self.mutated:self.restore_overlay()
        self.power('final',expected);self.inspect(p.OLD)
        final=self.inventory()
        if self.staged:p.require(self.matched(final),'final recovered complete requested overlay/NBF readback')
        else:
            for suffix,record in self.a['rollback_overlay'].items():
                actual=final['files']['load.'+suffix]
                p.require(not actual['missing'] and all(actual[k]==record[k] for k in ('bytes','sha256')),'final reviewed prior overlay collateral')
        self.record(state='accepted2dd and verified overlay/operating recovered before unlock')

    def guest(self):
        self.install_runner();results=[]
        for index,role in enumerate(p.ROLES):
            if index:self.recover('between-'+role)
            self.phase='case-'+role;self.inspect(p.RUNNER);verify_sources(self.a);verify_files(self.a)
            self.guest_started=True;self.record(state='fixture begins',role=role)
            result=run_case(self.a,role,self.output/(role+'.log'),self.env,self.scripts/'run_pynq_interactive.sh')
            results.append(result);self.record(state='fixture completed',role=role,complete_cases=[r['role'] for r in results])
        return results


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


def request_recovery(output):
    state=json.loads((output/'session.json').read_text())
    p.require(state['schema']==p.SCHEMA and state['state']=='recovery-required-reservation-held','live held diagnostic recovery required')
    intent=dict(schema='bp-capacity-recovery-request-v1',action='recover-only',token=state['recovery_token'],attempt=state['recovery_attempts']+1)
    with tempfile.NamedTemporaryFile(mode='w',dir=output,prefix='.recover-',delete=False) as stream:
        temp=Path(stream.name);json.dump(intent,stream);stream.flush();os.fsync(stream.fileno())
    try:os.link(temp,output/'recovery-request.json')
    finally:temp.unlink()
    descriptor=os.open(str(output),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def execute(a,output,operations=Operations,recovery_wait=time.sleep):
    p.validate(a);p.require(not output.exists(),'new diagnostic output required')
    # This holding loop follows the approved application supervisor. Only
    # admission/metadata/operations differ; original clients remain unchanged.
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
                    state['recovery_attempts']+=1;state['state']='recovery-in-progress-reservation-held';save()
                    try:ops.recover('final')
                    except BaseException as error:
                        if failure is None:failure=error
                        state.update(state='recovery-required-reservation-held',recovery='unconfirmed',recovery_error=repr(error))
                        state['recovery_history'].append(dict(attempt=state['recovery_attempts'],error=repr(error),utc=now()));save()
                        request=output/'recovery-request.json'
                        while True:
                            if not request.exists():recovery_wait(10);continue
                            try:
                                intent=json.loads(request.read_text())
                                p.require(set(intent)=={'schema','action','token','attempt'} and intent['schema']=='bp-capacity-recovery-request-v1'
                                    and intent['action']=='recover-only' and intent['token']==state['recovery_token']
                                    and type(intent['attempt']) is int and intent['attempt']==state['recovery_attempts']+1,'invalid fixed recovery request')
                            except (ValueError,TypeError,KeyError) as error:
                                count=len(state.setdefault('rejected_recovery_requests',[]))+1
                                kept=output/('recovery-request-rejected-%04d.json'%count);request.replace(kept)
                                state['rejected_recovery_requests'].append(dict(request=p.binding(kept),error=repr(error)));save();continue
                            request.replace(output/('recovery-request-attempt-%04d.json'%intent['attempt']));break
                        continue
                    state['recovery']='accepted2dd restored and overlay/operating/helper verified before unlock'
                    state['recovery_history'].append(dict(attempt=state['recovery_attempts'],state='verified',utc=now()));break
            else:state['recovery']='no mutation or target began'
            try:verify_sources(a)
            except BaseException as error:
                if failure is None:failure=error
                state.update(state='FAIL',error=repr(error))
            state['state']='PASS-complete-rolled-back-capacity-diagnostic' if failure is None else 'FAIL'
            state['reservation_release_utc']=now()
            if state['recovery'].startswith('accepted2dd restored'):state['release_after_recovery_utc']=state['reservation_release_utc']
            try:save()
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
