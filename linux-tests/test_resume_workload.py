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
import zlib

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


def record_corpus(kib, seed):
    """Independent parse-generator corpus, including its unused zero tail."""
    corpus = bytearray(kib * 1024)
    offset = number = 0
    while True:
        random = mix(seed + number)
        key = 1 + random % 1000000
        length = 16 + (random >> 24) % 97
        payload = bytes(97 + ((random + j * 7) & MASK) % 26
                        for j in range(length))
        record = str(key).encode() + b":" + payload + b"\n"
        if offset + len(record) + 1 > len(corpus):
            break
        corpus[offset:offset + len(record)] = record
        offset += len(record)
        number += 1
    return bytes(corpus), offset


ZLIB_DRIVER = r'''
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include "resume_workload.h"

static int fault;
static unsigned compress_calls, uncompress_calls;
static uLong request_bytes;
int __real_compress2(Bytef *, uLongf *, const Bytef *, uLong, int);
int __real_uncompress(Bytef *, uLongf *, const Bytef *, uLong);
int __wrap_compress2(Bytef *out, uLongf *out_bytes,
                     const Bytef *in, uLong in_bytes, int level)
{
    ++compress_calls;
    request_bytes = in_bytes;
    assert(level == Z_DEFAULT_COMPRESSION);
    if (fault == 1) return Z_STREAM_ERROR;
    if (fault == 2) return Z_MEM_ERROR;
    int result = __real_compress2(out, out_bytes, in, in_bytes, level);
    if (fault == 3 && result == Z_OK) out[0] ^= 0xff;
    return result;
}
int __wrap_uncompress(Bytef *out, uLongf *out_bytes,
                      const Bytef *in, uLong in_bytes)
{
    ++uncompress_calls;
    if (fault == 4) return Z_DATA_ERROR;
    int result = __real_uncompress(out, out_bytes, in, in_bytes);
    if (result == Z_OK && fault == 5) --*out_bytes;
    if (result == Z_OK && fault == 6) out[0] ^= 1;
    return result;
}
int main(int argc, char **argv)
{
    struct resume_workload w;
    uint64_t seed, total = 0, ideal_total = 0;
    unsigned kib, epochs;
    const char *action;
    if (argc != 5) return 2;
    kib = strtoul(argv[1], NULL, 0);
    seed = strtoull(argv[2], NULL, 0);
    action = argv[3];
    epochs = strtoul(argv[4], NULL, 0);
    if (resume_workload_init(&w, "deflate", kib, seed)) return 3;
    assert(resume_workload_check_total(&w, 0));
    printf("META %zu %zu %zu %zu\n", w.bytes, w.count,
           w.zlib_blocks, w.zlib_compressed_capacity);
    if (!strcmp(action, "input-corrupt") || !strcmp(action, "last-corrupt")) {
        if (!w.bytes) return 4;
        w.data[!strcmp(action, "last-corrupt") ? w.bytes - 1 : 0] ^= 1;
    } else if (!strcmp(action, "compress-error")) fault = 1;
    else if (!strcmp(action, "memory-error")) fault = 2;
    else if (!strcmp(action, "compressed-corrupt")) fault = 3;
    else if (!strcmp(action, "uncompress-error")) fault = 4;
    else if (!strcmp(action, "short-output")) fault = 5;
    else if (!strcmp(action, "output-corrupt")) fault = 6;
    else assert(!strcmp(action, "run"));
    for (unsigned epoch = 0; epoch < epochs; ++epoch) {
        uint64_t expected = resume_workload_expected(&w, epoch);
        uint64_t result = resume_workload_run(&w);
        ideal_total += expected;
        total += result;
        if (fault && fault != 6) {
            assert(result == UINT64_MAX && w.zlib_error != Z_OK);
            assert(!resume_workload_check(&w, result));
            /* Even a forged matching total must fail after a library error. */
            assert(!resume_workload_check_total(&w, ideal_total));
        } else {
            int damaged = fault == 6 ||
                (!strcmp(action, "input-corrupt") && epoch % w.zlib_blocks == 0) ||
                (!strcmp(action, "last-corrupt") &&
                 epoch % w.zlib_blocks == w.zlib_blocks - 1);
            assert(resume_workload_check(&w, result) == !damaged);
            assert(w.zlib_error == Z_OK);
        }
        printf("ROW %u %lu %" PRIu64 "\n", epoch, request_bytes, result);
    }
    if (!strcmp(action, "run")) {
        assert(resume_workload_check_total(&w, total));
        assert(!resume_workload_check_total(&w, total + 1));
        assert(compress_calls == (w.bytes ? epochs : 0));
        assert(uncompress_calls == compress_calls);
        if (w.bytes) assert(w.cursor == epochs % w.zlib_blocks);
    } else assert(!resume_workload_check_total(&w, total));
    printf("TOTAL %" PRIu64 "\n", total);
    resume_workload_free(&w);
    assert(!w.data && !w.bytes && !w.runs && !w.zlib_compressed
           && !w.zlib_output && !w.zlib_expected_crc && !w.zlib_blocks);
    return 0;
}
'''


class ResumeZlibWorkloadTests(unittest.TestCase):
    """Use the real host libz; wrap only explicit failure-injection boundaries."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="resume-zlib-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "driver.c"
        source.write_text(ZLIB_DRIVER)
        cls.binary = source.with_suffix("")
        subprocess.run([os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-O2",
                        "-Wall", "-Wextra", "-Werror", "-DBP_RESUME_ZLIB=1",
                        "-I", str(HERE), str(source), "-lz",
                        "-Wl,--wrap=compress2", "-Wl,--wrap=uncompress",
                        "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=30)

    def run_workload(self, kib, seed, action="run", epochs=17):
        return subprocess.run([str(self.binary), str(kib), str(seed), action, str(epochs)],
                              capture_output=True, text=True, timeout=30)

    def test_real_library_requests_match_pristine_python_block_crcs(self):
        for kib in (0, 1, 3, 4, 5, 7, 32, 257):
            for seed in (0, 0x1234, MASK):
                with self.subTest(kib=kib, seed=seed):
                    epochs = max(17, (kib + 3) // 4 + 2)
                    run = self.run_workload(kib, seed, epochs=epochs)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    corpus, record_bytes = record_corpus(kib, seed)
                    blocks = [corpus[i:i + 4096] for i in range(0, len(corpus), 4096)]
                    rows = re.findall(r"^ROW (\d+) (\d+) (\d+)$", run.stdout, re.M)
                    self.assertEqual(len(rows), epochs)
                    expected_total = 0
                    for epoch, size, observed in map(lambda row: map(int, row), rows):
                        block = blocks[epoch % len(blocks)] if blocks else b""
                        expected = zlib.crc32(block)
                        self.assertEqual(size, len(block))
                        self.assertEqual(observed, expected)
                        expected_total += expected
                    metadata = re.search(r"^META (\d+) (\d+) (\d+) (\d+)$", run.stdout, re.M)
                    size, records, count, scratch = map(int, metadata.groups())
                    self.assertEqual((size, records, count), (len(corpus), record_bytes, len(blocks)))
                    self.assertGreater(scratch, 4096) if blocks else self.assertEqual(scratch, 0)
                    self.assertIn(f"TOTAL {expected_total}\n", run.stdout)

    def test_rotating_requests_change_blocks_and_wrap(self):
        run = self.run_workload(5, 0x1234, epochs=9)
        self.assertEqual(run.returncode, 0, run.stderr)
        rows = re.findall(r"^ROW \d+ (\d+) (\d+)$", run.stdout, re.M)
        self.assertEqual([int(row[0]) for row in rows], [4096, 1024] * 4 + [4096])
        self.assertEqual(rows[0], rows[2])
        self.assertNotEqual(rows[0][1], rows[1][1])

    def test_input_and_output_corruption_are_rejected(self):
        for action in ("input-corrupt", "last-corrupt", "output-corrupt"):
            with self.subTest(action=action):
                run = self.run_workload(5, 1234, action, epochs=5)
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_library_errors_and_wrong_output_lengths_are_sticky_failures(self):
        for action in ("compress-error", "memory-error", "compressed-corrupt",
                       "uncompress-error", "short-output"):
            with self.subTest(action=action):
                run = self.run_workload(5, 1234, action, epochs=3)
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_zero_flag_excludes_optional_fields_code_and_library(self):
        source = Path(self.temp.name) / "plain.c"
        source.write_text(DRIVER)
        command = [os.environ.get("BP_HOST_CC", "cc"), "-std=c11", "-E", "-P",
                   "-I", str(HERE), str(source)]
        plain = subprocess.run(command, check=True, capture_output=True, timeout=30).stdout
        disabled = subprocess.run(command + ["-DBP_RESUME_ZLIB=0"],
                                  check=True, capture_output=True, timeout=30).stdout
        self.assertEqual(plain, disabled)
        self.assertNotIn(b'"deflate"', plain)
        self.assertNotIn(b"zlib_expected_crc", plain)


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

    def test_deflate_is_absent_from_plain_build(self):
        run = self.run_workload("deflate", 32, 1)
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
