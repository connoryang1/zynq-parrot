#!/usr/bin/env python3
"""Exercise request accounting, configuration bounds, and single-CPU affinity.

These host functional checks do not establish BlackParrot performance or Linux
board acceptance. Their compiler and generated executables stay in a temporary
directory, separate from simulator and FPGA artifacts.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def expected_checksum(workers, count, kib):
    total = 0
    mask = kib * 1024 // 64 - 1
    for worker in range(workers):
        state = 0x9e3779b9 ^ (worker + 1)
        for _ in range(count):
            state ^= (state << 13) & 0xffffffff
            state ^= state >> 17
            state ^= (state << 5) & 0xffffffff
            total += (state & mask) + 1
    return total


class RequestBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="request-benchmark-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / "benchmark"
        subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-O2",
                        "-Wall", "-Wextra", "-Werror", "-pthread",
                        str(HERE / "request_benchmark.c"), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=30)

    def run_benchmark(self, *args, **kwargs):
        return subprocess.run([str(self.binary), *map(str, args)],
                              text=True, capture_output=True, timeout=30, **kwargs)

    def test_exact_requests_checksums_and_rotating_order(self):
        for workers, count, kib in ((1, 1, 1), (2, 17, 64), (10, 128, 64), (64, 1, 1)):
            with self.subTest(workers=workers, requests=count):
                run = self.run_benchmark("--workers", workers, "--requests", count,
                                         "--data-kib", kib, "--samples", 3)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("[REQUEST-BENCH] PASS", run.stdout)
                self.assertIn("backend=x86-prefetcht0", run.stdout)
                self.assertNotIn("load-ahead", run.stdout)
                self.assertEqual([line for line in run.stdout.splitlines()
                                  if line.startswith("WARMUP_PASS ")],
                                 ["WARMUP_PASS mode=linux-threads-demand",
                                  "WARMUP_PASS mode=batched-prefetch-load"])
                lines = [line for line in run.stdout.splitlines() if line.startswith("RESULT ")]
                self.assertEqual(len(lines), 6)
                for position, line in enumerate(lines):
                    values = dict(re.findall(r"(\w+)=([^ ]+)", line))
                    sample, order = position // 2 + 1, position % 2
                    self.assertEqual(int(values["sample"]), sample)
                    self.assertEqual(int(values["order"]), order)
                    self.assertEqual(values["mode"], "batched-prefetch-load" if
                                     (sample + order) % 2 else "linux-threads-demand")
                    self.assertEqual(int(values["requests"]), workers * count)
                    self.assertEqual(int(values["checksum"]), expected_checksum(workers, count, kib))
                    self.assertGreater(int(values["ns"]), 0)

    def test_invalid_configuration_fails_before_running(self):
        cases = [("--workers", "0"), ("--workers", "65"), ("--workers", "-1"),
                 ("--requests", "0"), ("--requests", "1048577"), ("--requests", "1junk"),
                 ("--samples", "0"), ("--samples", "1001"), ("--data-kib", "3"),
                 ("--data-kib", "0"), ("--data-kib", "262144"),
                 ("--cpu", "1024"), ("--cpu", "9999999999999999999999"),
                 ("--unknown", "1"), ("--workers",)]
        for args in cases:
            with self.subTest(args=args):
                run = self.run_benchmark(*args)
                self.assertNotEqual(run.returncode, 0)
                self.assertNotIn("RESULT ", run.stdout)
                self.assertNotIn("PASS", run.stdout)

    def test_affinity_is_respected_and_unavailable_cpu_rejected(self):
        allowed = os.sched_getaffinity(0)
        selected = min(allowed)
        excluded = next(cpu for cpu in range(1024) if cpu != selected)
        restrict = lambda: os.sched_setaffinity(0, {selected})
        run = self.run_benchmark("--workers", 2, "--requests", 1, "--samples", 1,
                                 "--data-kib", 1, preexec_fn=restrict)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(f" cpu={selected} ", run.stdout)
        run = self.run_benchmark("--cpu", excluded, preexec_fn=restrict)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("outside the allowed affinity mask", run.stderr)

    def test_help(self):
        run = self.run_benchmark("--help")
        self.assertEqual(run.returncode, 0)
        self.assertIn("Requests are per worker", run.stdout)
        self.assertNotIn("RESULT ", run.stdout)

    def test_host_hardware_request_fails_closed(self):
        run = self.run_benchmark("--hardware")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("--hardware requires BlackParrot RV64", run.stderr)
        self.assertNotIn("RESULT ", run.stdout)

    def test_host_cannot_mislabel_prefetch_as_faulting_load(self):
        build = subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-O2",
                                "-pthread", "-DBP_REQUEST_LOAD_AHEAD=1",
                                str(HERE / "request_benchmark.c"), "-o",
                                str(Path(self.temp.name) / "invalid-load-control")],
                               text=True, capture_output=True, timeout=30)
        self.assertNotEqual(build.returncode, 0)
        self.assertIn("faulting-load control requires BlackParrot RV64", build.stderr)


if __name__ == "__main__":
    unittest.main()
