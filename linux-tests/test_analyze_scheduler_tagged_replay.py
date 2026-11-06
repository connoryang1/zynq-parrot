"""Test strict analysis of the tagged Linux replay benchmark."""

import json
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_tagged_replay import analyze
from compare_scheduler_tagged_replay_routes import compare
from pool_scheduler_tagged_replay_replicates import pool


def write_run(root, corrupt_counter=False, lines=32, probe_status=False,
              downstream_status=False, status_bits_59_58=False,
              layout="aligned", mode="data", sync="pipe",
              enabled_load=280, bitstream_sha256="5" * 64,
              prefix_entries=16):
    """Create a complete synthetic matched A/B transcript and status."""
    kernel_modes = {
        "off": 0, "data": 9, "data-late": 11,
        "instruction-select": 3, "instruction-wake": 13, "joint": 10,
        "joint-split": 12, "joint-split-one-hook": 12,
        "joint-follow-only": 12,
    }
    expected_hooks = 1
    path = root / "run.log"
    rows = [
        f"TAGGED_REPLAY_CONFIG mode={mode} lines={lines} slot=2 delay=0 gap=2 "
        f"policy=fifo lead_cycles=0 layout={layout} "
        f"probe_status={int(probe_status)} sync={sync} "
        f"kernel_mode={kernel_modes[mode]} expected_hooks={expected_hooks}"
    ]
    if mode == "instruction-wake":
        before = (prefix_entries << 4) | 1
        after = ((0x1ff << 55) | (0xff << 38) | (prefix_entries << 13)
                 | (prefix_entries << 4) | 1)
        rows.append(
            f"TAGGED_REPLAY_ICACHE_STATUS before=0x{before:016x} "
            f"after=0x{after:016x}"
        )
    for trial in range(512):
        enabled = (0 if mode == "off" else
                   ((trial ^ (trial >> 1)) & 1) ^ ((trial >> 2) & 1))
        expects_trigger = mode not in (
            "off", "instruction-select", "instruction-wake"
        )
        admitted = (lines if enabled and expects_trigger
                    and mode != "joint-follow-only" else 0)
        triggers = enabled if expects_trigger else 0
        if corrupt_counter and trial == 4:
            admitted -= 1
        entry = 100 + trial % 3
        load = enabled_load if enabled else 300
        preblock = ((1 << 42) | (admitted << 10)) \
            if probe_status and enabled else 0
        entry_status = preblock
        if probe_status and enabled and downstream_status:
            preblock |= (2 << 60) | (1 << 63)
            entry_status |= 1 << 60
        if probe_status and enabled and status_bits_59_58:
            preblock |= 3 << 58
            entry_status |= 2 << 58
        rows.append(
            f"TAGGED_REPLAY trial={trial} enabled={enabled} "
            f"hooks={enabled * expected_hooks} woken=1 "
            f"hook_cycles={10 + enabled} admitted={admitted} filtered=0 "
            f"triggers={triggers} dropped=0 wake_to_entry={entry} "
            f"load_cycles={load} wake_to_load={entry + load} "
            f"roundtrip={entry + load + 40} "
            f"preblock_status=0x{preblock:016x} "
            f"preblock_probe_cycles={30 if probe_status else 0} "
            f"entry_probe_status=0x{entry_status:016x} "
            f"entry_probe_cycles={32 if probe_status else 0}"
        )
    rows.extend((
        "TAGGED_REPLAY_CHILD PASS retries=0",
        "TAGGED_REPLAY_PARENT PASS",
        "CORE[0] PASS",
        "BSG PASS",
    ))
    path.write_text("\n".join(rows) + "\n")
    status = {
        "status": "PASS",
        "nbf_sha256": "1" * 64,
        "transfer_sha256": "2" * 64,
        "elf_sha256": "3" * 64,
        "control_program_sha256": "4" * 64,
        "bitstream_sha256": bitstream_sha256,
        "mode": mode,
        "delay": 0,
        "gap": 2,
        "policy": "fifo",
        "lead_cycles": 0,
        "lines_per_base": lines // 4,
        "probe_status": probe_status,
        "layout": layout,
        "sync": sync,
    }
    path.with_suffix(".log.status.json").write_text(json.dumps(status) + "\n")
    return path


class TaggedReplayAnalyzerTest(unittest.TestCase):
    def test_known_effect_and_complete_counters_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(write_run(Path(directory)), bootstrap_samples=100)
        self.assertEqual(result["trials_per_arm"], 256)
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 256)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 8192)
        self.assertEqual(
            result["metrics"]["load_cycles"]["paired_median_saved_cycles"], 20
        )

    def test_incomplete_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), corrupt_counter=True)
            with self.assertRaisesRegex(ValueError, "did not complete all replay entries"):
                analyze(path, bootstrap_samples=10)

    def test_reduced_footprint_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16), bootstrap_samples=10
            )
        self.assertEqual(result["config"]["lines"], 16)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 4096)

    def test_skew_layout_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), layout="skew"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["layout"], "skew")

    def test_late_data_mode_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="data-late"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "data-late")

    def test_instruction_selection_mode_has_no_data_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="instruction-select"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "instruction-select")
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 0)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 0)

    def test_instruction_wakeup_mode_has_no_data_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="instruction-wake"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "instruction-wake")
        self.assertEqual(result["config"]["kernel_mode"], 13)
        self.assertEqual(result["config"]["expected_hooks"], 1)
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 0)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 0)
        self.assertEqual(
            result["icache_prefix_status"]["after"]["accepted_triggers"], 255
        )
        self.assertEqual(
            result["icache_prefix_status"]["after"]["resident_drops"], 511
        )

    def test_instruction_wakeup_requires_prefix_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), mode="instruction-wake")
            path.write_text("\n".join(
                line for line in path.read_text().splitlines()
                if not line.startswith("TAGGED_REPLAY_ICACHE_STATUS ")
            ) + "\n")
            with self.assertRaisesRegex(ValueError, "I-cache status marker"):
                analyze(path, bootstrap_samples=10)

    def test_instruction_wakeup_accepts_image_bound_prefix_count(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(
                    Path(directory), mode="instruction-wake", prefix_entries=3
                ),
                bootstrap_samples=10,
            )
        self.assertEqual(
            result["icache_prefix_status"]["before"]["configured_entries"], 3
        )
        self.assertEqual(
            result["icache_prefix_status"]["after"]["next_index"], 3
        )

    def test_instruction_wakeup_rejects_changed_prefix_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(
                Path(directory), mode="instruction-wake", prefix_entries=3
            )
            text = path.read_text()
            old_after = ((0x1ff << 55) | (0xff << 38) | (3 << 13)
                         | (3 << 4) | 1)
            changed_after = ((0x1ff << 55) | (0xff << 38) | (4 << 13)
                             | (4 << 4) | 1)
            path.write_text(text.replace(
                f"after=0x{old_after:016x}", f"after=0x{changed_after:016x}"
            ))
            with self.assertRaisesRegex(ValueError, "did not drain cleanly"):
                analyze(path, bootstrap_samples=10)

    def test_counter_only_mode_four_cannot_be_labeled_instruction_wakeup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), mode="instruction-wake")
            text = path.read_text().replace("kernel_mode=13", "kernel_mode=4")
            path.write_text(text)
            with self.assertRaisesRegex(ValueError, "kernel mode"):
                analyze(path, bootstrap_samples=10)

    def test_split_joint_mode_requires_data_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="joint-split"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "joint-split")
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 256)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 8192)

    def test_split_joint_mode_requires_one_hardware_command_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), mode="joint-split")
            path.write_text(path.read_text().replace(
                "enabled=1 hooks=1", "enabled=1 hooks=2", 1
            ))
            with self.assertRaisesRegex(ValueError, "invalid hook count"):
                analyze(path, bootstrap_samples=10)

    def test_split_joint_one_hook_diagnostic_keeps_data_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="joint-split-one-hook"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "joint-split-one-hook")
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 256)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 8192)

    def test_joint_follow_only_accepts_tags_without_data_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="joint-follow-only"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "joint-follow-only")
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 256)
        self.assertEqual(result["counter_deltas"]["admitted_entries"], 0)

    def test_futex_sync_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), sync="futex"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["sync"], "futex")

    def test_replay_off_stability_run_has_no_ab_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), mode="off", sync="futex"),
                bootstrap_samples=10,
            )
        self.assertEqual(result["config"]["mode"], "off")
        self.assertEqual(result["trials_per_arm"], 512)
        self.assertEqual(result["counter_deltas"]["accepted_triggers"], 0)
        self.assertEqual(result["metrics"]["load_cycles"]["median_cycles"], 300)

    def test_timer_callback_guard_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            path.write_text(
                path.read_text()
                + "BP_REPLAY_TIMER_GUARD handler=0x2 replay_status=0x0\n"
            )
            with self.assertRaisesRegex(ValueError, "BP_REPLAY_TIMER_GUARD"):
                analyze(path, bootstrap_samples=10)

    def test_nonwaking_futex_trial_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), sync="futex")
            text = path.read_text().replace("hooks=0 woken=1", "hooks=0 woken=0", 1)
            path.write_text(text)
            with self.assertRaisesRegex(ValueError, "did not wake exactly one child"):
                analyze(path, bootstrap_samples=10)

    def test_status_sync_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory), sync="futex")
            status_path = path.with_suffix(".log.status.json")
            status = json.loads(status_path.read_text())
            status["sync"] = "pipe"
            status_path.write_text(json.dumps(status) + "\n")
            with self.assertRaisesRegex(ValueError, "status sync"):
                analyze(path, bootstrap_samples=10)

    def test_two_valid_replicates_pool_paired_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first").mkdir()
            (root / "second").mkdir()
            first = write_run(root / "first")
            second = write_run(root / "second")
            result = pool([first, second], bootstrap_samples=10)
        self.assertEqual(result["replicate_count"], 2)
        self.assertEqual(
            result["metrics"]["load_cycles"]["pooled_saved_cycles"], 20
        )
        self.assertAlmostEqual(
            result["metrics"]["load_cycles"]["pooled_saved_percent"],
            100.0 * 20 / 300,
        )

    def test_distinct_routes_compare_incremental_block_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "control").mkdir()
            (root / "candidate").mkdir()
            control = write_run(root / "control", bitstream_sha256="5" * 64)
            candidate = write_run(
                root / "candidate", enabled_load=260,
                bitstream_sha256="6" * 64,
            )
            result = compare(control, candidate, bootstrap_samples=10)
        self.assertEqual(
            result["metrics"]["load_cycles"]
                  ["candidate_incremental_saved_cycles"],
            20,
        )

    def test_route_comparison_pools_independent_boots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name, enabled_load, bit in (
                    ("control1", 280, "5"), ("control2", 280, "5"),
                    ("candidate1", 260, "6"), ("candidate2", 260, "6")):
                (root / name).mkdir()
                paths.append(write_run(
                    root / name, enabled_load=enabled_load,
                    bitstream_sha256=bit * 64,
                ))
            result = compare(paths[:2], paths[2:], bootstrap_samples=10)
        self.assertEqual(len(result["control"]["transcripts"]), 2)
        self.assertEqual(len(result["candidate"]["transcripts"]), 2)
        self.assertEqual(
            result["metrics"]["load_cycles"]
                  ["candidate_incremental_saved_cycles"],
            20,
        )

    def test_preblock_probe_is_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16, probe_status=True),
                bootstrap_samples=10,
            )
        self.assertEqual(result["preblock_probe"]["enabled_busy_trials"], 0)
        self.assertEqual(result["preblock_probe"]["enabled_admitted_median"], 16)
        self.assertEqual(result["preblock_probe"]["entry_admitted_median"], 16)

    def test_downstream_uce_status_is_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16, probe_status=True,
                          downstream_status=True),
                bootstrap_samples=10,
            )
        probe = result["preblock_probe"]
        self.assertEqual(probe["uce_outstanding_histogram"]["enabled"], {"2": 256})
        self.assertEqual(probe["uce_complete_histogram"]["enabled"], {"1": 256})
        self.assertEqual(
            probe["entry_uce_outstanding_histogram"]["enabled"], {"1": 256}
        )
        self.assertEqual(
            probe["entry_uce_complete_histogram"]["enabled"], {"0": 256}
        )

    def test_status_bits_59_58_are_reported_neutrally(self):
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                write_run(Path(directory), lines=16, probe_status=True,
                          status_bits_59_58=True),
                bootstrap_samples=10,
            )
        probe = result["preblock_probe"]
        self.assertEqual(
            probe["status_bits_59_58_histogram"]["enabled"], {"3": 256}
        )
        self.assertEqual(
            probe["entry_status_bits_59_58_histogram"]["enabled"], {"2": 256}
        )

    def test_status_parameter_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            status_path = path.with_suffix(".log.status.json")
            status = json.loads(status_path.read_text())
            status["gap"] = 3
            status_path.write_text(json.dumps(status) + "\n")
            with self.assertRaisesRegex(ValueError, "status gap"):
                analyze(path, bootstrap_samples=10)

    def test_rt_throttling_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            path.write_text(path.read_text() + "sched: RT throttling activated\n")
            with self.assertRaisesRegex(ValueError, "RT throttling activated"):
                analyze(path, bootstrap_samples=10)

    def test_unhandled_userspace_signal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(Path(directory))
            path.write_text(
                path.read_text()
                + "scheduler_tagge[41]: unhandled signal 11 code 0x2\n"
            )
            with self.assertRaisesRegex(ValueError, "unhandled signal"):
                analyze(path, bootstrap_samples=10)


if __name__ == "__main__":
    unittest.main()
