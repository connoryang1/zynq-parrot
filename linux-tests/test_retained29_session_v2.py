"""Offline v2 client refusal/provenance/recovery tests; physical steps mocked."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import retained29_protocol as p
import retained29_stage_v2 as stage
import run_retained29_session_v2 as client
from test_retained29_stage_v2 import fixture


class V2Client(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def operation(self,inventory=None,rollback=None):
        a,b,i=fixture();op=object.__new__(client.Operations)
        op.admission=a;op.outer=dict(package_bundle=b,load_stem='blackparrot_bd_1',rollback=rollback,prior_durable_stage=None)
        op.output=self.root;op.scripts=Path('/immutable/scripts');op.receipt={}
        op.stage_complete=False;op.mutation_started=False;op.original=None
        op.current=Mock();op.save=Mock();op.audit=Mock(return_value=inventory or i)
        op.step=Mock(return_value='Overlay("blackparrot_bd_1.bit")\n')
        return op,i

    def test_exact_cache_hit_sync_then_full_recheck_no_upload(self):
        op,i=self.operation();i['filesystems']['1'].update(available_bytes=0,available_inodes=0)
        order=[]
        def step_call(label,*args):
            order.append(label);return 'Overlay("blackparrot_bd_1.bit")\n'
        def audit(label):order.append(label);return i
        op.step.side_effect=step_call;op.audit.side_effect=audit;op.stage()
        self.assertTrue(op.stage_complete);self.assertFalse(op.mutation_started)
        self.assertEqual(order,['stage-v2-loader-dryrun','stage-v2-inventory-before','stage-v2-reuse-sync','stage-v2-inventory-after-sync'])
        self.assertEqual(op.step.call_count,2);self.assertEqual(op.step.call_args[0][1][-1],'sync')
        self.assertEqual(op.receipt['uploaded_files'],[]);self.assertEqual(op.receipt['stage_helper_invocations'],0)
        self.assertEqual(op.receipt['decision']['stage_allocated_bytes'],0)

    def test_sync_failure_or_postsync_change_never_marks_stage_complete(self):
        op,i=self.operation();op.step.side_effect=['Overlay("blackparrot_bd_1.bit")',RuntimeError('sync failed')]
        with self.assertRaisesRegex(RuntimeError,'sync failed'):op.stage()
        self.assertFalse(op.stage_complete)
        op,i=self.operation();changed=copy.deepcopy(i);changed['files']['load.hwh']['sha256']='0'*64
        op.audit.side_effect=[i,changed]
        with self.assertRaises(ValueError):op.stage()
        self.assertFalse(op.stage_complete)

    def test_postpower_complete_hash_gate_after_runner_identity(self):
        op,i=self.operation();order=[]
        def audit(label):order.append(label);return i
        op.audit.side_effect=audit
        with patch.object(client.v1.Operations,'remote_identity',side_effect=lambda:order.append('runner-helper')):
            op.remote_identity()
        self.assertEqual(order,['runner-helper','stage-v2-inventory-after-power'])
        i['files']['nbf']['sha256']='0'*64
        with patch.object(client.v1.Operations,'remote_identity'),self.assertRaises(ValueError):op.remote_identity()

    def test_inexact_no_rollback_never_invokes_stage_or_guest(self):
        for key in fixture()[2]['files']:
            op,i=self.operation();i['files'][key]['sha256']='0'*64
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'rollback'):op.stage()
            self.assertEqual(op.step.call_count,1);self.assertFalse(op.mutation_started)
            with self.assertRaisesRegex(ValueError,'original recovery bundle unavailable'):op.recover('final')
            self.assertEqual(op.step.call_count,1)

    def test_actual_make_loader_mismatch_stops_before_inventory(self):
        op,_=self.operation();op.step.return_value='Overlay("wrong.bit")'
        with self.assertRaises(ValueError):op.stage()
        op.audit.assert_not_called()

    def rollback(self):
        result={}
        for suffix in stage.SUFFIXES:
            path=self.root/('old.'+suffix);path.write_text('original '+suffix);result[suffix]=p.binding(path)
        return result

    def test_partial_nbf_reuse_helper_argv_and_complete_readback(self):
        rollback=self.rollback();op,before=self.operation(rollback=rollback)
        for suffix,record in rollback.items():before['files']['load.'+suffix].update(bytes=record['bytes'],sha256=record['sha256'])
        after=fixture()[2];op.audit.side_effect=[before,after]
        op.step.side_effect=['Overlay("blackparrot_bd_1.bit")','STAGE_OK=1\nSTAGE_DURABLE_SYNC_OK=1\n']
        with patch.object(client.v1,'verify_artifacts'):op.stage()
        argv=op.step.call_args[0][1]
        self.assertEqual(argv,[str(op.scripts/'stage_pynq_artifacts.sh'),op.admission['artifacts']['package']['path'],op.admission['host']])
        self.assertEqual(op.receipt['uploaded_files'],['package']);self.assertTrue(op.stage_complete)

    def test_budget_refusal_has_no_mutating_step(self):
        rollback=self.rollback();op,before=self.operation(rollback=rollback)
        for suffix,record in rollback.items():before['files']['load.'+suffix].update(bytes=record['bytes'],sha256=record['sha256'])
        before['filesystems']['1']['available_bytes']=0
        with self.assertRaisesRegex(ValueError,'insufficient'):op.stage()
        self.assertFalse(op.mutation_started);self.assertEqual(op.step.call_count,1)

    def test_original_recovery_distinct_from_requested_and_after_mutation_restore(self):
        rollback=self.rollback();op,_=self.operation(rollback=rollback);op.original=rollback;op.mutation_started=True
        order=[];op.restore_original=Mock(side_effect=lambda:order.append('restore'))
        def step_call(label,*args):
            order.append(label)
            return 'LOADING_BIT_SHA256='+rollback['bit']['sha256']+'\nREMOTE_FPGA_STATE_OK=1\nREMOTE_OVERLAY_LOAD_OK=1\n'
        op.step.side_effect=step_call;op.recover('final')
        self.assertEqual(order[0],'restore');self.assertEqual(len(order),4)
        self.assertEqual(op.receipt['final_recovery']['bit_sha256'],rollback['bit']['sha256'])

    def test_restore_checks_three_temps_before_publish_and_final_bundle(self):
        for wrong in (False,True):
            rollback=self.rollback();op,_=self.operation(rollback=rollback);op.original=rollback
            op.admission['stage_v2_admission']={'sha256':'f'*64};labels=[]
            def step_call(label,argv,*args):
                labels.append(label)
                if label=='restore-temp-readback':
                    rows={suffix:dict(missing=False,bytes=rec['bytes'],sha256=rec['sha256']) for suffix,rec in rollback.items()}
                    if wrong:rows['hwh']['sha256']='0'*64
                    return json.dumps(dict(files=rows))
                return ''
            op.step.side_effect=step_call
            after=fixture()[2]
            for suffix,rec in rollback.items():after['files']['load.'+suffix].update(bytes=rec['bytes'],sha256=rec['sha256'])
            op.audit.return_value=after
            if wrong:
                with self.assertRaisesRegex(ValueError,'temporary mismatch'):op.restore_original()
                self.assertNotIn('restore-publish',labels);op.audit.assert_not_called()
            else:
                op.restore_original()
                self.assertEqual(labels,['restore-upload-bit','restore-upload-hwh','restore-upload-map','restore-temp-readback','restore-publish'])
                self.assertEqual(op.receipt['restored_original'],rollback)

    def test_new_source_drift_fails_only_after_safe_recovery(self):
        op,_=self.operation();op.stage_complete=True;events=[]
        def endcheck():
            events.append('endcheck');raise ValueError('drift')
        op.current.side_effect=endcheck
        def step_call(label,*args):
            events.append(label)
            return 'LOADING_BIT_SHA256='+op.admission['artifacts']['bit']['sha256']+'\nREMOTE_FPGA_STATE_OK=1\nREMOTE_OVERLAY_LOAD_OK=1\n'
        op.step.side_effect=step_call
        with self.assertRaisesRegex(ValueError,'drift'):op.recover('final')
        self.assertEqual(events[-1],'endcheck');self.assertEqual(len(events),4)
        self.assertEqual(op.receipt['final_recovery']['state'],'complete before common unlock')
        self.assertIn('recovery completed',op.receipt['source_endcheck'])

    def test_outer_binds_extra_sources_bundle_and_base(self):
        base=fixture()[0];path=self.root/'base.json';path.write_text(json.dumps(base))
        outer=dict(schema=client.SCHEMA,state='bound-functional-only',base_admission=p.binding(path),
                   sources=client.new_sources(),package_bundle=fixture()[1],load_stem='blackparrot_bd_1',rollback=None,prior_durable_stage=None)
        target=self.root/'outer.json';target.write_text(json.dumps(outer))
        with patch.object(p,'validate_admission'),patch.object(stage,'local_bundle',return_value=fixture()[1]):
            _,validated=client.validate_outer(target)
            self.assertEqual(validated['stage_v2_admission'],p.binding(target))
            for key,value in [('schema','old'),('sources',{}),('package_bundle',{}),('load_stem','other')]:
                bad=copy.deepcopy(outer);bad[key]=value;target.write_text(json.dumps(bad))
                with self.subTest(key=key),self.assertRaises(ValueError):client.validate_outer(target)
            target.write_text(json.dumps(outer));path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'artifact changed'):client.validate_outer(target)

    def test_default_offline_no_execute_and_explicit_uses_exact_v1_lifecycle(self):
        base={'fixture':'base'}
        with patch.object(client,'validate_outer',return_value=({},base)),patch.object(client.v1,'execute') as execute:
            client.main([str(self.root/'outer.json')]);execute.assert_not_called()
            client.main([str(self.root/'outer.json'),'--execute',str(self.root/'new')])
            execute.assert_called_once_with(base,self.root/'new',operations=client.Operations)


if __name__=='__main__':unittest.main()
