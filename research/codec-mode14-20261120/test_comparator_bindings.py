"""Offline parser/CLI review only; synthetic timings are never target data."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'linux-tests'))
import compare_scheduler_pipe_hint_mode14 as comparator
import run_scheduler_pipe_hint as runner
import test_compare_scheduler_pipe_hint_mode14 as fixtures

ELF = '079f974d671908f6aa922122f6901b3123cf16ec244be25e3432b4df500b465b'
TRANSFER = '580da454d65c866aa4c0a880d63fec8948f1f813ea9791128357b892eea340d8'
LIB = 'e2c082d208dc2c6041fdef01579e1e86a441bb0dbc930e13fe8e2eee9eedc63b'
BIT = 'f0910fa4ee537963088cbeb6b21379ddb6b237af900a0aea7b12b87c0426fc3d'
ART = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120')


class CodecComparatorBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.Mode14ComparatorTests('test_primary_whole_can_regress_while_secondary_steady_improves')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare_capped_fixtures()
        self.paths = self.fixture.baseline+self.fixture.control
        for path in self.paths:
            text = path.read_text().replace('workload=lookup','workload=deflate')
            text = text.replace('PIPE_HINT_CONFIG', 'PIPE_HINT_LIBRARY name=zlib version=1.2.13 block_bytes=4096 input_corpus_kib=32\nPIPE_HINT_CONFIG',1)
            path.write_text(text)
            self.fixture.status(path,workload='deflate',elf_sha256=ELF,transfer_sha256=TRANSFER,
                bitstream_sha256=BIT,zlib_library_sha256=LIB,zlib_transfer_encoding='embedded-copy-v1',
                command='LD_LIBRARY_PATH=/tmp /tmp/scheduler_pipe_hint_benchmark_dynamic 10 2 futex-early 2 futex plain 32 deflate')

    def compare(self):
        return comparator.compare(self.fixture.baseline,self.fixture.control,10,image_pair='embedded46')

    def test_exact_real_artifact_cli_and_fixed_library_copy_without_spawn(self):
        args=runner.parse_args([str(ART/'embedded46-workloads/linux-prefix32-embedded46-baseline-shell.nbf'),
            str(ROOT/'research/complete-policy-scope-20261120/compiled/workload-zlib-scoped-resources-gzip.transfer'),
            ELF,str(self.fixture.root/'not-a-target-run.log'),'--bitstream-sha256',BIT,
            '--loops','64','--warmup','32','--repeats','4','--policy','futex-early','--sync','futex',
            '--profile','plain','--working-set-kib','32','--workload','deflate',
            '--zlib-library',str(ART/'libz.so.1'),'--embedded-zlib-library'])
        self.assertEqual(runner.build_guest_command(args),
            'LD_LIBRARY_PATH=/tmp /tmp/scheduler_pipe_hint_benchmark_dynamic 64 4 futex-early 32 futex plain 32 deflate')
        self.assertEqual(runner.library_commands(args,None),['cp /opt/bp-resume/libz.so.1 /tmp/libz.so.1'])
        runner.validate_transfer(args.transfer,ELF)

    def test_complete_codec_fixtures_and_library_hash_mismatch(self):
        result=self.compare()
        self.assertEqual(result['config']['workload'],'deflate')
        self.assertEqual(result['common_identity']['zlib_library_sha256'],LIB)
        self.fixture.status(self.paths[-1],zlib_library_sha256='e'*64)
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            self.compare()

    def test_library_banner_mismatch_and_invalid_block_are_rejected(self):
        path=self.paths[-1];text=path.read_text()
        path.write_text(text.replace('version=1.2.13','version=1.2.99'))
        with self.assertRaisesRegex(ValueError,'library configuration mismatch'):
            self.compare()
        path.write_text(text.replace('block_bytes=4096','block_bytes=2048'))
        with self.assertRaisesRegex(ValueError,'library marker'):
            self.compare()

    def test_printed_cli_config_must_agree_with_status(self):
        self.fixture.status(self.paths[-1],warmup=3)
        with self.assertRaisesRegex(ValueError,'warmup differ'):
            self.compare()

    def test_gap_all_missing_library_hash_is_not_a_generic_rejection(self):
        for path in self.paths:
            status=path.with_suffix('.log.status.json');data=json.loads(status.read_text())
            del data['zlib_library_sha256'];status.write_text(json.dumps(data))
        self.assertNotIn('zlib_library_sha256',self.compare()['common_identity'])

    def test_gap_command_string_and_delivery_encoding_are_not_generic_pins(self):
        self.fixture.status(self.paths[-1],command='/tmp/wrong-cli',zlib_transfer_encoding='gzip-base64-v1')
        self.assertEqual(self.compare()['config']['workload'],'deflate')

    def test_gap_same_wrong_cohort_identity_and_missing_helper_marker_need_study_gate(self):
        for path in self.paths:
            self.fixture.status(path,elf_sha256='e'*64,transfer_sha256='f'*64,
                zlib_library_sha256='a'*64,bitstream_sha256='b'*64)
            self.assertNotIn('BOARD_RUNNER_SOURCE_SHA256',path.read_text())
        result=self.compare()
        self.assertEqual(result['common_identity']['elf_sha256'],'e'*64)


if __name__=='__main__':
    unittest.main()
