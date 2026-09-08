#!/usr/bin/env python3
"""Build and exercise the optional AXI model in an isolated Verilator directory.

The explicit-clock C++ driver works with the repository's g++ 9 toolchain.
These tests never use or overwrite the full-system simulator's build artifacts.
"""
import os
from pathlib import Path
import resource
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def disable_core_dumps():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class PipelinedAXIMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retained = os.environ.get("BP_AXI_MEM_TEST_OUT")
        if retained:
            cls.out = Path(retained).resolve()
            cls.out.mkdir(parents=True, exist_ok=True)
        else:
            cls.temp = tempfile.TemporaryDirectory(prefix="axi-memory-test-")
            cls.addClassCleanup(cls.temp.cleanup)
            cls.out = Path(cls.temp.name)
        build = cls.out / "obj_dir"
        verilator = os.environ.get("VERILATOR", str(ROOT / "install/bin/verilator"))
        command = [verilator, "--cc", "--exe", "--build", "--assert", "-j", "2",
                   "--top-module", "bp_nonsynth_axi_mem_pipelined", "--Mdir", str(build),
                   "-Gaxi_id_width_p=3", "-Gaxi_addr_width_p=16", "-Gmem_els_p=1024",
                   "-Ginit_data_p=16909060", "-CFLAGS", "-std=c++14 -Wall -Wextra -Werror",
                   str(ROOT / "cosim/v/bp_nonsynth_axi_mem_pipelined.sv"),
                   str(ROOT / "cosim/tests/axi_mem_pipelined_test.cpp")]
        run = subprocess.run(command, cwd=cls.out, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=120)
        (cls.out / "build.log").write_bytes(run.stdout)
        if run.returncode:
            raise RuntimeError("isolated model build failed:\n" + run.stdout.decode())
        cls.binary = build / "Vbp_nonsynth_axi_mem_pipelined"

    def run_case(self, name):
        result = subprocess.run([str(self.binary), name], cwd=self.out,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=10, preexec_fn=disable_core_dumps)
        (self.out / (name + ".log")).write_bytes(result.stdout)
        return result

    def test_independent_latency_and_axi_protocol(self):
        run = self.run_case("positive")
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertIn(b"[AXI-MEM-TEST] PASS", run.stdout)
        self.assertIn(b"outstanding_max=4 first_latency=40 second_after_first_last=1 fifth_latency=40",
                      run.stdout)

    def test_malformed_wlast_is_rejected(self):
        run = self.run_case("bad_wlast")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn(b"AXI WLAST does not match AWLEN", run.stdout)

    def test_boundary_crossing_is_rejected(self):
        run = self.run_case("bad_boundary")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn(b"AXI INCR burst crosses a 4 KiB boundary", run.stdout)

    def test_unaligned_transfer_is_rejected(self):
        run = self.run_case("bad_alignment")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn(b"AXI memory requires aligned transfers", run.stdout)


if __name__ == "__main__":
    unittest.main()
