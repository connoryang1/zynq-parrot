#!/usr/bin/env python3
"""Exercise the Linux NBF timer patch against a synthetic embedded DTB.

The test reconstructs the final sparse NBF memory image, so it checks both the
timer-selector replacement and the aligned override write used for the DTB.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
PATCHER = HERE / "patch_linux_nbf_timer.py"
WIDTHS = {0: 1, 1: 2, 2: 4, 3: 8}


@unittest.skipUnless(shutil.which("dtc") and shutil.which("fdtget")
                     and shutil.which("fdtput"), "device-tree tools required")
class TimerPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        dts = self.root / "input.dts"
        self.dtb = self.root / "input.dtb"
        dts.write_text("""/dts-v1/;
/ {
  cpus {
    #address-cells = <1>;
    #size-cells = <0>;
    timebase-frequency = <10000000>;
  };
};
""")
        subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o",
                        str(self.dtb), str(dts)], check=True)
        blob = self.dtb.read_bytes()
        blob += bytes((-len(blob)) % 8)
        lines = ["02_0000000000308000_0000000000000001\n"]
        for offset in range(0, len(blob), 8):
            value = int.from_bytes(blob[offset:offset + 8], "little")
            lines.append(f"03_{0x80010000 + offset:016x}_{value:016x}\n")
        lines.append("02_0000000000200008_0000000000000000\n")
        self.source = self.root / "input.nbf"
        self.source.write_text("".join(lines))

    def reconstruct(self, path: Path) -> tuple[list[int], bytes]:
        memory = {}
        selectors = []
        for line in path.read_text().splitlines():
            command, address, data = (int(value, 16)
                                      for value in line.split("_"))
            if address == 0x308000:
                selectors.append(data)
            if command in WIDTHS and 0x80000000 <= address < 0x90000000:
                width = WIDTHS[command]
                for offset, byte in enumerate(data.to_bytes(width, "little")):
                    memory[address + offset] = byte
        start = next(address for address in sorted(memory)
                     if bytes(memory.get(address + i, 0) for i in range(4))
                     == b"\xd0\x0d\xfe\xed")
        size = struct.unpack(">I", bytes(memory[start + i]
                                         for i in range(4, 8)))[0]
        return selectors, bytes(memory[start + i] for i in range(size))

    def test_selector_and_timebase_change_together(self):
        output = self.root / "output.nbf"
        result = subprocess.run([str(PATCHER), str(self.source), str(output)],
                                check=True, text=True, capture_output=True)
        self.assertIn("device-tree patch writes: 1", result.stdout)
        selectors, blob = self.reconstruct(output)
        patched = self.root / "patched.dtb"
        patched.write_bytes(blob)
        value = subprocess.check_output(
            ["fdtget", "-t", "i", str(patched), "/cpus",
             "timebase-frequency"], text=True).strip()
        self.assertEqual(selectors, [2])
        self.assertEqual(value, "8000000")

    def test_matching_timebase_still_changes_selector(self):
        output = self.root / "output.nbf"
        result = subprocess.run(
            [str(PATCHER), "--frequency", "10000000",
             str(self.source), str(output)], check=True, text=True,
            capture_output=True)
        self.assertIn("device-tree patch writes: 0", result.stdout)
        selectors, _ = self.reconstruct(output)
        self.assertEqual(selectors, [2])


if __name__ == "__main__":
    unittest.main()
