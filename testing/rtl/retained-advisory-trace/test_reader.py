"""Actual FSTAPI writer/reader round-trip on a tiny host-generated waveform."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
API = Path("/home/coyang/zynq-parrot/install/share/verilator/include/gtkwave")
spec = importlib.util.spec_from_file_location("reader_builder", HERE / "build_reader.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

WRITER = r'''
#include "fstapi.h"
#include <string.h>
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *f = fstWriterCreate(argv[1], 1);
  if (!f) return 3;
  fstWriterSetScope(f, FST_ST_VCD_MODULE, "TOP", 0);
  fstHandle clock = fstWriterCreateVar(f, FST_VT_SV_LOGIC, FST_VD_IMPLICIT, 1, "clk", 0);
  fstHandle word = fstWriterCreateVar(f, FST_VT_SV_LOGIC, FST_VD_IMPLICIT, 512, "word", 0);
  fstWriterCreateVar(f, FST_VT_SV_LOGIC, FST_VD_IMPLICIT, 512, "alias", word);
  fstWriterSetUpscope(f);
  char bits[513]; memset(bits, '0', 512); bits[512] = 0;
  fstWriterEmitTimeChange(f, 0);
  fstWriterEmitValueChange(f, clock, "0"); fstWriterEmitValueChange(f, word, bits);
  fstWriterEmitTimeChange(f, 5);
  bits[0] = bits[383] = bits[511] = '1';
  fstWriterEmitValueChange(f, word, bits); fstWriterEmitValueChange(f, clock, "1");
  fstWriterEmitTimeChange(f, 10); fstWriterEmitValueChange(f, clock, "0");
  fstWriterClose(f); return 0;
}
'''


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="advisory-fst-test-", dir="/dev/shm")
        cls.directory = Path(cls.tmp.name)
        cls.reader = cls.directory / "fst_events"
        subprocess.run(["python3", str(HERE / "build_reader.py"), "--output", str(cls.reader)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        source = cls.directory / "writer.c"
        source.write_text(WRITER)
        writer = cls.directory / "writer"
        result = subprocess.run(["cc", "-O2", '-DFST_CONFIG_INCLUDE="fst_config.h"', "-I" + str(API),
            str(source), str(API / "fstapi.c"), str(API / "fastlz.c"), str(API / "lz4.c"),
            "-lz", "-lm", "-o", str(writer)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stdout)
        cls.fst = cls.directory / "fixture.fst"
        subprocess.run([str(writer), str(cls.fst)], check=True, timeout=10)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def extract(self, selection):
        path = self.directory / "selection.tsv"
        path.write_text(selection)
        return subprocess.run([str(self.reader), str(self.fst), str(path)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)

    def test_real_api_preserves_512bit_values_alias_handle_and_timestamp(self):
        result = self.extract("clock\tTOP.clk\nword\tTOP.word\nalias\tTOP.alias\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [line.split("\t") for line in result.stdout.splitlines()]
        declarations = {p[1]: p for p in rows if p[0] == "#SIGNAL"}
        self.assertEqual(declarations["word"][3], declarations["alias"][3])
        handle = declarations["word"][3]
        expected = "1" + "0" * 382 + "1" + "0" * 127 + "1"
        self.assertIn(["5", handle, expected], rows)
        self.assertEqual(len(expected), 512)
        self.assertEqual(rows[-1], ["#END"])

    def test_missing_signal_fails_without_end(self):
        result = self.extract("missing\tTOP.absent\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("#END", result.stdout)

    def test_duplicate_key_rejected(self):
        self.assertNotEqual(self.extract("x\tTOP.clk\nx\tTOP.word\n").returncode, 0)

    def test_unselected_payload_not_exported(self):
        result = self.extract("clock\tTOP.clk\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(len(p.split("\t")[-1]) == 1
                            for p in result.stdout.splitlines() if not p.startswith("#")))


if __name__ == "__main__":
    unittest.main()
