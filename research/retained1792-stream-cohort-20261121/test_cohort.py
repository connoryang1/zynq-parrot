#!/usr/bin/env python3
"""Offline admission/anchor/budget tests; model and reader launch paths are mocked."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import contract as c
import run_stream1792 as run
import audit_stream1792 as audit


class ContractTests(unittest.TestCase):
    def draft(self):
        path=c.HERE/'preparation.DRAFT.json'
        return path,c.bind(path)['sha256']

    def test_software_schema_draft_validates_but_cannot_execute(self):
        path,sha=self.draft();p,program=c.load(path,sha,approved=False)
        self.assertEqual(program['max_lines'],1792)
        self.assertEqual(p['geometry']['l2_bytes'],16384)
        with self.assertRaisesRegex(ValueError,'DRAFT UNLAUNCHABLE'):c.load(path,sha)

    def test_external_admission_anchor_precedes_self_declared_paths(self):
        path,sha=self.draft();p=json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/'redirected.json'
            p['program']['path']='/untrusted/no/such/input'
            c.archive.write_json(bad,p)
            with self.assertRaisesRegex(ValueError,'external admission anchor mismatch'):c.load(bad,sha)

    def test_exact_runtime_set_cannot_be_replaced_by_self_consistent_list(self):
        path,_=self.draft();p=json.loads(path.read_text());p['runtime_sources']=[]
        with tempfile.TemporaryDirectory() as td:
            bad=Path(td)/'changed.json';c.archive.write_json(bad,p)
            with self.assertRaisesRegex(ValueError,'exact source set'):c.load(bad,c.bind(bad)['sha256'],approved=False)

    def test_pending_draft_byte_review_allows_relocation_but_not_execution(self):
        path,_=self.draft();p=json.loads(path.read_text())
        for row in p['runtime_sources'][:4]:row['path']='/review-copy/'+Path(row['path']).name
        with tempfile.TemporaryDirectory() as td:
            moved=Path(td)/'moved.json';c.archive.write_json(moved,p)
            c.load(moved,c.bind(moved)['sha256'],approved=False)
            with self.assertRaisesRegex(ValueError,'DRAFT UNLAUNCHABLE'):c.load(moved,c.bind(moved)['sha256'])

    def test_native_and_audit_drafts_never_call_model_or_reader(self):
        path,sha=self.draft()
        for module,extra in ((run,[]),(audit,['--native-sha256','0'*64])):
            argv=['test','--preparation',str(path),'--preparation-sha256',sha,'--role','d-enabled','--execute']+extra
            with mock.patch.object(sys,'argv',argv), mock.patch.object(c.native,'owned_run',side_effect=AssertionError('no execution')), mock.patch.object(c.original,'guarded_reader',side_effect=AssertionError('no reader')):
                with self.assertRaisesRegex(ValueError,'DRAFT UNLAUNCHABLE'):module.main()

    def test_default_no_execution_even_before_admission(self):
        path,sha=self.draft()
        for module,extra in ((run,[]),(audit,['--native-sha256','0'*64])):
            argv=['test','--preparation',str(path),'--preparation-sha256',sha,'--role','d-enabled']+extra
            with mock.patch.object(sys,'argv',argv):
                with self.assertRaisesRegex(ValueError,'default offline'):module.main()

    def test_exact_three_role_counters_and_existing_bounded_code(self):
        self.assertEqual(c.counters_for('d-enabled'),[0,1792,0,1792,0,14336])
        self.assertEqual(c.counters_for('d-off'),[0]*6)
        self.assertEqual(c.counters_for('i-enabled'),[1792,0,1792,0,14336,0])
        self.assertIs(run.owned_run,c.native.owned_run)
        self.assertEqual(len(c.original.audit.selection()),167)
        self.assertEqual(c.CAPS['stage_total'],c.CAPS['raw_total']+c.CAPS['audit_total']+c.CAPS['other_total'])

    def test_nested_projection_adapter_is_charged_to_per_case_audit(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td);nested=stage/'d-enabled-audit/counter-check-input';nested.mkdir(parents=True)
            with (nested/'large-sparse-fixture').open('wb') as f:f.truncate(c.CAPS['audit_per_case']+1)
            with self.assertRaisesRegex(ValueError,'per-case budget'):c.check_budget(stage,{})

    def test_native_host_mock_parses_closed_log_and_rejects_counter_corruption(self):
        draft,_=self.draft();p=json.loads(draft.read_text())
        program=json.loads(Path(p['program']['path']).read_text())
        log=Path('/home/coyang/fpga-artifacts/context-resume/retained1792-allslots-20261121/stopped01/d-enabled/run.log').read_bytes()
        for mode in ('good','counter-bad','late-budget'):
            corrupt=mode=='counter-bad'
            with tempfile.TemporaryDirectory() as td:
                stage=Path(td);prepared=copy.deepcopy(p);prepared['stage']=td
                prepared['model']={'path':str(stage/'model/inert-not-executed'),'bytes':0,'sha256':'0'*64}
                prepared['compiled_sources']={'path':'inert-not-opened','bytes':0,'sha256':'0'*64}
                def fake_run(command,cwd,env,path,*args):
                    self.assertEqual(command[1],'+c_args=prog.nbf 1800000')
                    path.write_bytes(log.replace(b'd_write_beats=14336',b'd_write_beats=14335') if corrupt else log)
                    (cwd/'trace.fst').write_bytes(b'inert mock FST; never read by a reader')
                    return SimpleNamespace(returncode=-6)
                argv=['test','--preparation',str(draft),'--preparation-sha256','0'*64,'--role','d-enabled','--execute']
                calls=[]
                def budget(*unused):
                    calls.append(True)
                    if mode=='late-budget' and len(calls)==3:raise ValueError('late resource breach')
                with mock.patch.object(sys,'argv',argv),mock.patch.object(c,'load',return_value=(prepared,program)),mock.patch.object(run,'owned_run',side_effect=fake_run),mock.patch.object(run,'check_budget',side_effect=budget):
                    if corrupt:
                        with self.assertRaisesRegex(ValueError,'primary retained-use counter gate'):run.main()
                        self.assertFalse((stage/'d-enabled/verification.json').exists())
                        self.assertTrue((stage/'d-enabled/FAIL.json').exists())
                    elif mode=='late-budget':
                        with self.assertRaisesRegex(ValueError,'late resource breach'):run.main()
                        self.assertFalse((stage/'d-enabled/verification.json').exists())
                        self.assertTrue((stage/'d-enabled/FAILED-verification.json').exists())
                    else:
                        run.main()
                        proof=json.loads((stage/'d-enabled/verification.json').read_text())
                        self.assertEqual(proof['counters'],c.counters_for('d-enabled'))

    def test_audit_incomplete_full_schema_input_cannot_produce_acceptance(self):
        draft,_=self.draft();p=json.loads(draft.read_text())
        program=json.loads(Path(p['program']['path']).read_text())
        selected=c.original.audit.selection();lines=['#FST\t0\t10\t-12\n']
        for h,(key,(suffix,width)) in enumerate(selected.items(),1):
            lines.append('#SIGNAL\t%s\t%d\t%d\ttop.%s\n'%(key,width,h,suffix))
        for h,(key,(suffix,width)) in enumerate(selected.items(),1):
            lines.append('0\t%d\t%s\n'%(h,'0'*width))
        # Valid schema and initial values, but no EOF; no input lines omitted by
        # the production adapter and no fresh FST reader is launched.
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td);case=stage/'d-enabled';case.mkdir();(case/'trace.fst').write_bytes(b'inert FST never read')
            prepared=copy.deepcopy(p);prepared['stage']=td
            argv=['test','--preparation',str(draft),'--preparation-sha256','0'*64,'--role','d-enabled','--native-sha256','0'*64,'--execute']
            with mock.patch.object(sys,'argv',argv),mock.patch.object(c,'load',return_value=(prepared,program)),mock.patch.object(c,'check_native',return_value={}),mock.patch.object(c,'check_budget'),mock.patch.object(c.original,'guarded_reader',return_value=(line for line in lines)):
                with self.assertRaisesRegex(ValueError,'closed complete FST'):audit.main()
            self.assertFalse((stage/'d-enabled-audit/acceptance.json').exists())

    def test_wrong_native_anchor_fails_before_self_declared_native_json(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td);case=stage/'d-enabled';case.mkdir();(case/'verification.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'external native-proof anchor'):c.check_native(stage,'d-enabled',{},Path(td)/'prep','0'*64)

    def test_wrong_audit_anchor_fails_before_self_declared_graph(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td);out=stage/'d-enabled-audit';out.mkdir();(out/'acceptance.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'external audit acceptance anchor'):c.verify_audit(stage,'d-enabled',{},Path(td)/'prep','0'*64)

    def test_redirected_archive_path_rejected_even_with_rehashed_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            stage=Path(td);out=stage/'d-enabled-audit';out.mkdir();prep=stage/'prep.json';prep.write_text('{}')
            names=('verification.json','selection.tsv','gp0-counter-projection.tsv.gz','counter-check-input/verification.json','counter-words.json','counter-checker.log','counter-checker.owned.json','reader.stderr','reader.owned.json')
            for name in names:
                path=out/name;path.parent.mkdir(exist_ok=True);path.write_text('{}')
            outside=stage/'elsewhere.json';outside.write_text('{}')
            files=[c.bind(out/name) for name in names];files[0]=c.bind(outside)
            receipt=dict(schema='retained1792-stream-acceptance-v1',role='d-enabled',preparation=c.bind(prep),sources=[],native_sha256='0'*64,files=files)
            c.archive.write_json(out/'acceptance.json',receipt)
            with mock.patch.object(c,'check_native',return_value={'counters':c.counters_for('d-enabled')}):
                with self.assertRaisesRegex(ValueError,'archive paths fixed'):c.verify_audit(stage,'d-enabled',{'runtime_sources':[]},prep,c.bind(out/'acceptance.json')['sha256'])


if __name__=='__main__':unittest.main()
