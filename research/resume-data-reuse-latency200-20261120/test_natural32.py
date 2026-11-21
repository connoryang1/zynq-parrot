"""Strict admission/preparation tests; no model, compiler or board executes."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('natural200',HERE/'run_natural32.py')
D=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(D)


class Natural32Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='natural32-admission-')
        self.addCleanup(self.temp.cleanup);self.tmp=Path(self.temp.name)

    def source_fixture(self,change_source=None,change_audit=None):
        source=json.loads((D.BASELINE/'session.json').read_text())
        audit=json.loads((D.BASELINE/'dcache-audit/manifest.json').read_text())
        base=self.tmp/'source40';(base/'dcache-audit').mkdir(parents=True)
        if change_source:change_source(source)
        path=base/'session.json';path.write_text(json.dumps(source))
        audit['inputs']['session']=D.rec(path)
        if change_audit:change_audit(audit)
        ap=base/'dcache-audit/manifest.json';ap.write_text(json.dumps(audit))
        pins=dict(D.PINS,session40=D.sha(path),audit40=D.sha(ap))
        return base,pins

    def gate_fixture(self,change_gate=None,change_build=None,bad_model=False):
        gate=json.loads(D.GATE.read_text());build=json.loads((D.GATE.parent/'model/build.json').read_text())
        base=self.tmp/'gate';(base/'model').mkdir(parents=True)
        if change_build:change_build(build)
        bp=base/'model/build.json';bp.write_text(json.dumps(build))
        gate['build_manifest']=dict(gate['build_manifest'],sha256=D.sha(bp),bytes=bp.stat().st_size)
        if change_gate:change_gate(gate)
        path=base/'validation.json';path.write_text(json.dumps(gate))
        model=base/'model'/D.PREFIX
        if bad_model:model.write_text('changed model')
        else:shutil.copyfile(D.GATE.parent/'model'/D.PREFIX,model)
        pins=dict(D.PINS,gate200=D.sha(path),build200=D.sha(bp))
        return path,pins

    def test_real_closed_source_and200_gate_admitted(self):
        source,audit,metadata,observed,parser,model,bindings=D.admit()
        self.assertEqual(source['program']['elf']['sha256'],D.ELF)
        self.assertEqual(source['runtime_nbf']['sha256'],D.RUNTIME_NBF)
        self.assertEqual(D.sha(model),D.MODEL200)
        self.assertEqual(metadata['expected_target_loads_by_context']['0'],parser.expected_target_loads(32,0))
        self.assertEqual(observed['timed_requests'],32)

    def test_rejects_any_wrong_footprint_protocol_elf_or_source_model(self):
        changes=(lambda s:s.update(footprint_kib=1),lambda s:s.update(protocol='epochs-v1'),
                 lambda s:s['program']['elf'].update(sha256='0'*64),
                 lambda s:s['model'].update(sha256=D.MODEL200))
        for index,change in enumerate(changes):
            with self.subTest(index=index),tempfile.TemporaryDirectory()as temporary:
                with patch.object(self,'tmp',Path(temporary)):
                    base,pins=self.source_fixture(change_source=change)
                with patch.object(D,'BASELINE',base),patch.object(D,'PINS',pins),\
                     self.assertRaisesRegex(ValueError,'closed32KiB40'):
                    D.admit()

    def test_incomplete_or_missing_full_source_audit_rejected(self):
        for key in ('complete_converter_eof','complete_custom_guest_parser_recheck',
                    'independent_metadata_load_generator_recheck'):
            with self.subTest(key=key),tempfile.TemporaryDirectory()as temporary:
                with patch.object(self,'tmp',Path(temporary)):
                    base,pins=self.source_fixture(change_audit=lambda a:a.update({key:False}))
                with patch.object(D,'BASELINE',base),patch.object(D,'PINS',pins),\
                     self.assertRaisesRegex(ValueError,'audit incomplete'):
                    D.admit()

    def test_archived_source_content_must_match(self):
        bad=self.tmp/'bad.c';bad.write_text('changed')
        base,pins=self.source_fixture(change_source=lambda s:s['source']['testing/mt_resume_data_reuse_benchmark.c'].update(path=str(bad)))
        with patch.object(D,'BASELINE',base),patch.object(D,'PINS',pins),\
             self.assertRaisesRegex(ValueError,'bound artifact'):
            D.admit()

    def test_runtime_nbf_bytes_must_match(self):
        bad=self.tmp/'bad.nbf';bad.write_text('changed')
        base,pins=self.source_fixture(change_source=lambda s:s['runtime_nbf'].update(path=str(bad)))
        with patch.object(D,'BASELINE',base),patch.object(D,'PINS',pins),\
             self.assertRaisesRegex(ValueError,'bound artifact'):
            D.admit()

    def test_gate_counter_latency_and_bank_must_match200(self):
        for key,value in (('complete_ring_cycles',664),('configured_memory_latency_ticks',40),
                          ('model_l2_banks',2),('accepted_event_streams_byte_identical',False)):
            with self.subTest(key=key),tempfile.TemporaryDirectory()as temporary:
                with patch.object(self,'tmp',Path(temporary)):
                    gate,pins=self.gate_fixture(change_gate=lambda g:g.update({key:value}))
                with patch.object(D,'GATE',gate),patch.object(D,'PINS',pins),\
                     self.assertRaisesRegex(ValueError,'200 trace equivalence'):
                    D.admit()

    def test_changed_evaluation_archive_member_rejected(self):
        def change(build):
            key=next(key for key in build['final_archive_members']if not key.endswith('__Syms.o'))
            build['final_archive_members'][key]='0'*64
        gate,pins=self.gate_fixture(change_build=change)
        with patch.object(D,'GATE',gate),patch.object(D,'PINS',pins),\
             self.assertRaisesRegex(ValueError,'archive changed'):
            D.admit()

    def test_wrong_actual200_executable_rejected(self):
        gate,pins=self.gate_fixture(bad_model=True)
        with patch.object(D,'GATE',gate),patch.object(D,'PINS',pins),\
             self.assertRaisesRegex(ValueError,'bound artifact'):
            D.admit()

    def test_equal_counts_cannot_substitute_old40_event_stream(self):
        path=D.ROOT/'research/resume-data-reuse-20261120/scoped-mode0-validation/old-events.jsonl'
        def change(gate):
            gate['old_events']=D.rec(path);gate['scoped_events']=D.rec(path)
        gate,pins=self.gate_fixture(change_gate=change)
        with patch.object(D,'GATE',gate),patch.object(D,'PINS',pins),\
             self.assertRaisesRegex(ValueError,'OWN event stream'):
            D.admit()

    def test_prepare2400_copies_exact_elf_nbf_without_process(self):
        output=self.tmp/'prepared'
        class StopBeforeTarget(Exception):pass
        with patch.object(D,'run_model',side_effect=StopBeforeTarget),\
             patch.object(D.subprocess,'Popen',side_effect=AssertionError('unexpected process')):
            with self.assertRaises(StopBeforeTarget):
                D.main(['--output',str(output),'--native-runtime-seconds','2400'])
        state=json.loads((output/'session.json').read_text())
        self.assertEqual(state['program']['elf']['sha256'],D.ELF)
        self.assertEqual(state['runtime_nbf']['sha256'],D.RUNTIME_NBF)
        self.assertEqual(state['native_runtime_seconds'],2400)
        self.assertEqual(state['host_guard_seconds'],2580)
        self.assertEqual(state['baseline40_native_seconds'],1800)
        self.assertEqual(state['command'][1],'+c_args=prog.nbf 2400000')
        self.assertEqual(state['configured_memory_latency_ticks'],200)

    def test_host_guard_terminates_child_without_launching_real_process(self):
        class Fake:
            terminated=False
            def poll(self):return 0 if self.terminated else None
            def terminate(self):self.terminated=True
            def wait(self,timeout=None):return 0
        process=Fake();runtime=self.tmp/'runtime';runtime.mkdir()
        with patch.object(D.subprocess,'Popen',return_value=process),\
             patch.object(D.time,'monotonic',side_effect=[0,2581]):
            with self.assertRaisesRegex(ValueError,'host guard'):
                D.run_model(['fake-model'],runtime,runtime/'run.log',2580)
        self.assertTrue(process.terminated)


if __name__=='__main__':unittest.main()
