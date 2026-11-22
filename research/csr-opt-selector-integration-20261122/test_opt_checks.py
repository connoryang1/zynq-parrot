"""ROOT-only bounded pure-fixture gate. Never invokes launcher/Make/vendor."""
import unittest
from pathlib import Path
import opt_checks as c


class OptChecks(unittest.TestCase):
    def fixture(self):
        names=('PLACE_DESIGN','PHYS_OPT_DESIGN','ROUTE_DESIGN','POST_ROUTE_PHYS_OPT_DESIGN')
        receipt='selected_opt_directive\tExploreArea\n'+''.join('STEPS.'+n+'.ARGS.DIRECTIVE\tExplore\tExplore\n'for n in names)
        def xpr(value):
            return '<Project><Runs><Run Id="impl_1"><Strategy><StratHandle Name="Performance_ExplorePostRoutePhysOpt"/>'+''.join(
                '<Step Id="'+name+'"><Option Id="Directive">'+(value if name=='opt_design'else'0')+'</Option></Step>'for name in
                ('opt_design','place_design','phys_opt_design','route_design','post_route_phys_opt_design'))+'</Strategy></Run></Runs></Project>'
        return ['opt_directive=ExploreArea\n','set ::env(IMPL_OPT_DIRECTIVE) {ExploreArea}\n',receipt,
                'BP-IMPL-OPT-CONFIG: requested=ExploreArea actual=ExploreArea other_step_properties_unchanged=1\n',
                c.SYNTH+'\n','\n'.join(c.IMPL)+'\n',xpr('TEST_ONLY_NEW_ENUM'),xpr('0')]

    def test_exact_launch(self):
        a=c.expected_launch(Path('/source'),Path('/work'),Path('/logs'))
        c.check_launch(a,'/source','/work','/logs',c.TOP1536,c.BP)
        self.assertEqual(c.expected_defines(c.TOP1536)['BP_RETAINED_I_LINES'],1536)
        self.assertEqual(c.expected_defines(c.TOP256)['BP_RETAINED_D_LINES'],256)
        del a['environment']['FPGA_OPT_DIRECTIVE']
        with self.assertRaises(ValueError):c.check_launch(a,'/source','/work','/logs',c.TOP1536,c.BP)

    def test_all_extra_gates(self):
        r=c.check_generated_text(*self.fixture());self.assertEqual(r['selected'],'ExploreArea')

    def test_wrong_config(self):
        a=self.fixture();a[1]=a[1].replace('ExploreArea','Explore')
        with self.assertRaises(ValueError):c.check_generated_text(*a)

    def test_other_property_changed(self):
        a=self.fixture();a[2]=a[2].replace('Explore\tExplore','Explore\tDefault',1)
        with self.assertRaises(ValueError):c.check_generated_text(*a)

    def test_old_child(self):
        a=self.fixture();a[5]=a[5].replace('opt_design -directive ExploreArea','opt_design -directive Explore')
        with self.assertRaises(ValueError):c.check_generated_text(*a)

    def test_missing_or_changed_xpr(self):
        a=self.fixture();a[6]=a[7]
        with self.assertRaises(ValueError):c.check_generated_text(*a)
        a=self.fixture();a[6]=a[6].replace('Id="route_design"><Option Id="Directive">0','Id="route_design"><Option Id="Directive">9')
        with self.assertRaises(ValueError):c.check_generated_text(*a)


if __name__=='__main__':unittest.main()
