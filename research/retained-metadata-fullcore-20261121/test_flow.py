"""Offline admission/geometry tests; no build or target subprocess is invoked."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location('metadata_'+name,HERE/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

flow=load('run_full');geometry=load('geometry')

class FlowTests(unittest.TestCase):
    def command(self):
        macro=' '.join('-D'+n+'='+str(v) for n,v in [('ACLK_MHZ',20),('BP_RETAINED_BUFFER',1),
            ('BP_RETAINED_I_LINES',1280),('BP_RETAINED_D_LINES',1280),('BP_RETAINED_SETS',256),
            ('BP_RETAINED_OBSERVE',1),('BP_AXI_RESPONSE_DELAY',0)])
        return '--assert --trace-fst --build-jobs 3 -DBSG_HIDE_FROM_SYNTHESIS '+macro+' '+ ' '.join(str(flow.ROOT/'import/black-parrot'/p) for p in ('bp_common/src/v/bp_retained_line_store.sv','bp_me/src/v/cce/bp_uce.sv'))

    def test_exact_command_and_wrong_path_macro_assert(self):
        c=self.command();flow.validate_actual_command(c)
        for bad in (c.replace('ACLK_MHZ=20','ACLK_MHZ=18'),c.replace('--assert',''),
                    c.replace('BP_RETAINED_I_LINES=1280','BP_RETAINED_I_LINES=64'),
                    c+' -DBP_RETAINED_METADATA_VERIFY',c+' -DBP_CUSTOM_BASE_CFG=x',
                    c.replace(str(flow.ROOT/'import/black-parrot'),'wrong')):
            with self.assertRaises(ValueError):flow.validate_actual_command(bad)

    def test_static_stamp_cannot_be_custom_or_different_geometry(self):
        good='.build_config-nt-nc-cfge_bp_unicore_zynqparrot_prefetch16k_cfg-trace1-BP_AXI_RESPONSE_DELAY_0-BP_RETAINED_BUFFER_1-BP_RETAINED_I_LINES_1280-BP_RETAINED_D_LINES_1280-BP_RETAINED_SETS_256-BP_RETAINED_OBSERVE_1-assert-bsgsimhidden-support'
        flow.validate_stamp(good)
        for old,new in [('prefetch16k_cfg','custom_cfg'),('trace1','trace0'),('SETS_256','SETS_64')]:
            with self.assertRaises(ValueError):flow.validate_stamp(good.replace(old,new))

    def test_output_scope(self):
        with self.assertRaises(ValueError):flow.validate_output(Path('/tmp/outside-metadata'))

    def test_reserve_and_allocation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'data').write_bytes(b'x')
            enough=mock.Mock(free=flow.RESERVE+flow.ALLOCATION)
            with mock.patch.object(flow.shutil,'disk_usage',return_value=enough):flow.resource_check(p)
            with mock.patch.object(flow.shutil,'disk_usage',return_value=mock.Mock(free=flow.RESERVE)):
                with self.assertRaises(ValueError):flow.resource_check(p)
            with mock.patch.object(flow,'directory_bytes',return_value=flow.ALLOCATION+1):
                with self.assertRaises(ValueError):flow.resource_check(p)

    def events(self):
        lines=['#FST\t0\t100\t-12\n']
        for n,k in enumerate(geometry.EXPECTED,1):lines.append(f'#SIGNAL\t{k}\t32\t{n}\tTOP.dut.unicore_lite.{k}\n')
        for n,(k,v) in enumerate(geometry.EXPECTED.items(),1):lines.append(f'0\t{n}\t{v:032b}\n')
        return lines+['#END\n']

    def test_actual_parameters_full_eof(self):
        result=geometry.parse(self.events());self.assertTrue(result['clean_eof'])
        for lines in (self.events()[:-1],self.events()+['100\t1\t'+32*'0'+'\n']):
            with self.assertRaises(ValueError):geometry.parse(lines)

    def test_wrong_thread_or_unknown_param(self):
        for bits in (f'{4:032b}',32*'x'):
            lines=self.events();lines[-17]='0\t1\t'+bits+'\n'
            with self.assertRaises(ValueError):geometry.parse(lines)

if __name__=='__main__':unittest.main()
