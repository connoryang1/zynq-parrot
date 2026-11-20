"""Validate complete-cell resource telemetry using explicit parser fixtures.

These fixtures are not FPGA executions or performance observations.
"""
import json
from pathlib import Path
import tempfile
import unittest

from analyze_scheduler_pipe_hint import analyze, RESOURCE_FIELDS
from test_analyze_scheduler_retention import fixture


def resource_fixture(policy="preseed", capability=False, workload="lookup"):
    text, runner = fixture()
    runner.update(policy=policy, workload=workload)
    lines = []
    if workload == "deflate":
        lines.append("PIPE_HINT_LIBRARY name=zlib version=1.2.13 block_bytes=4096 input_corpus_kib=32")
        runner["zlib_library_sha256"] = "b" * 64
    for line in text.splitlines():
        line = line.replace("policy=retention-first", "policy=" + policy)
        line = line.replace("workload=lookup", "workload=" + workload)
        if line.startswith("PIPE_HINT_RETENTION"):
            if not capability:
                continue
            if policy == "preseed":
                enabled = int(line.split("enabled=")[1][0])
                raw = (1 << 63) | (7 << 16 if enabled else 0)
                line = (line.split(" raw=")[0] + f" raw=0x{raw:016x} capability=1 "
                        f"mode=0 completed=0 consumed_fetches={7 if enabled else 0}")
        if line.startswith("PIPE_HINT_STATUS") and policy == "preseed":
            before = 1 | (32 << 4)
            after = before | (32 << 13) | (128 << 22) | (4 << 38)
            line = (f"PIPE_HINT_STATUS before=0x{before:016x} after=0x{after:016x} "
                    "configured_entries=32 dropped=0")
        lines.append(line)
        if line.startswith("PIPE_HINT_RETENTION" if capability else "PIPE_HINT_WHOLE"):
            key = line.split(" ", 1)[1].split(" cycles=")[0].split(" raw=")[0]
            repeat = int(key.split("repeat=")[1].split()[0])
            counters = (100 + repeat, 0, 200000, 50000, 24, 3)
            lines.append("PIPE_HINT_RESOURCE " + key + " " + " ".join(
                f"{name}={value}" for name, value in zip(RESOURCE_FIELDS, counters)))
    return "\n".join(lines) + "\n", runner


class ResourceAnalyzerTests(unittest.TestCase):
    def parse(self, text, runner):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(text)
            log.with_suffix(".log.status.json").write_text(json.dumps(runner))
            return analyze(log, bootstrap_samples=100)

    def test_resource_only_and_capable_legacy_and_retention(self):
        for policy, capability in (("preseed", False), ("preseed", True),
                                   ("retention-first", True)):
            with self.subTest(policy=policy, capability=capability):
                text, runner = resource_fixture(policy, capability)
                result = self.parse(text, runner)
                self.assertEqual(result["config"]["resource_stats"], 1)
                self.assertEqual(len(result["resources"]["rows"]), 8)
                self.assertEqual(result["resources"]["rows"][0]["minor_faults"], 100)
                self.assertIn("not L1 cache-miss", result["resources"]["scope"])
                self.assertEqual(result["metrics"]["paired_median_saved_cycles_per_roundtrip"], 10)
                self.assertEqual(result["whole_cell"]["metrics"]["paired_median_saved_cycles_per_cell"], -500)
                self.assertEqual("retention_status" in result, capability)

    def test_real_library_header_is_bound_to_corpus(self):
        for policy, capable in (("preseed", False), ("retention-first", True)):
            text, runner = resource_fixture(policy, capable, "deflate")
            self.assertEqual(self.parse(text, runner)["library"]["block_bytes"], 4096)
            for bad in (text.replace("input_corpus_kib=32", "input_corpus_kib=64"),
                        text.replace("block_bytes=4096", "block_bytes=8192"),
                        "\n".join(text.splitlines()[1:]) + "\n"):
                with self.assertRaises(ValueError):
                    self.parse(bad, runner)

    def test_partial_duplicate_reordered_and_overflow_rows_fail(self):
        text, runner = resource_fixture()
        row = next(line for line in text.splitlines() if line.startswith("PIPE_HINT_RESOURCE"))
        for bad in (text.replace(row + "\n", "", 1),
                    text.replace(row, row + "\n" + row, 1),
                    text.replace(row, row.replace("order=0", "order=1"), 1),
                    text.replace("minor_faults=100", "minor_faults=-1", 1),
                    text.replace("minor_faults=100", f"minor_faults={1 << 64}", 1)):
            with self.assertRaises(ValueError):
                self.parse(bad, runner)


if __name__ == "__main__":
    unittest.main()
