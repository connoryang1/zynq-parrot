#!/usr/bin/env python3
"""Test strict sustained pipe-hint result parsing and paired effects."""

import json
from pathlib import Path
import tempfile
import unittest

from analyze_scheduler_pipe_hint import analyze


class PipeHintAnalyzerTests(unittest.TestCase):
    def test_balanced_pairs_and_controller_drain(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=32 configured_entries=16\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0xff803fc020020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nINFO:    CORE PASS\nINFO:    BSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=100)
            self.assertEqual(
                result["metrics"]["paired_median_saved_cycles_per_roundtrip"],
                15.0,
            )

    def test_rejects_unbalanced_order(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=1 warmup=32 configured_entries=16\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0xff803fc020020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 1,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            with self.assertRaisesRegex(ValueError, "does not alternate"):
                analyze(log, bootstrap_samples=10)


if __name__ == "__main__":
    unittest.main()
