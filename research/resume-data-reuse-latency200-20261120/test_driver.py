"""Read-only latency200 driver tests; no compiler, build or target execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('scoped200',HERE/'build_scoped_model.py')
D=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(D)


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.manifest,self.report=D.old200_baseline()
        self.names=json.loads((HERE/'required-signals.json').read_text())['canonical_names_verbatim']

    def test_original200_identity_and_configuration(self):
        old=D.original_session()
        self.assertEqual(old['model']['configured_axi_memory_latency_ticks'],200)
        self.assertEqual(old['model']['binary']['sha256'],D.MODEL_SHA)
        self.assertEqual(old['model']['capture'],'off')
        self.assertEqual(old['blackparrot_revision'],'ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57')

    def test_compiler_and_pch_map_preserve_exact200_flags(self):
        compile_argv,link_argv,binding=D.commands()
        self.assertIn('-DBP_AXI_MEM_READ_LATENCY=200',compile_argv)
        self.assertNotIn('-DBP_AXI_MEM_READ_LATENCY=40',compile_argv)
        self.assertIn('-DVM_TRACE=1',compile_argv)
        self.assertIn('-DVM_TRACE_FST=1',compile_argv)
        self.assertIn('-DBP_AXI_MEM_READ_QUEUE_DEPTH=4',compile_argv)
        self.assertEqual(binding['original_pch_creation_argv'][:-5],binding['original_compile_argv'][:-6])
        self.assertEqual(compile_argv[-5],D.PREFIX+'__pch.h')
        self.assertEqual([arg for arg in link_argv if arg.endswith(('.a','.o'))],
                         list(D.HOST_OBJECTS)+[D.PREFIX+'__ALL.a'])

    def test_own_mode0_counter1944_and_checksum(self):
        text=Path(self.manifest['mode0']['log']['path']).read_text()
        self.assertEqual(D.mode0_values(text),1944)

    def test_40_counter_is_not_200_oracle(self):
        path=D.REPO/'research/resume-retention-matrix-20261120/burst-off40/mode0/run.log'
        with self.assertRaisesRegex(ValueError,'old200'):D.mode0_values(path.read_text())

    def test_wrong_modes_duplicate_counter_and_bad_checksums_rejected(self):
        text=Path(self.manifest['mode0']['log']['path']).read_text()
        variants=(text.replace('Mode: 0x0000000000000000','Mode: 0x0000000000000001'),
                  text+'\nResume cycles: 0x798\n',
                  text.replace('Prefix checksum:                0x0000000000000060',
                               'Prefix checksum:                0x0000000000000061'))
        for item in variants:
            with self.subTest(item=item[-80:]),self.assertRaises(ValueError):D.mode0_values(item)

    def test_frozen_baseline_really_is_complete_old200(self):
        self.assertTrue(self.manifest['complete_converter_eof'])
        self.assertEqual(self.manifest['old_session']['sha256'],D.SESSION_SHA)
        self.assertEqual(self.manifest['mode0']['resume_core_global_cycles'],1944)
        self.assertEqual(self.report['validation'],'passed')

    def test_all105_same_watch_paths_verified_on_old200(self):
        self.assertEqual(len(self.names),105)
        self.assertEqual(set(self.names),set(self.report['signals'].values()))
        self.assertEqual(sum('physical_thread_context_id_r['in name for name in self.names),2)
        self.assertEqual(sum('tag_mem_'in name and name.endswith(('.tag','.state'))for name in self.names),48)

    def test_matching_own_report_and_events_admitted(self):
        D.compare_own200_audit(self.report,Path(self.manifest['events']['path']),self.names,
                              self.manifest,self.report)

    def test_counts_alone_do_not_accept_40_event_timestamps(self):
        old40=D.REPO/'research/resume-data-reuse-20261120/scoped-mode0-validation/old-events.jsonl'
        self.assertNotEqual(D.sha(old40),self.manifest['events']['sha256'])
        with self.assertRaisesRegex(ValueError,'event stream'):
            D.compare_own200_audit(self.report,old40,self.names,self.manifest,self.report)

    def test_bad_statistics_or_missing_signal_rejected(self):
        bad=copy.deepcopy(self.report);bad['stats']['ordinary_misses']+=1
        with self.assertRaisesRegex(ValueError,'statistics'):
            D.compare_own200_audit(bad,Path(self.manifest['events']['path']),self.names,self.manifest,self.report)
        bad=copy.deepcopy(self.report);bad['signals'].pop(next(iter(bad['signals'])))
        with self.assertRaisesRegex(ValueError,'signal names'):
            D.compare_own200_audit(bad,Path(self.manifest['events']['path']),self.names,self.manifest,self.report)

    def test_failed_audit_rejected(self):
        bad=copy.deepcopy(self.report);bad['validation']='failed'
        with self.assertRaisesRegex(ValueError,'incomplete'):
            D.compare_own200_audit(bad,Path(self.manifest['events']['path']),self.names,self.manifest,self.report)

    def test_snapshot_and430_file_inventory_bindings(self):
        path=HERE/'source-review/generated-inventory.json'
        self.assertEqual(D.sha(path),D.INVENTORY_SHA)
        inventory=json.loads(path.read_text())
        self.assertEqual(inventory['recorded_blackparrot_revision'],'ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57')
        files={item['name']:item for item in inventory['files']}
        self.assertEqual(len(files),430)
        for name in D.HOST_OBJECTS:self.assertIn(name,files)
        self.assertEqual(files[D.PREFIX+'__ALL.a']['sha256'],D.ARCHIVE_SHA)
        self.assertEqual(D.sha(HERE/'source-review'/(D.SYMS+'.cpp')),D.SYMS_SHA)

    def test_changed_capture_or_latency_session_rejected(self):
        for field,value in(('capture','on'),('configured_axi_memory_latency_ticks',40)):
            with tempfile.TemporaryDirectory()as temporary:
                directory=Path(temporary);old=json.loads((D.OLD/'session.json').read_text())
                old['model'][field]=value;path=directory/'session.json';path.write_text(json.dumps(old))
                with patch.object(D,'OLD',directory),patch.object(D,'SESSION_SHA',D.sha(path)),\
                     self.assertRaisesRegex(ValueError,'configuration'):
                    D.original_session()


if __name__=='__main__':unittest.main()
