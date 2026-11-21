"""Synthetic complete-cohort fixtures; never model/board or primary-data reads."""
from datetime import timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import codec_admission as codec
REAL_VERIFY_FIXED_FILES=codec.verify_fixed_files


class CodecAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='codec-admission-host-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.a=json.loads(codec.ADMISSION.read_text())
        patch=mock.patch.object(codec,'verify_fixed_files',return_value=[codec.artifact(codec.ADMISSION)])
        patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(codec.generic,'verify_reviewed_images',return_value={'synthetic_image_fixture':True})
        patch.start();self.addCleanup(patch.stop)
        self.sessions=[]
        for i,row in enumerate([self.a['pilot']]+self.a['primary_plan']):
            self.sessions.append(self.make_session(row,i))
        self.acquisition=self.root/'acquisition.json'
        self.write_acquisition()

    def write_acquisition(self,**changes):
        obj=dict(admission_sha256=codec.ADMISSION_SHA,all_attempts_declared=True,
            pilot_session_manifest=str(self.sessions[0]),primary=[dict(label=r['label'],session_manifest=str(p))
                for r,p in zip(self.a['primary_plan'],self.sessions[1:])],failed_attempts=[])
        obj.update(changes);self.acquisition.write_text(json.dumps(obj))

    def make_session(self,row,index):
        pilot=index==0;directory=self.root/row['label'];directory.mkdir()
        log=directory/'0-deflate32-futex-early.log';config=dict(self.a['config'])
        if pilot:config.update({k:self.a['pilot'][k] for k in ('loops','warmup','repeats')})
        nbf=self.a['files']['baseline_nbf' if row['image']=='A' else 'control_nbf']
        identity=dict(self.a['identity'],nbf_sha256=nbf['sha256'])
        command=self.a['pilot']['guest_command'] if pilot else self.a['guest_command']
        status=dict(identity,status='PASS',runner_exit=0,command=command,
            zlib_transfer_encoding='embedded-copy-v1',legacy_four_arg_cli=False,
            **{k:v for k,v in config.items() if k not in ('configured_entries','resource_stats','complete_policy_scope')})
        log.with_suffix('.log.status.json').write_text(json.dumps(status))
        lines=['INFO:    ps.cpp: allocating owned DRAM buffer with size 48234496',
            'bsg_zynq_pl: allocate_dram() called with size 48234496 bytes --> synthetic-host-fixture',
            'Domain0 Next Arg1         : 0x0000000082200000',
            '[    0.000000] Linux version 6.6.0 SYNTHETIC_CODEC_'+row['label'],
            '[    0.000000] Memory limited to 46MB',
            '[    0.000000]   DMA32    [mem 0x0000000080000000-0x0000000082dfffff]',
            '[    0.000000] Kernel command line: console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M',
            '[    0.000000] Memory: 20000K/47104K available (fixture)',
            identity['zlib_library_sha256']+'  /tmp/libz.so.1',identity['elf_sha256']+'  /tmp/scheduler_pipe_hint_benchmark_dynamic',
            'PIPE_HINT_LIBRARY name=zlib version=1.2.13 block_bytes=4096 input_corpus_kib=32',
            'PIPE_HINT_CONFIG '+' '.join(k+'='+str(config[k]) for k in
                ('loops','repeats','warmup','configured_entries','policy','sync','profile','working_set_kib','workload','terminal_handshake')),
            'PIPE_HINT_SCOPE version=1 mode=cell cleanup=mode0 drain=prefix-controller max_polls=4096']
        for repeat in range(config['repeats']):
            for order in range(2):
                enabled=(repeat&1)^order;key=f'repeat={repeat} order={order} enabled={enabled}'
                # B has larger paired benefit yet larger absolute enabled cost.
                disabled=200000+(5000 if row['image']=='B' else 0)
                benefit=12000 if row['image']=='B' else 10000
                lines.extend([f'PIPE_HINT_RESULT {key} cycles={100000-enabled*1000} loops={config["loops"]}',
                    f'PIPE_HINT_WHOLE {key} cycles={disabled-enabled*benefit} loops={config["loops"]}',
                    f'PIPE_HINT_RESOURCE {key} minor_faults=20 major_faults=0 user_us=2 system_us=3 voluntary_switches=4 involuntary_switches=0'])
        triggers=min(255,config['repeats']*(config['warmup']+config['loops']+1))
        admitted=config['repeats']*32
        after=1|(32<<4)|(32<<13)|(admitted<<22)|(triggers<<38)|(511<<55)
        lines.extend([f'PIPE_HINT_STATUS before=0x0000000000000201 after=0x{after:016x} configured_entries=32 dropped=0',
            'PIPE_HINT_PASS','# poweroff -f','CORE PASS','BSG PASS',
            'BOARD_RUNNER_SOURCE_SHA256='+self.a['board_helper']['sha256']])
        log.write_text('\n'.join(lines)+'\n')
        cell=dict({k:v for k,v in config.items() if k not in ('configured_entries','resource_stats','complete_policy_scope','terminal_handshake')},
            host=self.a['host'],nbf=nbf['path'],transfer=self.a['files']['transfer']['path'],elf_sha256=identity['elf_sha256'],
            bitstream_sha256=identity['bitstream_sha256'],control_sha256=identity['control_program_sha256'],
            zlib_library=self.a['files']['zlib_library']['path'],embedded_zlib_library=True,retention_probe=None,
            legacy_four_arg_cli=False,legacy_no_terminal_handshake=False,runtime_ms=3600000,log=str(log))
        begin=codec.timestamp(self.a['created_utc'])+timedelta(seconds=100+index*100)
        session=dict(state='complete',reservation=self.a['reservation_lock'],all_three_acknowledged=True,
            host=self.a['host'],started_utc=begin.isoformat(),released_utc=(begin+timedelta(seconds=10)).isoformat(),
            host_source_sha256=self.a['host_sources'],plan=[cell])
        for relative in self.a['host_sources']:
            target=directory/'host-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(codec.ROOT/relative,target)
        path=directory/'session.json';path.write_text(json.dumps(session));return path

    def change_status(self,index,**changes):
        p=self.sessions[index].parent/'0-deflate32-futex-early.log.status.json'
        obj=json.loads(p.read_text());obj.update(changes);p.write_text(json.dumps(obj))

    def change_session(self,index,mutate):
        p=self.sessions[index];obj=json.loads(p.read_text());mutate(obj);p.write_text(json.dumps(obj))

    def reject(self,pattern):
        with mock.patch.object(codec.generic,'compare') as compare:
            with self.assertRaisesRegex(ValueError,pattern):codec.analyze(self.acquisition)
            compare.assert_not_called()

    def test_complete_cohort_excludes_pilot_and_preserves_absolute_regression_limit(self):
        result=codec.analyze(self.acquisition)
        self.assertEqual(len(result['audit']['sessions']),4)
        self.assertTrue(all('pilot-A' not in p for a in result['audit']['comparator_inputs'].values() for p in a))
        self.assertEqual(result['primary']['primary_whole_cell_control_minus_baseline']['saved_cycles_per_cell'],2000)
        decision=result['absolute_whole_crosschecks']['decision_crosschecks']
        self.assertTrue(decision['positive_primary_without_supported_absolute_enabled_reduction'])
        self.assertFalse(decision['kernel_optimization_claim_established'] if 'kernel_optimization_claim_established' in decision else result['absolute_whole_crosschecks'].get('kernel_optimization_claim_established',False))

    def test_library_hash_required_and_pinned_even_if_all_statuses_agree(self):
        for i in range(5):self.change_status(i,zlib_library_sha256='a'*64)
        self.reject('exact runner identity.*zlib')

    def test_missing_library_hash_rejected(self):
        p=self.sessions[-1].parent/'0-deflate32-futex-early.log.status.json';x=json.loads(p.read_text());del x['zlib_library_sha256'];p.write_text(json.dumps(x))
        self.reject('exact runner identity.*zlib')

    def test_wrong_ld_command_and_encoding_rejected(self):
        self.change_status(1,command='/tmp/wrong');self.reject('LD_LIBRARY_PATH')

    def test_wire_library_encoding_rejected(self):
        self.change_status(1,zlib_transfer_encoding='gzip-base64-v1');self.reject('encoding differs')

    def test_wrong_cohort_elf_bit_transfer_rejected(self):
        for i in range(5):self.change_status(i,elf_sha256='a'*64)
        self.reject('exact runner identity.*elf')

    def test_old_or_missing_helper_marker_rejected(self):
        p=self.sessions[1].parent/'0-deflate32-futex-early.log';p.write_text(p.read_text().replace('BOARD_RUNNER_SOURCE_SHA256','OLD_HELPER_SOURCE_SHA256'))
        self.reject('executed de54')

    def test_actual_library_reply_and_hash_order_required(self):
        p=self.sessions[1].parent/'0-deflate32-futex-early.log';p.write_text(p.read_text().replace(self.a['identity']['zlib_library_sha256']+'  /tmp/libz.so.1','not-an-actual-guest-hash'))
        self.reject('actual guest.*libz')

    def test_pipe_pass_without_shell_return_is_rejected(self):
        p=self.sessions[1].parent/'0-deflate32-futex-early.log';p.write_text(p.read_text().replace('# poweroff -f',''))
        self.reject('normal shell return')

    def test_one_boot_per_reservation_required(self):
        self.change_session(1,lambda x:x['plan'].append(dict(x['plan'][0])));self.reject('one boot')

    def test_wrong_abba_or_missing_pilot_rejected(self):
        x=json.loads(self.acquisition.read_text());x['primary'][0],x['primary'][1]=x['primary'][1],x['primary'][0];self.acquisition.write_text(json.dumps(x));self.reject('label/order')

    def test_overlap_and_incomplete_sessions_rejected_before_comparison(self):
        self.change_session(3,lambda x:x.update(state='failed'));self.reject('session incomplete')

    def test_changed_frozen_source_snapshot_rejected(self):
        relative=next(iter(self.a['host_sources']));p=self.sessions[1].parent/'host-sources'/relative;p.write_text('changed')
        self.reject('source8 snapshot')

    def test_actual_bounds_and_cli_configuration_remain_strict(self):
        p=self.sessions[1].parent/'0-deflate32-futex-early.log';p.write_text(p.read_text().replace('Memory limited to 46MB','Memory limited to 64MB'));self.reject('46MB')

    def test_overlapping_boot_reservations_rejected(self):
        first=json.loads(self.sessions[1].read_text())
        self.change_session(2,lambda x:x.update(started_utc=first['started_utc']))
        self.reject('overlap')

    def test_duplicate_session_cannot_supply_independent_boot(self):
        x=json.loads(self.acquisition.read_text());x['primary'][2]['session_manifest']=x['primary'][1]['session_manifest'];self.acquisition.write_text(json.dumps(x))
        self.reject('duplicate session')

    def test_actual_elf_hash_reply_required(self):
        p=self.sessions[1].parent/'0-deflate32-futex-early.log';p.write_text(p.read_text().replace(self.a['identity']['elf_sha256']+'  /tmp/scheduler_pipe_hint_benchmark_dynamic','not-an-actual-elf-hash'))
        self.reject('actual guest.*scheduler_pipe')

    def test_preflight_detects_changed_host_library_bytes(self):
        p=self.root/'bad-library';p.write_bytes(b'bad')
        wrong=dict(self.a);wrong['files']={'zlib_library':dict(path=str(p),bytes=3,sha256=self.a['identity']['zlib_library_sha256'])}
        with self.assertRaisesRegex(ValueError,'fixed codec artifact changed'):
            REAL_VERIFY_FIXED_FILES(wrong)


if __name__=='__main__':unittest.main()
