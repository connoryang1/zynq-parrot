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
                "after=0xff802a0008020101 configured_entries=16 dropped=0\n"
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
            self.assertEqual(result["config"]["workload"], "scan")
            self.assertEqual(
                result["metrics"]["paired_median_saved_cycles_per_roundtrip"],
                15.0,
            )

    def test_binds_natural_workload_and_rejects_status_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            identity = "a" * 64
            runner = {
                "status": "PASS", "loops": 10, "repeats": 2,
                "working_set_kib": 32,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }
            status = log.with_suffix(".log.status.json")
            for workload in ("scan", "lookup", "parse", "chase"):
                with self.subTest(workload=workload):
                    log.write_text(
                        "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=32 configured_entries=16 "
                        f"policy=continuous sync=pipe profile=plain working_set_kib=32 workload={workload}\n"
                        "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                        "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                        "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                        "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                        "PIPE_HINT_STATUS before=0x0000000000000101 "
                        "after=0xff802a0008020101 configured_entries=16 dropped=0\n"
                        "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
                    )
                    runner["workload"] = workload
                    status.write_text(json.dumps(runner))
                    self.assertEqual(analyze(log, 10)["config"]["workload"], workload)
                    runner["workload"] = "parse" if workload != "parse" else "scan"
                    status.write_text(json.dumps(runner))
                    with self.assertRaisesRegex(ValueError, "workload differ"):
                        analyze(log, 10)
                    if workload != "scan":
                        del runner["workload"]
                        status.write_text(json.dumps(runner))
                        with self.assertRaisesRegex(ValueError, "workload differ"):
                            analyze(log, 10)

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

    def test_binds_seed_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=1 warmup=32 "
                "configured_entries=16 policy=seed\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0xff803fc020020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 1,
                "policy": "continuous", "nbf_sha256": identity,
                "transfer_sha256": identity, "elf_sha256": identity,
                "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            with self.assertRaisesRegex(ValueError, "policy differ"):
                analyze(log, bootstrap_samples=10)

    def test_accepts_exact_preseed_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=256 "
                "configured_entries=16 policy=preseed\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0x0000008008020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "warmup": 256, "policy": "preseed",
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(result["config"]["policy"], "preseed")

    def test_binds_futex_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=256 "
                "configured_entries=16 policy=preseed sync=futex\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0x0000008008020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "warmup": 256, "policy": "preseed", "sync": "futex",
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(result["config"]["sync"], "futex")
            self.assertIn("futex", result["purpose"])

    def test_binds_private_working_set(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=32 "
                "configured_entries=16 policy=continuous sync=pipe "
                "profile=plain working_set_kib=256\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0xff802a0008020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "working_set_kib": 256,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(result["config"]["working_set_kib"], 256)

    def test_binds_unmatched_continuous_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=32 "
                "configured_entries=16 policy=continuous-unmatched sync=pipe "
                "profile=plain working_set_kib=0\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0xff802a0008020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "policy": "continuous-unmatched",
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(result["config"]["policy"],
                             "continuous-unmatched")

    def test_binds_futex_early_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=32 "
                "configured_entries=16 policy=futex-early sync=futex "
                "profile=plain working_set_kib=32\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=900 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=1000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0xff80150008020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "warmup": 32, "policy": "futex-early", "sync": "futex",
                "working_set_kib": 32,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(result["config"]["policy"], "futex-early")

    def test_terminal_barrier_and_explicit_both_direction_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            status_path = log.with_suffix(".log.status.json")
            identity = "a" * 64
            for policy, triggers in (("futex-early", 86), ("futex-early-both", 170)):
                with self.subTest(policy=policy):
                    after = (1 | (16 << 4) | (16 << 13) | (32 << 22)
                             | (triggers << 38) | (511 << 55))
                    log.write_text(
                        "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=32 configured_entries=16 "
                        f"policy={policy} sync=futex profile=plain working_set_kib=32 "
                        "workload=lookup terminal_handshake=1\n"
                        + "".join(
                            f"PIPE_HINT_RESULT repeat={repeat} order={order} "
                            f"enabled={(repeat & 1) ^ order} cycles=1000 loops=10\n"
                            for repeat in range(2) for order in range(2))
                        + f"PIPE_HINT_STATUS before=0x0000000000000101 after=0x{after:016x} "
                        "configured_entries=16 dropped=0\nPIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
                    )
                    runner = {
                        "status": "PASS", "loops": 10, "repeats": 2,
                        "warmup": 32, "policy": policy, "sync": "futex",
                        "working_set_kib": 32, "workload": "lookup", "terminal_handshake": 1,
                        "nbf_sha256": identity, "transfer_sha256": identity,
                        "elf_sha256": identity, "control_program_sha256": identity,
                        "bitstream_sha256": identity,
                    }
                    status_path.write_text(json.dumps(runner))
                    parsed = analyze(log, 10)
                    self.assertEqual(parsed["config"]["terminal_handshake"], 1)
                    self.assertEqual(parsed["icache_prefix_status"]["after"]["accepted_triggers"], triggers)
                    runner["terminal_handshake"] = 0
                    status_path.write_text(json.dumps(runner))
                    with self.assertRaisesRegex(ValueError, "terminal handshake differ"):
                        analyze(log, 10)

    def test_futex_early_accepts_whole_table_reload_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            # 0x140 accepted entries is ten complete 32-line table loads.
            # Residency/invalidation can change reload count independently of
            # raw trigger count, whose telemetry may saturate in this mode.
            log.write_text(
                "PIPE_HINT_CONFIG loops=128 repeats=4 warmup=64 "
                "configured_entries=32 policy=futex-early sync=futex "
                "profile=plain working_set_kib=32\n"
                + "".join(
                    f"PIPE_HINT_RESULT repeat={repeat} order={order} "
                    f"enabled={(repeat & 1) ^ order} cycles={1000 - 10 * ((repeat & 1) ^ order)} loops=128\n"
                    for repeat in range(4) for order in range(2)
                )
                + "PIPE_HINT_STATUS before=0x0000000000000201 "
                "after=0xff803fc050040201 configured_entries=32 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 128, "repeats": 4,
                "warmup": 64, "policy": "futex-early", "sync": "futex",
                "working_set_kib": 32,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(
                result["icache_prefix_status"]["after"]["accepted_entries"],
                320,
            )

    def test_unsaturated_mode14_uses_actual_sweeps_not_wake_only_equality(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            identity = "a" * 64
            runner = {
                "status": "PASS", "loops": 1, "repeats": 2, "warmup": 1,
                "policy": "futex-early", "sync": "futex", "terminal_handshake": 1,
                "nbf_sha256": identity, "transfer_sha256": identity,
                "elf_sha256": identity, "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }
            log.with_suffix(".log.status.json").write_text(json.dumps(runner))

            def write(triggers, resident, admitted=32):
                # Six explicit parent wakes are known. Additional selections
                # are kernel/schedule dependent. Two fresh cells admit 32 lines.
                after = (1 | (16 << 4) | (16 << 13) | (admitted << 22)
                         | (triggers << 38) | (resident << 55))
                log.write_text(
                    "PIPE_HINT_CONFIG loops=1 repeats=2 warmup=1 configured_entries=16 "
                    "policy=futex-early sync=futex terminal_handshake=1\n"
                    + "".join(
                        f"PIPE_HINT_RESULT repeat={repeat} order={order} "
                        f"enabled={(repeat & 1) ^ order} cycles=1000 loops=1\n"
                        for repeat in range(2) for order in range(2))
                    + f"PIPE_HINT_STATUS before=0x0000000000000101 after=0x{after:016x} "
                    "configured_entries=16 dropped=0\nPIPE_HINT_PASS\nCORE PASS\nBSG PASS\n")

            # The third case re-admits one evicted line. Entry admission is
            # per line; divisibility by the configured table size is unjustified.
            for triggers, admitted in ((6, 32), (10, 32), (10, 33), (13, 32)):
                with self.subTest(triggers=triggers, admitted=admitted):
                    write(triggers, triggers * 16 - admitted, admitted)
                    result = analyze(log, 10)
                    self.assertEqual(result["trigger_accounting"]["early_wake_opportunities"], 6)
                    self.assertFalse(result["trigger_accounting"]["accepted_triggers_saturated"])
                    self.assertTrue(any("combined-policy" in text
                                        for text in result["interpretation_limits"]))
            for triggers, resident, admitted in ((5, 48, 32), (10, 64, 32),
                                                  (6, 511, 32), (6, 65, 31)):
                with self.subTest(invalid=(triggers, resident, admitted)):
                    write(triggers, resident, admitted)
                    with self.assertRaisesRegex(ValueError, "did not drain cleanly"):
                        analyze(log, 10)

    def test_profiles_two_resume_legs(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            log.write_text(
                "PIPE_HINT_CONFIG loops=10 repeats=2 warmup=256 "
                "configured_entries=16 policy=preseed sync=futex profile=legs\n"
                "PIPE_HINT_RESULT repeat=0 order=0 enabled=0 cycles=10000 loops=10\n"
                "PIPE_HINT_LEGS repeat=0 order=0 enabled=0 child_resume=4000 parent_resume=3000 loops=10\n"
                "PIPE_HINT_RESULT repeat=0 order=1 enabled=1 cycles=9000 loops=10\n"
                "PIPE_HINT_LEGS repeat=0 order=1 enabled=1 child_resume=3500 parent_resume=2800 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=0 enabled=1 cycles=8000 loops=10\n"
                "PIPE_HINT_LEGS repeat=1 order=0 enabled=1 child_resume=3000 parent_resume=2500 loops=10\n"
                "PIPE_HINT_RESULT repeat=1 order=1 enabled=0 cycles=10000 loops=10\n"
                "PIPE_HINT_LEGS repeat=1 order=1 enabled=0 child_resume=4000 parent_resume=3000 loops=10\n"
                "PIPE_HINT_STATUS before=0x0000000000000101 "
                "after=0x0000008008020101 configured_entries=16 dropped=0\n"
                "PIPE_HINT_PASS\nCORE PASS\nBSG PASS\n"
            )
            identity = "a" * 64
            log.with_suffix(".log.status.json").write_text(json.dumps({
                "status": "PASS", "loops": 10, "repeats": 2,
                "warmup": 256, "policy": "preseed", "sync": "futex",
                "profile": "legs", "nbf_sha256": identity,
                "transfer_sha256": identity, "elf_sha256": identity,
                "control_program_sha256": identity,
                "bitstream_sha256": identity,
            }))
            result = analyze(log, bootstrap_samples=10)
            self.assertEqual(result["config"]["profile"], "legs")
            self.assertEqual(
                result["metrics"][
                    "paired_median_saved_combined_resume_cycles_per_roundtrip"],
                110.0,
            )
            self.assertEqual(
                result["metrics"][
                    "paired_median_saved_unattributed_cycles_per_roundtrip"],
                40.0,
            )


if __name__ == "__main__":
    unittest.main()
