"""Reject false success from corrupted real-driver outputs, without target runs."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import prepare


class OracleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (Path(__file__).resolve().parent /
                    "preparation-001/oracle-32-7.stdout").read_text()

    def check(self, text):
        return prepare.oracle(text, 32, 7, 17)

    def test_actual_closed_driver(self):
        self.assertEqual(self.check(self.text)["actual_regexec_calls"], 1088)

    def test_schema_is_independent_and_anchored(self):
        row = b"id=17 user=alice status=fail bytes=91"
        self.assertEqual(prepare.scan(row)[0], 7)
        self.assertEqual(prepare.scan(row.replace(b"fail", b"warn"))[0], 3)
        for bad in (row + b" extra=ignored", row.replace(b"alice", b"Alice"),
                    row.replace(b"17", b"1234567"), row.replace(b"91", b"-1")):
            self.assertEqual(prepare.scan(bad)[0], 0)

    def test_changed_record(self):
        lines = self.text.splitlines()
        fields = lines[1].split()
        fields[-1] = "49" + fields[-1][2:]
        lines[1] = " ".join(fields)
        with self.assertRaises(AssertionError):
            self.check("\n".join(lines))

    def test_changed_request_checksum(self):
        lines = self.text.splitlines()
        index = next(n for n, line in enumerate(lines) if line.startswith("REQUEST "))
        fields = lines[index].split(); fields[2] = "%016x" % (int(fields[2], 16) ^ 1)
        lines[index] = " ".join(fields)
        with self.assertRaises(AssertionError):
            self.check("\n".join(lines))

    def test_call_count(self):
        with self.assertRaises(AssertionError):
            self.check(self.text.replace("calls=64 ", "calls=63 ", 1))

    def test_missing_request(self):
        lines = [line for line in self.text.splitlines() if not line.startswith("REQUEST 0 ")]
        with self.assertRaises(AssertionError):
            self.check("\n".join(lines))

    def test_missing_pass(self):
        with self.assertRaises(AssertionError):
            self.check(self.text.replace("RETAINED29_REGEX_FUNCTIONAL_PASS", "INCOMPLETE"))


if __name__ == "__main__":
    unittest.main()
