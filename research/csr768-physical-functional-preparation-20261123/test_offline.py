"""Offline parser/admission and inherited-lifecycle tests; all transports forbidden."""
import ast,copy,inspect,json,sys,tempfile,textwrap,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import protocol as p
import collector as c
import recovery as r
BIT='a'*64
SHAPES=Path('/home/coyang/fpga-artifacts/context-resume/csr768-board-source-shape-20261123/actual-shapes.json')
MANIFEST=Path('/home/coyang/fpga-artifacts/context-resume/retained-capacity1792-fixtures-20261121/preparation01/build01/manifest.json')


def console(role):
    built=json.loads(MANIFEST.read_text())
    p.FIXTURE_CONFIG.update(data_base='0x%016x'%built['data_base'],code_base='0x%016x'%built['code_base'])
    values=p.COUNTERS[role];raw=[values[2*n]|(values[2*n+1]<<16)for n in range(3)]
    return '\n'.join([
        'CONTROL_PROGRAM_SHA256='+p.RUNNER,'NBF_SHA256='+p.NBFS[role],'BITSTREAM_SHA256='+BIT,
        'INFO: ps.cpp: limiting target runtime to 300000 ms',
        'INFO: ps.cpp: allocating owned DRAM buffer with size 48234496',
        'bsg_zynq_pl: allocate_dram() called with size 48234496 bytes --> virtual ptr=0x20000000, physical ptr=0x10000000',
        json.loads(SHAPES.read_text())['roles'][role]['configs'][0]['line'],
        '[BSG-PASS] retained capacity checked all full64B payloads completed','INFO: CORE[0] PASS',
        'INFO: RETAINED_USE_COUNTERS version=1 '+ ' '.join(k+'='+str(v)for k,v in zip(('i_hits','d_hits','i_published','d_published','i_write_beats','d_write_beats'),values))+' saturating_bits=16 reset=axi_only',
        'INFO: RETAINED_USE_COUNTERS_STABILITY version=1 stable=1 equal=1 saturated=0 gap_us=1000 delay_rc=0 '+' '.join(k+'=0x%08x'%v for k,v in zip(('first_hits','first_published','first_writes','second_hits','second_published','second_writes'),raw+raw)),
        'INFO: Returning from ps_main with RC: 0','INFO: BSG PASS','BOARD_RUNNER_SOURCE_SHA256='+p.HELPER])+'\n'


class Offline(unittest.TestCase):
    def setUp(self):
        self.guards=[patch('subprocess.run',side_effect=AssertionError('FORBIDDEN subprocess')),patch('subprocess.Popen',side_effect=AssertionError('FORBIDDEN process')),patch.object(c.pexpect,'spawn',side_effect=AssertionError('FORBIDDEN pexpect'))]
        for g in self.guards:g.start();self.addCleanup(g.stop)
    def test_three_complete_fixture_consoles(self):
        for role in p.ROLES:
            with self.subTest(role=role):
                result=p.parse_console(console(role),role,BIT)
                self.assertEqual(result['counters'],list(p.COUNTERS[role]));self.assertEqual(result['owned_bytes'],48234496)
                self.assertEqual(result['primary_use_gate_rejected'],role=='d-off')
    def test_old_geometry_maximum_control_and_base_refused(self):
        text=console('d-enabled')
        for old,new in [('lines=768','lines=1280'),('max_lines=1792','max_lines=1280'),('sets=256','sets=64'),('active=1','active=0'),('copy=0','copy=1'),(p.FIXTURE_CONFIG['data_base'],'0x0000000080058000')]:
            with self.subTest(field=old),self.assertRaises(ValueError):p.parse_console(text.replace(old,new),'d-enabled',BIT)
    def test_payload_failures_missing_completion_and_terminal_refused(self):
        text=console('d-enabled')
        changes=[text.replace('[BSG-PASS] retained capacity checked all full64B payloads completed','[BSG-FAIL] payload word mismatch'),text.replace('[BSG-PASS] retained capacity checked all full64B payloads completed\n',''),text.replace('CORE[0] PASS','CORE FAIL'),text.replace('RC: 0','RC: 1'),text.replace('INFO: BSG PASS\n',''),text+'NATIVE_RETAINED_OBSERVER_FAIL stable=0\n',text+'ps.cpp: target runtime limit reached\n']
        for i,bad in enumerate(changes):
            with self.subTest(case=i),self.assertRaises(ValueError):p.parse_console(bad,'d-enabled',BIT)
    def test_counter_corruption_instability_saturation_and_duplicate_refused(self):
        text=console('d-enabled')
        changes=[text.replace('d_hits=768','d_hits=767'),text.replace('d_write_beats=6144','d_write_beats=65535'),text.replace('stable=1','stable=0'),text.replace('second_hits=0x03000000','second_hits=0x02000000'),text.replace('reset=axi_only','reset=bp_only'),text+'INFO: RETAINED_USE_COUNTERS version=1\n']
        for i,bad in enumerate(changes):
            with self.subTest(case=i),self.assertRaises(ValueError):p.parse_console(bad,'d-enabled',BIT)
    def test_128MiB_unaligned_zero_or_overflow_allocation_refused(self):
        text=console('d-enabled')
        for old,new in [('48234496','134217728'),('physical ptr=0x10000000','physical ptr=0x10000001'),('physical ptr=0x10000000','physical ptr=0x0'),('physical ptr=0x10000000','physical ptr=0xff000000')]:
            with self.subTest(replacement=new),self.assertRaises(ValueError):p.parse_console(text.replace(old,new),'d-enabled',BIT)
    def test_wrong_identity_and_chronology_refused(self):
        text=console('i-enabled')
        for bad in (text.replace(p.NBFS['i-enabled'],'b'*64),text.replace(BIT,'c'*64),text.replace(p.HELPER,'d'*64),text.replace('INFO: CORE[0] PASS\n','')+'INFO: CORE[0] PASS\n'):
            with self.assertRaises(ValueError):p.parse_console(bad,'i-enabled',BIT)
    def test_draft_refuses_before_reservation_output_or_transport(self):
        a=json.loads((HERE/'admission.DRAFT.json').read_text())
        with tempfile.TemporaryDirectory()as tmp,patch.object(p.base.maintained_session,'reservation')as lock:
            out=Path(tmp)/'never'
            with self.assertRaisesRegex(ValueError,'UNLAUNCHABLE'):c.execute(a,out)
            lock.assert_not_called();self.assertFalse(out.exists())
    def test_admission_top_level_guards_before_program_or_route(self):
        a=json.loads((HERE/'admission.DRAFT.json').read_text());a.update(state='bound-reviewed-capacity-diagnostic',unlaunchable_reasons=[],sources=p.source_hashes())
        with patch.object(p,'verify_programs')as programs,patch.object(p,'verify_route')as route:
            self.assertIs(p.validate(a),a);programs.assert_called_once_with(a);route.assert_called_once_with(a)
            for key,value in [('schema','old-v3'),('host','foreign'),('schedule',list(reversed(p.ROLES))),('runtime_ms',600000),('outer_timeout_s',421),('performance_inference',True),('hardware',dict(p.HARDWARE,retained_i_lines=1280)),('sources',{})]:
                bad=copy.deepcopy(a);bad[key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):p.validate(bad)
    def test_actual_generated_MAP_bytes_and_rejections(self):
        selected=Path('/home/coyang/fpga-artifacts/context-resume/csr-opt768-fpga-preparation-20261123/preparation01/usable96-image01/ROOT-selected-image.json')
        record=json.loads(selected.read_text())['artifacts']['map'];self.assertEqual(p.binding(record['path']),record)
        self.assertEqual(record['bytes'],81);self.assertEqual(record['sha256'],'cc43f4d00b80bf04c4c0050a7f2af1dc64599c330909ae5bcd3117d1564eb2ef')
        text=Path(record['path']).read_text();self.assertEqual(p.verify_map_defines(text),p.MAP_DEFINES)
        for bad in (text.replace('0x40000000','0x50000000'),text+' -DUNKNOWN=1',text+' -DACLK_MHZ=20',text+' -DGP0_ADDR_BASE=0x40000000',text.replace('-DGP0_ADDR_BASE=0x40000000',''),text+' stray',text.replace('0x80000000','nonnumeric')):
            with self.subTest(MAP=bad),self.assertRaises(ValueError):p.verify_map_defines(bad)
    def test_independent_IO_certificate_preserves_width_clock_source_guards(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);proof=root/'synthetic-evidence.json';proof.write_text('{"test_only":true}\n');e=p.binding(proof)
            runner=dict(e,sha256=p.RUNNER);a=dict(compile_gate=e,runner=runner);art=dict(hwh=e)
            cert=dict(ROOT_verified=True,values=dict(p.IO),build=e,HWH=e,host_source=e,compile_gate=e,runner=runner)
            # Isolate certificate comparisons only. Real binding reads remain
            # mandatory in production, exercised separately by actualMAP test.
            with patch.object(p,'verify_binding')as bound:
                self.assertEqual(p.verify_io_certificate(cert,art,a),p.IO);self.assertEqual(bound.call_count,5)
                for key,value in [('values',dict(p.IO,GP1_DATA_WIDTH=64)),('values',dict(p.IO,GP0_ENABLE=0)),('values',dict(p.IO,ACLK_MHZ=21)),('values',dict(p.IO,RTCLK_MHZ=4)),('ROOT_verified',False),('HWH',dict(e,sha256='0'*64)),('compile_gate',dict(e,sha256='0'*64)),('runner',dict(runner,sha256='0'*64))]:
                    bad=copy.deepcopy(cert);bad[key]=value
                    with self.subTest(field=key),self.assertRaises(ValueError):p.verify_io_certificate(bad,art,a)
                for key in ('build','HWH','host_source','compile_gate','runner'):
                    bad=copy.deepcopy(cert);del bad[key]
                    with self.subTest(missing=key),self.assertRaises(ValueError):p.verify_io_certificate(bad,art,a)
    def test_candidate_approval_identity_and_owned46M_guards(self):
        with tempfile.TemporaryDirectory()as tmp,patch.object(p,'HERE',Path(tmp)):
            root=Path(tmp);proof=root/'synthetic-proof.json';proof.write_text('{"test_only":true}\n')
            bridge=dict(schema='csr768-physical-image-approval-v1',ROOT_verified=True,state='PASS ROOT approved exact routed768 image and unchanged physical fixtures',candidate=dict(top=p.TOP,bp=p.BP,model_sha256=p.MODEL),hardware=p.HARDWARE,parameters=p.PARAMETERS,runner_API_ownership_accepted=True,owned_DRAM_bytes=48234496,evidence=dict(synthetic=p.binding(proof)))
            def checked(value,approved=True):
                image=root/'synthetic-image.json';image.write_text(json.dumps(value));im=p.binding(image)
                app=root/'approvals.ROOT.json';app.write_text(json.dumps(dict(ROOT_approved=approved,candidate_bridge=im)))
                return p.verify_candidate(dict(approvals=p.binding(app),candidate_bridge=im))
            self.assertEqual(checked(bridge),bridge['candidate'])
            with self.assertRaises(ValueError):checked(bridge,False)
            for key,value in [('candidate',dict(bridge['candidate'],top='0'*40)),('candidate',dict(bridge['candidate'],model_sha256='0'*64)),('parameters',dict(p.PARAMETERS,BP_RETAINED_I_LINES=1280)),('owned_DRAM_bytes',134217728),('runner_API_ownership_accepted',False),('ROOT_verified',False)]:
                bad=copy.deepcopy(bridge);bad[key]=value
                with self.subTest(field=key),self.assertRaises(ValueError):checked(bad)
    def test_lifecycle_inheritance_and_exact_recovery_overrides(self):
        for name in ('stage','install_runner','restore_runner','_power','recover','resolve_idle_for_final','requires_recovery'):
            self.assertIs(getattr(c.Operations,name),getattr(c.qualified.Operations,name),name)
        old=c.qualified.guard.RPC.replace('retained-capacity1280','retained-capacity768')
        for a,b in zip(('f5cd0e5dd6796252dce03ca38fbfae227cf14b3dbab395ec0eb791ba340063e1','313666a37eed4467ec39b98f98a1980ec80e6157b11434b959e6d3008204e93e','c19f4aeeb392169191722876695c780a5d3fce52c8ce83febe7ea1ce3efa7e1f'),p.NBFS.values()):old=old.replace(a,b)
        self.assertEqual(r.RPC,old);ast.parse(r.RPC)
        for name,path in p.SOURCE_PATHS.items():self.assertFalse(Path(name).is_absolute());self.assertNotIn('..',Path(name).parts);self.assertTrue(path.is_file())
        self.assertTrue(issubclass(c.Operations,c.qualified.Operations))
    def test_actual_exported_shapes_match_program_schema_accesses(self):
        actual=json.loads(SHAPES.read_text());built=json.loads(MANIFEST.read_text())
        for role in p.ROLES:
            with self.subTest(role=role):
                a=actual['roles'][role];self.assertEqual(a['lines'],768)
                self.assertEqual(a['actual_count_summary']['sets'],256);self.assertEqual(a['actual_count_summary']['expected_six_GP0'],list(p.COUNTERS[role]))
                for key in ('state','lines','actual_count_summary','targets','publications','hits','retained_bursts','ordinary_bursts','bindings','archive'):self.assertIn(key,a['keys'])
                self.assertEqual(a['array_lengths']['targets'],768)
                self.assertEqual(a['bindings']['program']['sha256'],p.BUILD);self.assertEqual(a['bindings']['model']['sha256'],p.MODEL)
                for key in ('publications','hits','retained_bursts'):self.assertEqual(a['array_lengths'][key],0 if role=='d-off'else 768)
                self.assertEqual(a['array_lengths']['ordinary_bursts'],768 if role=='d-off'else 0)
                stream=a['archive']['full_stream'];self.assertEqual(stream['reader_returncode'],0);self.assertEqual(stream['exact_end_records'],1);self.assertEqual(stream['lines'],stream['events']+169)
                cfg=p.base.fields(a['configs'][0]['line'],'RETAINED_CAPACITY_CONFIG',('version','lane','active','lines','sets','max_lines','line_bytes','data_base','code_base','code_stride','copy'))
                self.assertEqual(cfg['max_lines'],str(built['max_lines']));self.assertEqual(cfg['data_base'],'0x%016x'%built['data_base']);self.assertEqual(cfg['code_base'],'0x%016x'%built['code_base']);self.assertEqual(built['cases'][role]['nbf']['sha256'],p.NBFS[role])
    def test_inherited_methods_read_only_shared_protocol_constants(self):
        names=('__init__','record','step','rpc','inspect','inventory','matched','stage','install_runner','restore_runner','restore_overlay','_power','power','recover','resolve_idle_for_final','requires_recovery')
        allowed={'require','verify_binding','ROLES','RUNNER','OLD','HELPER','base','stage'}
        observed=set()
        for name in names:
            fn=getattr(c.Operations,name);module=ast.parse(Path(inspect.getsourcefile(fn)).read_text());node=next(x for x in ast.walk(module)if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))and x.name==name and x.lineno==fn.__code__.co_firstlineno)
            used={x.attr for x in ast.walk(node)if isinstance(x,ast.Attribute)and isinstance(x.value,ast.Name)and x.value.id=='p'}
            self.assertTrue(used<=allowed,(name,used-allowed));observed.update(used)
            old=fn.__globals__.get('p')
            for key in used:self.assertEqual(getattr(old,key),getattr(p,key),(name,key))
        self.assertTrue({'RUNNER','OLD','HELPER','ROLES','stage'}<=observed)
    def test_run_case_requires_eof_and_actual_process_success(self):
        class Child:
            exitstatus=0;signalstatus=None;logfile_read=None
            def setwinsize(self,*args):pass
            def expect(self,expected,timeout):self.logfile_read.write(console('d-enabled'));self.asserted=(expected,timeout)
            def close(self,**kwargs):pass
            def isalive(self):return False
        a=dict(host='xilinx@192.168.4.35',programs={'d-enabled':dict(path='retained-capacity768-d-enabled.nbf')},artifacts={'bit':dict(sha256=BIT)})
        with tempfile.TemporaryDirectory()as tmp:
            child=Child();result=c.run_case(a,'d-enabled',Path(tmp)/'run.log',{},Path('inert'),spawn=lambda *a,**k:child)
            self.assertEqual(result['actual_exit'],0);self.assertEqual(child.asserted,(c.pexpect.EOF,420))
            for rc,sig in ((1,None),(None,9)):
                child=Child();child.exitstatus=rc;child.signalstatus=sig
                with self.assertRaises(ValueError):c.run_case(a,'d-enabled',Path(tmp)/'bad.log',{},Path('inert'),spawn=lambda *a,**k:child)


if __name__=='__main__':unittest.main(verbosity=2)
