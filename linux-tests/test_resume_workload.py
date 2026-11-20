"""Check private resume workloads against independent Python generators.

These are host correctness tests; their results say nothing about replay
effectiveness, simulated memory latency, or FPGA performance.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MASK = (1 << 64) - 1


def mix(value):
    value &= MASK
    value = ((value ^ (value >> 30)) * 0xbf58476d1ce4e5b9) & MASK
    value = ((value ^ (value >> 27)) * 0x94d049bb133111eb) & MASK
    return value ^ (value >> 31)


def reference(mode, kib, seed, epochs):
    size = kib * 1024
    if not size:
        return 0
    if mode == "scan":
        one = sum((seed + line) % 256 for line in range((size + 63) // 64))
        return one * epochs & MASK
    if mode == "parse":
        records = bytearray()
        expected = 0
        number = 0
        while True:
            random = mix(seed + number)
            key = 1 + random % 1000000
            length = 16 + (random >> 24) % 97
            payload = bytes(97 + ((random + j * 7) & MASK) % 26
                            for j in range(length))
            record = str(key).encode() + b":" + payload + b"\n"
            if len(records) + len(record) + 1 > size:
                break
            records.extend(record)
            expected += key + sum(payload)
            number += 1
        return expected * epochs & MASK
    total = 0
    if mode == "lookup":
        entries = size // 16 // 2
        for epoch in range(epochs):
            for query in range(64):
                key = 1 + mix(seed + epoch * 64 + query) % entries
                if query % 8 != 7:
                    total += mix(seed ^ key)
    else:
        nodes = size // 64
        for rank in range(epochs * min(nodes, 64)):
            total += mix(seed ^ (rank % nodes))
    return total & MASK


DRIVER = r'''
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include "resume_workload.h"
int main(int argc, char **argv)
{
    struct resume_workload w;
    unsigned epochs = 41;
    uint64_t total = 0, seed;
    if (argc != 5) return 2;
    seed = strtoull(argv[3], NULL, 0);
    if (resume_workload_init(&w, argv[1], strtoul(argv[2], NULL, 0), seed))
        return 3;
    assert(resume_workload_check_total(&w, 0));
    if (!strcmp(argv[4], "corrupt")) {
        if (!w.bytes) return 4;
        if (w.kind == resume_lookup) {
            struct resume_lookup_slot *slots = (void *)w.data;
            for (size_t i = 0; i < w.count; ++i) ++slots[i].value;
        } else if (w.kind == resume_chase) {
            struct resume_chase_node *nodes = (void *)w.data;
            ++nodes[w.cursor].value;
        } else {
            ++w.data[0];
        }
        total = resume_workload_run(&w);
        assert(!resume_workload_check(&w, total));
        assert(!resume_workload_check_total(&w, total));
    } else {
        for (unsigned i = 0; i < epochs; ++i) {
            uint64_t result = resume_workload_run(&w);
            assert(resume_workload_check(&w, result));
            total += result;
        }
        assert(resume_workload_check_total(&w, total));
        assert(!resume_workload_check_total(&w, total + 1));
        printf("%" PRIu64 "\n", total);
    }
    resume_workload_free(&w);
    assert(!w.data && !w.bytes && !w.runs);
    return 0;
}
'''


class ResumeWorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="resume-workload-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "driver.c"
        source.write_text(DRIVER)
        cls.binary = source.with_suffix("")
        subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-O2",
                        "-Wall", "-Wextra", "-Werror", "-I", str(HERE),
                        str(source), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=30)

    def run_workload(self, mode, kib, seed, action="run"):
        return subprocess.run([str(self.binary), mode, str(kib), str(seed), action],
                              capture_output=True, text=True, timeout=30)

    def test_sizes_seeds_and_epoch_checksums(self):
        for mode in ("scan", "lookup", "parse", "chase"):
            for kib in (0, 1, 3, 32, 256, 1024):
                for seed in (0, 0x1234, MASK):
                    with self.subTest(mode=mode, kib=kib, seed=seed):
                        run = self.run_workload(mode, kib, seed)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        self.assertEqual(int(run.stdout), reference(mode, kib, seed, 41))

    def test_corrupted_values_are_rejected(self):
        for mode in ("scan", "lookup", "parse", "chase"):
            with self.subTest(mode=mode):
                run = self.run_workload(mode, 32, 1234, "corrupt")
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_unknown_mode_rejected_before_work(self):
        run = self.run_workload("unknown", 32, 1)
        self.assertEqual(run.returncode, 3)
        self.assertEqual(run.stdout, "")


class ResumeProtocolHostTests(unittest.TestCase):
    """Exercise actual fork, pipe/futex exchange, drain, and checksum checks."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="resume-protocol-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / "benchmark"
        subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-O2",
                        "-Wall", "-Wextra", "-Werror", "-DBP_RESUME_HOST_VERIFY=1",
                        str(HERE / "scheduler_pipe_hint_benchmark.c"),
                        "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=30)

    def run_benchmark(self, *args):
        # Keep protocol tests on one permitted host CPU, including descendants.
        selected = min(os.sched_getaffinity(0))
        return subprocess.run([str(self.binary), *map(str, args)],
                              capture_output=True, text=True, timeout=10,
                              preexec_fn=lambda: os.sched_setaffinity(0, {selected}))

    def test_all_workloads_and_both_transports_finish_with_checked_results(self):
        for sync in ("pipe", "futex"):
            policies = ["continuous", "continuous-unmatched", "seed", "preseed"]
            if sync == "futex":
                policies += ["futex-early", "futex-early-both"]
            for workload in ("scan", "lookup", "parse", "chase"):
                for policy in policies:
                    with self.subTest(sync=sync, workload=workload, policy=policy):
                        run = self.run_benchmark(3, 2, policy, 2, sync,
                                                 "legs" if sync == "futex" else "plain",
                                                 32, workload)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        self.assertIn("Software protocol verification only", run.stderr)
                        self.assertIn("PIPE_HINT_HOST_VERIFY_PASS", run.stdout)
                        self.assertNotIn("PIPE_HINT_RESULT", run.stdout)
                        self.assertNotIn("PIPE_HINT_PASS", run.stdout)
                        self.assertIn(f"workload={workload} terminal_handshake=1", run.stdout)
                        rows = re.findall(
                            r"PIPE_HINT_HOST_VERIFY_RESULT repeat=(\d+) order=(\d+) "
                            r"enabled=([01]) cycles=(\d+) loops=3", run.stdout)
                        self.assertEqual(len(rows), 4)
                        self.assertEqual([int(row[2]) for row in rows], [0, 1, 1, 0])
                        self.assertTrue(all(int(row[3]) > 0 for row in rows))

    def test_zero_work_and_many_chase_epochs_complete(self):
        for sync in ("pipe", "futex"):
            for kib in (0, 3):
                run = self.run_benchmark(257, 1, "preseed", 3, sync, "plain", kib, "chase")
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("PIPE_HINT_HOST_VERIFY_PASS", run.stdout)

    def test_invalid_arguments_rejected_before_fork_or_result(self):
        cases = [
            [0], [1000001], ["junk"], [1, 0],
            [1, 1, "unknown"], [1, 1, "preseed", 0],
            [1, 1, "preseed", 1, "unknown"],
            [1, 1, "futex-early", 1, "pipe"],
            [1, 1, "futex-early-both", 1, "pipe"],
            [1, 1, "preseed", 1, "pipe", "legs"],
            [1, 1, "preseed", 1, "futex", "plain", ""],
            [1, 1, "preseed", 1, "futex", "plain", "-0"],
            [1, 1, "preseed", 1, "futex", "plain", 65537],
            [1, 1, "preseed", 1, "futex", "plain", 1, "unknown"],
            [1, 1, "preseed", 1, "futex", "plain", 1, "scan", "extra"],
        ]
        for args in cases:
            with self.subTest(args=args):
                run = self.run_benchmark(*args)
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertNotIn("CONFIG", run.stdout)
                self.assertNotIn("RESULT", run.stdout)


if __name__ == "__main__":
    unittest.main()
