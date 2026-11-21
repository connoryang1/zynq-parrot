"""Test bounded FDT parsing and DDR write-tail ownership offline.

Fixtures are synthetic DTBs and NBF records; no target execution occurs.
"""
from pathlib import Path
import struct
import tempfile
import unittest

import build_pair as gate
from verify_pair import load_write_bound


def fixture(bootargs=None, duplicate=False):
    names = ('#address-cells', '#size-cells', 'bootargs', 'device_type', 'reg')
    strings, offsets = b'', {}
    for name in names:
        offsets[name] = len(strings)
        strings += name.encode() + b'\0'
    word = lambda value: struct.pack('>I', value)

    def node(name):
        value = name.encode() + b'\0'
        return word(1) + value + b'\0' * (-len(value) % 4)

    def prop(name, data):
        return word(3) + word(len(data)) + word(offsets[name]) + data + b'\0' * (-len(data) % 4)

    if bootargs is None:
        bootargs = b'console=hvc0 loglevel=8 rdinit=/bin/sh          \0'
    tree = node('') + prop('#address-cells', word(2)) + prop('#size-cells', word(2))
    tree += node('chosen') + prop('bootargs', bootargs)
    if duplicate:
        tree += prop('bootargs', bootargs)
    tree += word(2) + node('memory@80000000') + prop('device_type', b'memory\0')
    tree += prop('reg', struct.pack('>QQ', 0x80000000, 64 * 1024 * 1024))
    tree += word(2) + word(2) + word(9)
    total = 56 + len(tree) + len(strings)
    header = struct.pack('>10I', 0xd00dfeed, total, 56, 56 + len(tree), 40, 17, 16, 0, len(strings), len(tree))
    return header + bytes(16) + tree + strings


class FdtCapTests(unittest.TestCase):
    def test_padding_edit_preserves_header_property_length_and_all_other_properties(self):
        old = fixture()
        before = gate.parse_fdt(old)
        prop, original, capped = gate.bootarg_edit(before)
        self.assertEqual(len(original), len(capped))
        self.assertEqual(capped, b'console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M  ')
        new = bytearray(old)
        new[prop['offset']:prop['offset'] + len(capped)] = capped
        after = gate.parse_fdt(bytes(new))
        self.assertEqual(old[:40], new[:40])
        self.assertEqual(before['total'], after['total'])
        self.assertEqual(prop['bytes'], 49)
        self.assertEqual(sum(a != b for a, b in zip(old, new)), 7)
        for a, b in zip(before['properties'], after['properties']):
            if a['name'] != 'bootargs':
                self.assertEqual(a, b)

    def test_rejects_truncation_block_overlap_bad_name_offset_and_duplicates(self):
        original = fixture()
        bad_overlap = bytearray(original)
        struct.pack_into('>I', bad_overlap, 12, 60)
        bad_name = bytearray(original)
        prop = gate.parse_fdt(original)['properties'][0]
        struct.pack_into('>I', bad_name, prop['offset'] - 4, 0xffffffff)
        for bad in (original[:-1], bytes(bad_overlap), bytes(bad_name), fixture(duplicate=True)):
            with self.subTest(length=len(bad)):
                with self.assertRaises(ValueError):
                    gate.parse_fdt(bad)

    def test_rejects_different_or_already_capped_bootargs(self):
        for args in (b'console=hvc0 rdinit=/bin/sh\0',
                     b'console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M  \0'):
            with self.assertRaisesRegex(ValueError, 'exact reviewed'):
                gate.bootarg_edit(gate.parse_fdt(fixture(args)))

    def test_inventory_distinguishes_all_valid_trees_and_false_magic(self):
        image = bytearray(8192)
        first, second = fixture(), fixture()
        image[16:16 + len(first)] = first
        image[4096:4096 + len(second)] = second
        image[7000:7004] = gate.FDT_MAGIC
        candidates, valid = gate.inventory(image)
        self.assertEqual([address for address, _ in valid], [gate.BASE + 16, gate.BASE + 4096])
        self.assertEqual(len(candidates), 3)
        self.assertFalse(candidates[-1]['valid'])


class DdrWriteBoundTests(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.nbf'
            path.write_text(text)
            return load_write_bound(path)

    def test_exact_final_byte_and_word_fit_and_mmio_stays_separate(self):
        result = self.check('03_0000000082dffff8_ffffffffffffffff\n'
                            '00_0000000082dfffff_0000000000000001\n'
                            '02_0000000000200008_0000000000000000\n')
        self.assertEqual(result['maximum_load_end_exclusive'], '0x82e00000')
        self.assertEqual(result['maximum_load_offset'], '0x2dfffff')
        self.assertEqual(result['ddr_write_count'], 2)
        self.assertEqual(result['separate_config_or_mmio_records'], 1)

    def test_rejects_write_tail_overrun_and_high_unowned_memory(self):
        for record in ('03_0000000082dffffc_0000000000000000\n',
                       '02_0000000082dffffe_0000000000000000\n',
                       '00_0000000082e00000_0000000000000000\n',
                       '03_0000000083fffff8_0000000000000000\n'):
            with self.subTest(record=record):
                with self.assertRaisesRegex(ValueError, 'tail.*exceeds'):
                    self.check(record)

    def test_rejects_width_truncation_and_empty_ddr_inventory(self):
        with self.assertRaisesRegex(ValueError, 'actual NBF width'):
            self.check('00_0000000080000000_0000000000000100\n')
        with self.assertRaisesRegex(ValueError, 'no advertised-DDR'):
            self.check('02_0000000000200008_0000000000000000\n')


if __name__ == '__main__':
    unittest.main()
