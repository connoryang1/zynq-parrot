"""Pure fixtures only: no compiler, FST reader or model execution."""
import hashlib
import json
from pathlib import Path
import unittest
from common import HERE,MODEL_SHA,STAGE,SP
import canonical
import host_flow

OLD=HERE.parents[1]/'retained256-observation-clone-20261122/helper'


class PreparationTests(unittest.TestCase):
    def test_existing_algorithms_byte_identical(self):
        for name in ('canonical.py','framing.py','protocol.py'):
            with self.subTest(name=name):self.assertEqual((HERE/name).read_bytes(),(OLD/name).read_bytes())

    def test_only_registration_insertion(self):
        original='HEAD\n        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n        __Vm_dumperp->open("x");\nTAIL\n'
        rows=[dict(path='TOP.a',width=512),dict(path='TOP.b',width=1)]
        changed,extra=host_flow.filtered_source(original,rows)
        self.assertEqual(changed.replace(extra,''),original)
        self.assertEqual(extra.count('dumpvars(1,'),2)
        self.assertNotIn('eval(',extra)
        with self.assertRaises(ValueError):host_flow.filtered_source(original,rows+rows)
        with self.assertRaises(ValueError):host_flow.filtered_source(original+original,rows)

    def test_new_actual_model_and_literal_source_root(self):
        self.assertEqual(MODEL_SHA,'695e53dccdf418dac6e40ec1c652752e82fb7187c834dbd689ac80233445a80c')
        self.assertIn('borrow256-trace0',str(STAGE))
        self.assertEqual(SP.name,'zynq-parrot-linux-borrow256-profile')
        compile((SP/'testing/rtl/retained-advisory-trace/validate.py').read_text(),str(SP),'exec')

    def test_canonical_fullstream_retains_every_transition_and_rejects_corruption(self):
        leaves=[dict(path='TOP.a',width=1)]
        base=['#FST\t0\t10\t-12\n','#SIGNAL\ts000\t1\t7\tTOP.a\n','0\t7\t0\n','1\t7\t1\n','1\t7\t0\n','#END\n']
        output=[];a=canonical.canonicalize(base,leaves,output.append)
        self.assertEqual(a['events'],3)
        changed=base.copy();changed[3]='1\t7\t0\n'
        b=canonical.canonicalize(changed,leaves,lambda _:None)
        self.assertNotEqual(a['sha256'],b['sha256'])
        for bad in (base[:-1],base+['2\t7\t1\n']):
            with self.assertRaises(ValueError):canonical.canonicalize(bad,leaves,lambda _:None)


if __name__=='__main__':unittest.main()
