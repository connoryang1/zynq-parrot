"""Admission-policy tests only; never compile or execute the target model."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('reuse_runner', ROOT/'tools/run_resume_data_reuse.py')
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
BASE = Path(__file__).resolve().parent
GATE = BASE/'scoped-mode0-validation/validation.json'
FAILED = BASE/'one-kib/session.json'


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='resume-admission-')
        self.addCleanup(self.scratch.cleanup)
        self.tmp = Path(self.scratch.name)
        self.sources = {name:R.record(ROOT/name) for name in R.DEPENDENCIES}

    def prior(self, change):
        value = json.loads(FAILED.read_text())
        change(value)
        path = self.tmp/'prior.json'
        path.write_text(json.dumps(value))
        return path

    def scope_fixture(self, gate_change=None, build_change=None, bad_model=False):
        value = json.loads(GATE.read_text())
        directory = self.tmp/'gate'; (directory/'model').mkdir(parents=True)
        build = json.loads((GATE.parent/'model/build.json').read_text())
        if build_change: build_change(build)
        build_path = directory/'model/build.json'
        build_path.write_text(json.dumps(build))
        value['build_manifest']['sha256'] = R.sha(build_path)
        value['build_manifest']['bytes'] = build_path.stat().st_size
        model = directory/'model/Vbsg_nonsynth_zynq_testbench'
        if bad_model: model.write_bytes(b'wrong model')
        else: shutil.copyfile(GATE.parent/'model'/model.name, model)
        if gate_change: gate_change(value)
        path = directory/'validation.json'; path.write_text(json.dumps(value))
        return path, build_path

    def select_fixture(self, path, build):
        with patch.object(R,'SCOPED_VALIDATION_SHA',R.sha(path)), patch.object(R,'SCOPED_BUILD_SHA',R.sha(build)):
            return R.selected_model(path)

    def test_default_still_selects_only_immutable_binary(self):
        old, model, admission = R.selected_model()
        self.assertEqual(R.sha(model),R.MODEL_SHA)
        self.assertEqual(old['blackparrot_revision'],R.BP_REV)
        self.assertIsNone(admission)

    def test_exact_approved_durable_scoped_model(self):
        _, model, admission = R.selected_model(GATE)
        self.assertEqual(model.parent,GATE.parent/'model')
        self.assertEqual(R.sha(model),R.SCOPED_SHA)
        self.assertEqual(admission['original_model_sha256'],R.MODEL_SHA)

    def test_validation_bytes_must_be_the_approved_gate(self):
        path = self.tmp/'validation.json'; path.write_text(GATE.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'approved complete'):
            R.selected_model(path)

    def test_incomplete_gate_rejected_even_with_consistent_hash_binding(self):
        path, build = self.scope_fixture(lambda v:v.update(state='failed'))
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.select_fixture(path,build)

    def test_missing_event_equivalence_rejected(self):
        path, build = self.scope_fixture(lambda v:v.update(accepted_event_streams_byte_identical=False))
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.select_fixture(path,build)

    def test_wrong_actual_model_rejected(self):
        path, build = self.scope_fixture(bad_model=True)
        with self.assertRaisesRegex(ValueError,'bound artifact'):
            self.select_fixture(path,build)

    def test_unrelated_archive_member_change_rejected(self):
        def change(v):
            key=next(k for k in v['final_archive_members'] if not k.endswith('__Syms.o'))
            v['final_archive_members'][key]='0'*64
        path, build = self.scope_fixture(build_change=change)
        with self.assertRaisesRegex(ValueError,'archive changed'):
            self.select_fixture(path,build)

    def test_incorrect_capture_original_session_rejected(self):
        old=json.loads(R.MODEL_SESSION.read_text());old['model']['capture']='on'
        path=self.tmp/'old.json';path.write_text(json.dumps(old))
        with patch.object(R,'MODEL_SESSION',path),self.assertRaisesRegex(ValueError,'off40'):
            R.selected_model(GATE)

    def test_exact_failed_one_kib_reuse_admitted(self):
        prior=R.reuse_program(FAILED,True,1,R.SCOPED_SHA,self.sources)
        self.assertEqual(prior['program']['elf']['sha256'],R.REPEAT_ELF_SHA)

    def test_failed_repeat_cannot_admit_32_kib(self):
        with self.assertRaisesRegex(ValueError,'exact failed1KiB'):
            R.reuse_program(FAILED,True,32,R.SCOPED_SHA,self.sources)

    def test_failed_repeat_cannot_use_original_unfiltered_model(self):
        with self.assertRaisesRegex(ValueError,'exact failed1KiB'):
            R.reuse_program(FAILED,True,1,R.MODEL_SHA,self.sources)

    def test_failed_program_is_not_accepted_program_from(self):
        with self.assertRaisesRegex(ValueError,'completed accepted1KiB'):
            R.reuse_program(FAILED,False,32,R.SCOPED_SHA,self.sources)

    def test_same_source_and_selected_model_required_for_accepted_reuse(self):
        def accepted(v):
            v['state']='pass';v['model']=R.record(GATE.parent/'model/Vbsg_nonsynth_zynq_testbench')
        path=self.prior(accepted)
        self.assertEqual(R.reuse_program(path,False,32,R.SCOPED_SHA,self.sources)['footprint_kib'],1)
        with self.assertRaisesRegex(ValueError,'selected model'):
            R.reuse_program(path,False,32,R.MODEL_SHA,self.sources)

    def test_current_source_drift_rejected(self):
        sources=copy.deepcopy(self.sources);sources[R.DEPENDENCIES[0]]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source changed'):
            R.reuse_program(FAILED,True,1,R.SCOPED_SHA,sources)

    def test_all_program_files_verified_before_reuse(self):
        bad=self.tmp/'bad';bad.write_text('changed')
        for key in ('elf','mem','nbf','symbol_file','disassembly'):
            with self.subTest(key=key):
                path=self.prior(lambda v:v['program'][key].update(path=str(bad)))
                with self.assertRaisesRegex(ValueError,'bound artifact'):
                    R.reuse_program(path,True,1,R.SCOPED_SHA,self.sources)

    def test_archived_source_content_verified(self):
        bad=self.tmp/'bad-source';bad.write_text('changed')
        path=self.prior(lambda v:v['source'][R.DEPENDENCIES[0]].update(path=str(bad)))
        with self.assertRaisesRegex(ValueError,'bound artifact'):
            R.reuse_program(path,True,1,R.SCOPED_SHA,self.sources)


if __name__=='__main__':
    unittest.main()
