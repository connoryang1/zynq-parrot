"""Synthetic retention cohort fixtures only; no ELF/model/board execution."""
from datetime import timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import retention_admission as module


class RetentionAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='retention-admission-')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.a=json.loads(module.ADMISSION.read_text());self.pins=json.loads(module.PINS.read_text())
        patch=mock.patch.object(module,'verify_fixed_files',return_value=[module.artifact(module.ADMISSION),module.artifact(module.PINS)])
        patch.start();self.addCleanup(patch.stop)
        self.sessions=[];self.logs=[]
        scheduled=[dict(label='pilot',pilot=True,cells=[(p,'scan') for p in self.a['pilot']['policy_order']])]
        scheduled += [dict(v,pilot=False,cells=[(v['policy'],w) for w in v['workloads']]) for v in self.a['reservation_plan']]
        for i,v in enumerate(scheduled):self.sessions.append(self.session(v,i))
        self.acquisition=self.root/'acquisition.json'
        self.acquisition.write_text(json.dumps(dict(admission_sha256=module.ADMISSION_SHA,validator_pins_sha256=module.PINS_SHA,
            all_attempts_declared=True,failed_attempts=[],pilot_session_manifest=str(self.sessions[0]),
            primary=[dict(label=v['label'],session_manifest=str(p)) for v,p in zip(self.a['reservation_plan'],self.sessions[1:])])) )

    def session(self,visit,number):
        folder=self.root/visit['label'];folder.mkdir();cells=[]
        for index,(policy,workload) in enumerate(visit['cells']):
            limits=self.a['pilot'] if visit['pilot'] else self.a['config']
            config={k:limits[k] for k in ('loops','warmup','repeats','sync','profile','working_set_kib')}
            config.update(policy=policy,workload=workload,terminal_handshake=1,configured_entries=32)
            identity={k:self.a['identity'][k] for k in ('bitstream_sha256','control_program_sha256')}
            identity.update({k+'_sha256':self.a['identity'][k]['sha256'] for k in ('nbf','elf','transfer')})
            command=module.guest_command(policy,workload,config['loops'],config['warmup'],config['repeats'])
            log=folder/f'{index}-{workload}32-{policy}.log';self.logs.append(log)
            status=dict(identity,status='PASS',runner_exit=0,legacy_four_arg_cli=False,command=command,
                **{k:v for k,v in config.items() if k!='configured_entries'})
            log.with_suffix('.log.status.json').write_text(json.dumps(status))
            lines=['INFO:    ps.cpp: allocating owned DRAM buffer with size 48234496',
                'bsg_zynq_pl: allocate_dram() called with size 48234496 bytes --> SYNTHETIC_FIXTURE',
                'Domain0 Next Arg1         : 0x0000000082200000',
                '[    0.000000] Linux version 6.6.0 SYNTHETIC_RETENTION_'+visit['label']+'_'+str(index),
                '[    0.000000] Memory limited to 46MB',
                '[    0.000000]   DMA32    [mem 0x0000000080000000-0x0000000082dfffff]',
                '[    0.000000] Kernel command line: console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M',
                '[    0.000000] Memory: 20000K/47104K available (fixture)',identity['elf_sha256']+'  '+module.GUEST_ELF,
                'PIPE_HINT_CONFIG '+' '.join(k+'='+str(config[k]) for k in ('loops','repeats','warmup','configured_entries','policy','sync','profile','working_set_kib','workload','terminal_handshake')),
                'PIPE_HINT_SCOPE version=1 mode=cell cleanup=mode0 drain=prefix-controller max_polls=4096']
            benefits={'scan':-1000,'lookup':0,'parse':3000,'chase':4000}
            benefit=benefits[workload]*(2 if policy=='retention-first' else 1)
            for repeat in range(config['repeats']):
                for order in range(2):
                    enabled=(repeat&1)^order;mode=self.a['policies'][policy] if enabled else 0
                    key=f'repeat={repeat} order={order} enabled={enabled}'
                    disabled=200000+number*1000+repeat*10
                    lines.extend([f'PIPE_HINT_RESULT {key} cycles={50000-enabled*100} loops={config["loops"]}',
                        f'PIPE_HINT_WHOLE {key} cycles={disabled-enabled*benefit} loops={config["loops"]}',
                        f'PIPE_HINT_RETENTION {key} raw=0x{((1<<63)|mode):016x} capability=1 mode={mode} completed=0 consumed_fetches=0',
                        f'PIPE_HINT_RESOURCE {key} minor_faults=20 major_faults=0 user_us=2 system_us=3 voluntary_switches=4 involuntary_switches=0'])
            lines += ['PIPE_HINT_STATUS before=0x0000000000000201 after=0x0000000000000201 configured_entries=32 dropped=0',
                      'PIPE_HINT_PASS','# poweroff -f','CORE PASS','BSG PASS','BOARD_RUNNER_SOURCE_SHA256='+self.pins['board_helper']['sha256']]
            log.write_text('\n'.join(lines)+'\n')
            cells.append(dict({k:v for k,v in config.items() if k not in ('configured_entries','terminal_handshake')},
                host=self.pins['host'],nbf=self.a['identity']['nbf']['path'],transfer=self.a['identity']['transfer']['path'],
                elf_sha256=identity['elf_sha256'],bitstream_sha256=identity['bitstream_sha256'],control_sha256=identity['control_program_sha256'],
                zlib_library=None,embedded_zlib_library=False,retention_probe=None,legacy_four_arg_cli=False,
                legacy_no_terminal_handshake=False,runtime_ms=3600000,log=str(log)))
        begin=module.timestamp(self.pins['created_utc'])+timedelta(seconds=100+number*100)
        obj=dict(state='complete',host=self.pins['host'],reservation=self.pins['reservation_lock'],all_three_acknowledged=True,
            started_utc=begin.isoformat(),released_utc=(begin+timedelta(seconds=20)).isoformat(),
            host_source_sha256=self.pins['host_sources'],plan=cells)
        for relative in self.pins['host_sources']:
            target=folder/'host-sources'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(module.ROOT/relative,target)
        path=folder/'session.json';path.write_text(json.dumps(obj));return path

    def status(self,index,**changes):
        path=self.logs[index].with_suffix('.log.status.json');obj=json.loads(path.read_text());obj.update(changes);path.write_text(json.dumps(obj))

    def mutate_session(self,index,fn):
        path=self.sessions[index];obj=json.loads(path.read_text());fn(obj);path.write_text(json.dumps(obj))

    def reject(self,pattern):
        with mock.patch.object(module,'uncertainty') as contrast:
            with self.assertRaisesRegex(ValueError,pattern):module.analyze(self.acquisition)
            contrast.assert_not_called()

    def test_full_analysis_retains_negative_null_boot_uncertainty_and_all_raw_rows(self):
        result=module.analyze(self.acquisition)
        self.assertEqual(len(result['audit']['pilot_boots_excluded']),2)
        self.assertEqual(len(result['audit']['primary_boots']),16)
        for policy in self.a['policies']:
            for workload,case in result['policy_workload_results'][policy].items():
                self.assertEqual(len(case['boots']),2)
                self.assertTrue(all(len(b['whole_cells'])==len(b['retention_status']['rows'])==len(b['resources']['rows'])==8 for b in case['boots']))
                interval=case['metrics']['absolute_enabled_cycles_per_cell']['hierarchical_95pct_ci']
                self.assertLess(interval[0],interval[1])
            self.assertLess(result['policy_workload_results'][policy]['scan']['metrics']['whole_cycles']['point'],0)
            self.assertEqual(result['policy_workload_results'][policy]['lookup']['metrics']['whole_cycles']['point'],0)
        self.assertEqual(result['first_minus_rr_by_workload']['parse']['metrics']['whole_cycles']['point'],3000)
        self.assertFalse(result['deployment_gain_claim_established'])
        self.assertFalse(result['unmodified_deployment_baseline_measured'])

    def test_zero_active_capture_and_consumed_counts_are_valid(self):
        result=module.audit(self.acquisition)
        self.assertTrue(all(row['consumed_fetches']==row['completed']==0 for b in result['primary_boots'] for row in b['retention_status']['rows']))

    def test_pilot_policy_order_is_fixed(self):
        self.mutate_session(0,lambda x:x['plan'].reverse());self.reject('planned config/order')

    def test_missing_second_pilot_rejected(self):
        self.mutate_session(0,lambda x:x['plan'].pop());self.reject('two planned')

    def test_primary_wave_order_fixed(self):
        obj=json.loads(self.acquisition.read_text());obj['primary'].reverse();self.acquisition.write_text(json.dumps(obj));self.reject('wave order')

    def test_incomplete_session_rejected(self):
        self.mutate_session(3,lambda x:x.update(state='failed'));self.reject('session incomplete')

    def test_overlapping_sessions_rejected(self):
        first=json.loads(self.sessions[1].read_text());self.mutate_session(2,lambda x:x.update(started_utc=first['started_utc']));self.reject('overlap')

    def test_more_than_two_boots_rejected(self):
        self.mutate_session(1,lambda x:x['plan'].append(dict(x['plan'][0])));self.reject('two planned')

    def test_wrong_identity_even_if_cohort_agrees_rejected(self):
        for i in range(18):self.status(i,bitstream_sha256='a'*64)
        self.reject('fixed identity')

    def test_optional_library_or_probe_plan_rejected(self):
        self.mutate_session(1,lambda x:x['plan'][0].update(retention_probe='present'));self.reject('delivery/probe')

    def test_wrong_guest_command_rejected(self):
        self.status(2,command='LD_LIBRARY_PATH=/tmp '+module.GUEST_ELF);self.reject('exact command')

    def test_changed_source8_snapshot_rejected(self):
        relative=next(iter(self.pins['host_sources']));(self.sessions[1].parent/'host-sources'/relative).write_text('changed');self.reject('snapshot changed')

    def test_old_helper_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace('BOARD_RUNNER_SOURCE_SHA256','OLD_HELPER'));self.reject('de54 helper')

    def test_missing_actual_guest_hash_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace(self.a['identity']['elf']['sha256']+'  '+module.GUEST_ELF,'no actual guest hash'));self.reject('actual guest ELF')

    def test_pipe_pass_without_return_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace('# poweroff -f',''));self.reject('shell return')

    def test_prior_probe_would_pollute_entry_rejected(self):
        p=self.logs[2];p.write_text('ICACHE_RETENTION_PROBE_PASS capability=present\n'+p.read_text());self.reject('prior probe')

    def test_missing_csr_row_rejected(self):
        p=self.logs[2];lines=p.read_text().splitlines();lines.pop(next(i for i,s in enumerate(lines) if s.startswith('PIPE_HINT_RETENTION')));p.write_text('\n'.join(lines)+'\n');self.reject('missing|order|bijection')

    def test_wrong_disabled_global_mode_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace('raw=0x8000000000000000 capability=1 mode=0','raw=0x8000000000000001 capability=1 mode=1',1));self.reject('policy mode mismatch')

    def test_disabled_stale_capture_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace('raw=0x8000000000000000 capability=1 mode=0 completed=0','raw=0x8000000000000004 capability=1 mode=0 completed=1',1));self.reject('stale capture')

    def test_nonzero_prefix_activity_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace('after=0x0000000000000201','after=0x0000000000400201'));self.reject('prefix hint|prefix activity')

    def test_missing_scope_rejected(self):
        p=self.logs[2];p.write_text('\n'.join(s for s in p.read_text().splitlines() if not s.startswith('PIPE_HINT_SCOPE'))+'\n');self.reject('fixed config')

    def test_bounds_mismatch_rejected(self):
        p=self.logs[2];p.write_text(p.read_text().replace('Memory limited to 46MB','Memory limited to 64MB'));self.reject('46MB')

    def test_duplicate_log_content_not_independent(self):
        self.logs[3].write_bytes(self.logs[2].read_bytes());self.reject('duplicate transcript content')


if __name__=='__main__':unittest.main()
