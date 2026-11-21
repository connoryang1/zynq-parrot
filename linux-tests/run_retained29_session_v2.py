#!/usr/bin/env python3
"""ABI29 v2 staging with the unchanged v1 single-boot lock and lifecycle."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex

import retained29_protocol as p
import retained29_stage_v2 as stage
import run_retained29_session as v1

SCHEMA='bp-retained29-functional-session-v2'
NEW_SOURCES=('linux-tests/retained29_stage_v2.py','linux-tests/run_retained29_session_v2.py')


def new_sources():return {name:p.binding(p.ROOT/name)['sha256'] for name in NEW_SOURCES}


def validate_outer(path):
    path=Path(path).resolve();outer=json.loads(path.read_text())
    p.require(set(outer)=={'schema','state','base_admission','sources','package_bundle','load_stem','rollback','prior_durable_stage'},'v2 admission fields')
    p.require(outer['schema']==SCHEMA and outer['state']=='bound-functional-only','v2 admission version/state')
    p.verify_binding(outer['base_admission'])
    base=json.loads(Path(outer['base_admission']['path']).read_text());p.validate_admission(base)
    p.require(outer['sources']==new_sources(),'v2 source identity changed')
    p.require(outer['package_bundle']==stage.local_bundle(base),'v2 complete local package member binding')
    p.require(outer['load_stem']=='blackparrot_bd_1','fixed privileged loader target')
    if outer['prior_durable_stage'] is not None:stage.verify_prior_durable_stage(base,outer['prior_durable_stage'])
    if outer['rollback'] is not None:
        p.require(set(outer['rollback'])==set(stage.SUFFIXES),'v2 original rollback triplet')
        for artifact in outer['rollback'].values():p.verify_binding(artifact)
    # The unchanged v1 validator accepts this additional truthful provenance.
    # It is preserved in session.json; the outer file pins ALL extra sources.
    base['stage_v2_admission']=p.binding(path)
    return outer,base


class Operations(v1.Operations):
    def __init__(self,admission,output,env):
        super().__init__(admission,output,env)
        p.verify_binding(admission['stage_v2_admission'])
        outer,base=validate_outer(admission['stage_v2_admission']['path'])
        p.require(base==admission,'inherited admission/v2 mismatch')
        p.require(env.get('PYNQ_REMOTE_EXAMPLE_DIR',stage.REMOTE_BASE) in (stage.REMOTE_BASE,'~/zynq-parrot/cosim/black-parrot-example'),
                  'unexpected remote stage directory override')
        self.outer=outer;self.stage_complete=False;self.mutation_started=False;self.original=None
        self.receipt=dict(schema=SCHEMA,admission=admission['stage_v2_admission'],sources=outer['sources'],
                          package_bundle=outer['package_bundle'],state='reserved; not inventoried')
        for relative,expected in outer['sources'].items():
            target=output/'v2-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((p.ROOT/relative).read_bytes())
            p.require(p.binding(target)['sha256']==expected,'v2 source snapshot race')
        self.save()

    def save(self):
        (self.output/'stage-v2-receipt.json').write_text(json.dumps(self.receipt,indent=2)+'\n')

    def current(self):p.require(new_sources()==self.outer['sources'],'v2 original source drift')

    def step(self,*args,**kwargs):
        # Safe recovery uses captured code/scripts, independent of later changes
        # to original source files. Original drift is checked after recovery.
        for relative,expected in self.outer['sources'].items():
            p.require(p.binding(self.output/'v2-sources'/relative)['sha256']==expected,'v2 source snapshot drift')
        return super().step(*args,**kwargs)

    def audit(self,label):
        command=stage.inventory_command(self.admission,self.outer['package_bundle'],self.outer['load_stem'])
        return json.loads(self.step(label,command,180))

    def stage(self):
        self.current()
        text=self.step('stage-v2-loader-dryrun',['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',self.admission['host'],
            'cd '+stage.REMOTE_ZYNQ+' && make -n load_bitstream BOARDNAME=pynqz2 VIVADO_VERSION=2024.2 VIVADO_MODE=batch'],30)
        stems=re.findall(r'Overlay\("([A-Za-z0-9_-]+)\.bit"\)',text)
        p.require(stems==[self.outer['load_stem']],'actual make/privileged-loader stem mismatch')
        before=self.audit('stage-v2-inventory-before')
        self.receipt['inventory_before']=before;self.save()
        # Establish rollback ownership before any budget refusal or mutation.
        rollback=self.outer['rollback']
        if rollback is not None:
            for suffix,artifact in rollback.items():
                row=before['files']['load.'+suffix];p.verify_binding(artifact)
                p.require(not row['missing'] and all(row[k]==artifact[k] for k in ('bytes','sha256')),'original rollback inventory mismatch')
            self.original=rollback
        decision=stage.plan(self.admission,self.outer['package_bundle'],self.outer['load_stem'],before,rollback)
        self.receipt['decision']=decision;self.save()
        if not decision['stage_required']:
            if self.outer['prior_durable_stage'] is not None:
                stage.verify_prior_durable_stage(self.admission,self.outer['prior_durable_stage'])
                self.receipt['prior_durable_stage']=self.outer['prior_durable_stage']
            # Exact cache bytes may have been rewritten by a preceding owner.
            # Flush them before power removal; do not infer durability from SHA.
            self.step('stage-v2-reuse-sync',['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',self.admission['host'],'sync'],60)
            after=self.audit('stage-v2-inventory-after-sync')
            verified=stage.plan(self.admission,self.outer['package_bundle'],self.outer['load_stem'],after)
            p.require(verified['action']=='reuse-complete','cache changed across durability sync')
            self.receipt.update(durability='explicit sync plus full identity recheck before power',inventory_after_sync=after)
        if decision['stage_required']:
            self.current();v1.verify_artifacts(self.admission)
            self.mutation_started=True;self.receipt['state']='mutation started after preflight';self.save()
            text=self.step('stage',stage.helper_argv(self.admission,decision,self.scripts))
            p.require('STAGE_OK=1' in text and 'STAGE_DURABLE_SYNC_OK=1' in text,'durable reused-NBF stage missing')
            after=self.audit('stage-v2-inventory-after')
            verified=stage.plan(self.admission,self.outer['package_bundle'],self.outer['load_stem'],after)
            p.require(verified['action']=='reuse-complete','poststage complete bundle/NBF mismatch')
            self.receipt['inventory_after']=after
        self.stage_complete=True
        self.receipt.update(state='PASS verified reuse plus durability sync; zero uploads/new staging files' if not decision['stage_required'] else 'PASS durable stage and exact readback',
                            stage_helper_invocations=int(decision['stage_required']),
                            uploaded_files=(['package']+(['nbf'] if decision['stage_nbf'] else [])) if decision['stage_required'] else [])
        self.save()

    def restore_original(self):
        p.require(self.original is not None,'no verified original bundle to restore')
        token=self.admission['stage_v2_admission']['sha256'][:12]+'-'+str(os.getpid())
        temporary={suffix:'.bp-retained29-v2-restore-'+token+'.'+suffix for suffix in stage.SUFFIXES}
        for suffix in stage.SUFFIXES:
            artifact=self.original[suffix];p.verify_binding(artifact)
            self.step('restore-upload-'+suffix,['scp','-o','BatchMode=yes','--',artifact['path'],
                      self.admission['host']+':'+stage.REMOTE_ZYNQ+'/'+temporary[suffix]])
        request={suffix:stage.REMOTE_ZYNQ+'/'+temporary[suffix] for suffix in stage.SUFFIXES}
        command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',self.admission['host'],
                 'python3 -c '+shlex.quote(stage.REMOTE_AUDIT)+' '+shlex.quote(json.dumps(request))]
        copied=json.loads(self.step('restore-temp-readback',command,60))
        for suffix,artifact in self.original.items():
            p.require(not copied['files'][suffix]['missing'] and all(copied['files'][suffix][k]==artifact[k] for k in ('bytes','sha256')),'original restore temporary mismatch')
        commands=['cd '+stage.REMOTE_ZYNQ]+['mv -f '+temporary[s]+' '+self.outer['load_stem']+'.'+s for s in stage.SUFFIXES]+['sync']
        self.step('restore-publish',['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',self.admission['host'],' && '.join(commands)],60)
        actual=self.audit('restore-final-readback')
        for suffix,artifact in self.original.items():
            p.require(not actual['files']['load.'+suffix]['missing'] and all(actual['files']['load.'+suffix][k]==artifact[k] for k in ('bytes','sha256')),'original restore final mismatch')
        self.receipt['restored_original']=self.original;self.save()

    def recover(self,label):
        if not self.stage_complete:
            if self.original is None:
                # No stage mutation/guest was allowed. Do not blindly load an
                # unbound original or the unstaged requested overlay.
                self.receipt.update(state='FAIL preflight; no stage mutation/guest',recovery='unbound original; no board mutation attempted')
                self.save();raise ValueError('no stage mutation/guest; original recovery bundle unavailable')
            if self.mutation_started:self.restore_original()
            expected=self.original['bit']['sha256']
        else:expected=self.admission['artifacts']['bit']['sha256']
        for name in ('power_cycle_pynq','wait_pynq_ready','load_pynq_overlay'):
            text=self.step(label+'-'+name,[str(self.scripts/(name+'.sh')),self.admission['host']])
        p.require('LOADING_BIT_SHA256='+expected in text and 'REMOTE_FPGA_STATE_OK=1' in text and 'REMOTE_OVERLAY_LOAD_OK=1' in text,
                  'actual v2 recovery overlay/state mismatch')
        self.receipt[label+'_recovery']=dict(state='complete before common unlock',bit_sha256=expected)
        self.save()
        if label=='final':
            try:self.current()
            except ValueError:
                self.receipt['source_endcheck']='FAIL original changed; recovery completed using immutable copies';self.save();raise
            self.receipt['source_endcheck']='PASS';self.save()

    def guest(self):
        self.current()
        return super().guest()

    def remote_identity(self):
        super().remote_identity()
        after=self.audit('stage-v2-inventory-after-power')
        decision=stage.plan(self.admission,self.outer['package_bundle'],self.outer['load_stem'],after)
        p.require(decision['action']=='reuse-complete','post-power NBF/package/bundle identity changed')
        self.receipt['inventory_after_power']=after;self.save()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('admission',type=Path)
    parser.add_argument('--execute',type=Path,metavar='NEW_OUTPUT')
    args=parser.parse_args(argv);outer,base=validate_outer(args.admission)
    if args.execute is None:print('RETAINED29_V2_OFFLINE_ADMISSION_OK=1')
    else:v1.execute(base,args.execute,operations=Operations)
    return 0


if __name__=='__main__':raise SystemExit(main())
