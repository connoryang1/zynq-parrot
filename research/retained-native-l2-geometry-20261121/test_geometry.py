import unittest
from audit_geometry import constants,summary
from source_chain import source_records


class Geometry(unittest.TestCase):
    def test_both_actual_source_manifest_shapes(self):
        records={'/source':{'sha256':'fixed'}}
        self.assertEqual(source_records(records),records)
        self.assertEqual(source_records({'sources':records,'metadata':{}}),records)
        with self.assertRaises(ValueError):source_records({'metadata':{}})
    def test_constant_aliases_and_changes(self):
        e={'a':'TOP.a','b':'TOP.b'}
        text='#FST\t0\t100\t-12\n#SIGNAL\ta\t32\t9\tTOP.a\n#SIGNAL\tb\t32\t9\tTOP.b\n0\t9\t'+format(32,'032b')+'\n#END\n'
        self.assertEqual(constants(text,e),{'a':32,'b':32})
        changed=text.replace('#END','1\t9\t'+format(64,'032b')+'\n#END')
        with self.assertRaisesRegex(ValueError,'changed'):constants(changed,e)
        with self.assertRaisesRegex(ValueError,'clean EOF'):constants(text.replace('#END\n',''),e)

    def values(self,banks,sets):
        v=dict(l2_slices_p=1,l2_banks_p=banks,l2_sets_p=sets,l2_assoc_p=2,l2_block_width_p=512)
        for side in ('i','d'):
            for key,value in (('sets_p',64),('assoc_p',8),('block_width_p',512)):v[side+'cache_'+key]=value
        for bank in range(banks):
            for key,value in (('sets_p',sets),('ways_p',2),('data_width_p',64),('block_size_in_words_p',8)):v['bank%d.%s'%(bank,key)]=value
        return v

    def test_actual_instantiated_bank_capacity(self):
        for banks,sets,total in ((1,32,4096),(2,64,16384)):
            r=summary(self.values(banks,sets),list(range(banks)))
            self.assertEqual(r['L2_bytes'],total);self.assertEqual(r['ordinary_L1_bytes'],{'i':32768,'d':32768})

    def test_top_bank_count_and_real_geometry_must_match(self):
        v=self.values(2,64)
        with self.assertRaisesRegex(ValueError,'hierarchy count'):summary(v,[0])
        v['bank1.sets_p']=16
        with self.assertRaisesRegex(ValueError,'actual cache bank'):summary(v,[0,1])


if __name__=='__main__':unittest.main()
