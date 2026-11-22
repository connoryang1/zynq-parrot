"""Pure hierarchy fixtures; no FST reader/model/compiler or launcher."""
import copy
import json
from pathlib import Path
import unittest
import inventory as m


class InventoryTests(unittest.TestCase):
    def test_real_domain_shape_adds_exact_trace_parameter(self):
        parts, union = m.domains(json.loads(m.TEMPLATE.read_text()))
        self.assertEqual(len(union),415)
        self.assertEqual(len(parts['capacity167']),167)
        self.assertEqual(len(parts['actual_geometry17']),17)
        self.assertTrue(parts['actual_geometry17'][-1]['path'].endswith('.unicore_lite.core_minimal.cache_miss_trace_p'))

    def test_complete_aliases_and_wide_payload(self):
        rows=[dict(path='TOP.a',width=512),dict(path='TOP.alias',width=512)]
        self.assertEqual(m.parse_listing('#FST\t0\t9\t-12\n#VAR\t512\t1\tTOP.a\n#VAR\t512\t1\tTOP.alias\n#END\n',rows),{'TOP.a':512,'TOP.alias':512})

    def test_missing_width_duplicate_and_truncation_refused(self):
        required=[dict(path='TOP.a',width=512)]
        for text in ('#END\n','#VAR\t64\t1\tTOP.a\n#END\n',
                     '#VAR\t512\t1\tTOP.a\n#VAR\t512\t2\tTOP.a\n#END\n',
                     '#VAR\t512\t1\tTOP.a\n', '#VAR\t512\t1\tTOP.a\n#END\n#junk\n'):
            with self.subTest(text=text), self.assertRaises(ValueError): m.parse_listing(text,required)

    def test_domain_contract_not_loosened(self):
        template=json.loads(m.TEMPLATE.read_text())
        template['domains']['capacity167'].pop()
        with self.assertRaises(ValueError):m.domains(template)


if __name__=='__main__':unittest.main()
