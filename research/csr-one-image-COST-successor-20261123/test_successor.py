"""HOST TEST ONLY: synthetic certificates/cycles; no physical admissions."""
import base64,copy,io,json,tarfile,tempfile,unittest
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"linux-tests"))
from unittest.mock import patch
import image_context as c
import cohort_protocol as cohort
import cost_protocol as cost
import analyze
import register
import approved_cost_images
import test_analyze_retained29_cost_cohort as math_fixture


def write(path,data):
    path.write_text(json.dumps(data)+'\n')
    return c.base.binding(path)

class Image(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='HOST_VERIFY-csr-image-');self.root=Path(self.temp.name)
        self.counter=0
        self.nbf=self.file('nbf');self.kernel=self.file('kernel')
        self.patches=[patch.object(c.base,'NBF_SHA',self.nbf['sha256']),patch.object(c.base,'KERNEL_PROOF_SHA',self.kernel['sha256'])]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def file(self,name):return write(self.root/(name+'.json'),dict(HOST_VERIFY=name))
    def make(self,n=256):
        self.counter+=1;stem='HOST_VERIFY'+str(self.counter)
        artifacts={k:self.file(stem+k)for k in ('bit','hwh','map')}
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:xz')as tar:
            for k in ('bit','hwh','map'):
                raw=Path(artifacts[k]['path']).read_bytes();entry=tarfile.TarInfo('test.'+k);entry.size=len(raw);tar.addfile(entry,io.BytesIO(raw))
        package=self.root/(stem+'.b64');package.write_bytes(base64.b64encode(buf.getvalue()));artifacts['package']=c.base.binding(package)
        artifacts.update(nbf=self.nbf,kernel_verification=self.kernel)
        artifacts['fit']=write(self.root/(stem+'fit.json'),dict(state='routed-fit-and-package-PASS HOST_VERIFY ONLY',bit_sha256=artifacts['bit']['sha256'],package_sha256=artifacts['package']['sha256']))
        h=dict(cfg='e_bp_unicore_zynqparrot_prefetch16k_cfg',retained=dict(i_lines=n,d_lines=n,set_log2=8),l1i_bytes=32768,l1d_bytes=32768,l2_bytes=16384)
        evidence=self.file(stem+'evidence');full=self.file(stem+'full')
        source=write(self.root/(stem+'source.json'),dict(schema='csr-one-image-source-qualification-v1',ROOT_verified=True,TOP=c.TOPS[n],BP=c.BP,bit_sha256=artifacts['bit']['sha256'],canonical_fullcore=full,i_lines=n,d_lines=n,sets=256,epoch_bits=8,cache_miss_trace=0,**{k:evidence for k in ('compiled_sources','parameters','strict_payload','counter')}))
        defines=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=n,BP_RETAINED_D_LINES=n,BP_RETAINED_SETS=256,BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)
        profile=write(self.root/(stem+'profile.json'),dict(TOP=c.TOPS[n],BP=c.BP,bit_sha256=artifacts['bit']['sha256'],epoch_bits=8,line_bytes=64,contexts=[dict(project=x,defines=defines,receipt=evidence)for x in ('top_ip_proj','black_parrot_bd_proj','tmp_edit_project')],**{k:evidence for k in ('config','revision_record','XPR','child_commands')}))
        clocks=write(self.root/(stem+'clock.json'),dict(scope='actual-FPGA-clock-topology',bit_sha256=artifacts['bit']['sha256'],core_hz=20000000,axi_hz=20000000,timer_hz=8000000,l1i_bytes=32768,l1d_bytes=32768,l1_sets=64,l1_ways=8,line_bytes=64,l2_bytes=16384))
        runtime=dict(profile='HOST_VERIFY-observer',runner_sha256='9'*64,source_proof=evidence,execution_proof=evidence)
        physical=dict(schema='bp-retained29-physical-capacity-qualification-v1',state='PASS root-reviewed actual physical capacity/source/clock qualification',platform='FPGA',closed_utc='2026-11-23T00:00:00+00:00',hardware=h,artifacts={k:artifacts[k]for k in ('nbf','package','bit','fit','kernel_verification')},observer_runtime=runtime,canonical_fullcore=full,source_bridge=source,clock_topology=clocks,cases=[])
        for role in ('d-enabled','d-off','i-enabled'):
            words=[0]*6 if role=='d-off' else ([0,n,0,n,0,8*n]if role=='d-enabled' else[n,0,n,0,8*n,0])
            physical['cases'].append(dict(role=role,lines=n,counter_words=words,complete=True,all_payloads_checked=True,observer_stable=True,saturated=False,recovery_verified=True,primary_use_rejected=role=='d-off',receipt=evidence,fixture=evidence,checker=evidence))
        physical_row=write(self.root/(stem+'physical.json'),physical)
        shutdown=write(self.root/(stem+'shutdown.json'),dict(ROOT_verified=True,method='normal-Linux-SBI-shutdown-plus-verified-safe-recovery',stop_printf_is_halt=False,abnormal_timeout_is_accepted_result=False))
        return dict(schema='csr-one-image-ROOT-certificate-v1',state='PASS ROOT-reviewed physical CSR image and deployed API contract',ROOT_verified=True,TOP=c.TOPS[n],BP=c.BP,lines_per_side=n,hardware=h,artifacts=artifacts,canonical_fullcore=full,source_bridge=source,clock_topology=clocks,build_profile=profile,API_provenance=evidence,normal_shutdown_scope=shutdown,physical_qualification=physical_row,approved_observer_runtime={k:runtime[k]for k in ('runner_sha256','source_proof','execution_proof')},application_runtime=dict(runner_sha256=c.base.RUNNER_SHA,helper_sha256=c.base.HELPER_SHA,application_gp0=False),allocation_contract=dict(method='successful-deployed-allocation-api-contract-v1',runner_sha256=c.base.RUNNER_SHA,helper_sha256=c.base.HELPER_SHA,libcma_sha256=c.LIBCMA,allocation_bytes=48234496,cacheable=0,extent_basis='Successful deployed cma_alloc(requested_bytes,0) owns the requested extent; no returned-size getter claimed',kernel_source_binary_equivalence_required=False,live_kernel_table_required=False))
    def registration(self,cert):return write(self.root/'certificate.json',cert)
    def test_default_registry_empty_blocks_real_entry(self):
        self.assertEqual(c.approved_images.REGISTRATIONS,{})
        cert=self.make()
        with self.assertRaisesRegex(ValueError,'unregistered'):c.registration(cert['hardware'],cert['artifacts'])
    def test_both_exact_sources_and_api_success_method(self):
        for n in (256,768):
            cert=self.make(n);c.validate_certificate(cert);row=self.registration(cert)
            with patch.dict(c.approved_images.REGISTRATIONS,{cert['artifacts']['bit']['sha256']:row},clear=True),patch.dict(approved_cost_images.PHYSICAL_REGISTRATIONS,{cert['artifacts']['bit']['sha256']:cert['physical_qualification']},clear=True):
                cohort.physical_qualification(cert['physical_qualification'],cert['hardware'],{k:cert['artifacts'][k]for k in ('nbf','package','bit','fit','kernel_verification')})
                text='bsg_zynq_pl: allocate_dram() called with size 48234496 bytes --> virtual ptr=0x70000000, physical ptr=0x10000000\n'
                result=c.actual_allocation(text,cert['hardware'],cert['artifacts']);self.assertEqual(result['owned_bytes'],48234496);self.assertFalse(result['kernel_table_read'])
    def test_old_source_geometry_clock_or_primary_observer_swap_rejected(self):
        original=self.make()
        edits=[lambda x:x.update(TOP='0'*40),lambda x:x.update(BP='b'*40),lambda x:x.update(lines_per_side=1280),lambda x:x['hardware'].update(l2_bytes=4096),lambda x:x['allocation_contract'].update(live_kernel_table_required=True),lambda x:x['application_runtime'].update(runner_sha256='9'*64)]
        for edit in edits:
            q=copy.deepcopy(original);edit(q)
            with self.assertRaises(ValueError):c.validate_certificate(q)
        q=copy.deepcopy(original);clock=c.read(q['clock_topology']);clock['timer_hz']=400000;q['clock_topology']=write(self.root/'wrongclock.json',clock)
        with self.assertRaisesRegex(ValueError,'20/8MHz'):c.validate_certificate(q)
    def test_bad_physical_counts_or_missing_bit_and_source_drift_rejected(self):
        cert=self.make();physical=c.read(cert['physical_qualification']);physical['cases'][0]['counter_words'][1]-=1
        cert['physical_qualification']=write(self.root/'badphysical.json',physical)
        with self.assertRaisesRegex(ValueError,'capacity'):c.validate_physical(cert,cert['physical_qualification'])
        cert=self.make();Path(cert['source_bridge']['path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):c.validate_certificate(cert)
    def test_null_failed_overflow_or_duplicate_allocation_record_rejected(self):
        cert=self.make();row=self.registration(cert)
        with patch.dict(c.approved_images.REGISTRATIONS,{cert['artifacts']['bit']['sha256']:row},clear=True):
            for virtual,phy in [('0x0','10000000'),('0xffffffff','10000000'),('0x70000000','0'),('0x70000000','ffffffff')]:
                text=f'allocate_dram() called with size 48234496 bytes --> virtual ptr={virtual}, physical ptr=0x{phy}\n'
                with self.assertRaises(ValueError):c.actual_allocation(text,cert['hardware'],cert['artifacts'])
            text='allocate_dram() called with size 48234496 bytes --> virtual ptr=0x70000000, physical ptr=0x10000000\n'
            with self.assertRaises(ValueError):c.actual_allocation(text*2,cert['hardware'],cert['artifacts'])
    def test_present_can_precede_cost_registration_without_source_drift(self):
        cert=self.make();physical=cert.pop('physical_qualification');cert.pop('approved_observer_runtime')
        c.validate_certificate(cert);row=self.registration(cert)
        with patch.dict(c.approved_images.REGISTRATIONS,{cert['artifacts']['bit']['sha256']:row},clear=True):
            import functional_protocol as functional
            before=functional.source_hashes()
            c.registration(cert['hardware'],cert['artifacts'])
            with self.assertRaisesRegex(ValueError,'not registered'):c.physical(physical,cert['hardware'],cert['artifacts'])
            new=self.root/'new-cost.py';register.emit_physical(Path(row['path']),row['sha256'],Path(physical['path']),physical['sha256'],new)
            self.assertIn(physical['sha256'],new.read_text())
            self.assertEqual(functional.source_hashes(),before)
            self.assertNotIn(str((c.HERE/'approved_cost_images.py').relative_to(c.base.ROOT)),before)
    def test_registrar_external_sha_and_new_file_only(self):
        cert=self.make();row=self.registration(cert);out=self.root/'new-approval.py'
        with self.assertRaisesRegex(ValueError,'external ROOT'):register.emit(Path(row['path']),'0'*64,out)
        register.emit(Path(row['path']),row['sha256'],out)
        self.assertIn(row['sha256'],out.read_text());self.assertEqual(c.approved_images.REGISTRATIONS,{})
        with self.assertRaisesRegex(ValueError,'new source'):register.emit(Path(row['path']),row['sha256'],out)

class InheritedControls(unittest.TestCase):
    def test_real_local_ledger_failure_blocks_retry_and_later_slot(self):
        import collect
        import fcntl
        with tempfile.TemporaryDirectory(prefix='HOST_VERIFY-ledger-') as tmp:
            root=Path(tmp);ledger=dict(ledger_path=str(root/'acquisition-ledger.json'))
            def operation(index):
                result=object.__new__(collect.Operations)
                result.wrapper=dict(cohort={'HOST_VERIFY':True},prior_results=[])
                result.input_record={'HOST_VERIFY':True};result.ledger_lock=None;result.ledger=None;result.entry=None
                return result,cohort.canonical_visits()[index]
            op,visit=operation(0)
            with patch.object(cohort,'static_admission',return_value=({},ledger,visit)),patch.object(cohort.safe.Operations,'stage'):
                try:op.stage();op.finish_attempt(False,error='HOST_VERIFY injected failure')
                finally:op.close_ledger()
            for index in (0,1):
                op,visit=operation(index)
                with patch.object(cohort,'static_admission',return_value=({},ledger,visit)),patch.object(cohort.safe.Operations,'stage') as stage:
                    try:
                        with self.assertRaises(ValueError):op.stage()
                        stage.assert_not_called()
                    finally:op.close_ledger()
    def test_complete_gate_rejects_subset_before_parsing_any_session(self):
        with tempfile.TemporaryDirectory(prefix='HOST_VERIFY-incomplete-') as tmp:
            root=Path(tmp);cohort_row=write(root/'cohort.json',{'HOST_VERIFY':True})
            ledger=write(root/'ledger.json',dict(schema='bp-retained29-cost-acquisition-ledger-v1',cohort=cohort_row,entries=[]))
            with self.assertRaisesRegex(ValueError,'all16'):cohort.verify_complete(cohort_row,ledger)

    def test_complete_fixed_workloads_masks_order_and_metric(self):
        visits=cohort.canonical_visits();self.assertEqual(len(visits),16)
        self.assertEqual([v['plan']['rotation']for v in visits[1:]],[0]*5+[2]*5+[4]*5)
        self.assertEqual(set(cost.WORKLOADS),{'scan','lookup','parse','chase','regex'})
        for visit in visits[1:]:
            self.assertEqual({(x['kib'],x['mask'])for x in visit['plan']['cases']},{(k,m)for k in (32,128)for m in (9,6,15)})
        result=analyze.estimate(math_fixture.boots());self.assertEqual(result['primary']['ratio'],1);self.assertEqual(result['counts']['performance_boots'],15)
        self.assertEqual(result['counts']['primary_joint_pairs'],120)
    def test_missing_boot_or_reused_uuid_is_not_passing_subset(self):
        data=math_fixture.boots();data.pop()
        with self.assertRaises(ValueError):analyze.estimate(data)
        data=math_fixture.boots();data[1]['acquisition_boot_id']=data[0]['acquisition_boot_id']
        with self.assertRaises(ValueError):analyze.estimate(data)
    def test_joint_whole_primary_is_not_favorable_diagnostic(self):
        result=analyze.estimate(math_fixture.boots(lambda v,c,r:2 if c['mask']==15 else .5))
        self.assertAlmostEqual(result['primary']['ratio'],2);self.assertEqual(result['primary']['endpoint'],'whole')
        self.assertEqual(result['primary']['mask'],15)
    def test_runtime_snapshot_has_every_new_module_and_unchanged_safe_engine(self):
        import functional_protocol as f
        import retained29_safe_session as safe
        for protocol in (f,cost,cohort):
            actual=set(protocol.source_hashes())
            self.assertTrue(set(c.source_names())<=actual)
            self.assertIn('linux-tests/retained29_safe_session.py',actual)
        self.assertIs(cohort.safe,safe)

if __name__=='__main__':unittest.main()
