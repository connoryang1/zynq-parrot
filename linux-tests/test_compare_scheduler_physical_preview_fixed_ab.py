"""Test strict comparison of joint and instruction-only fixed-arm effects."""

import copy
import unittest

from compare_scheduler_physical_preview_fixed_ab import compare


def analysis(timing, enabled_value, disabled_value):
    """Build a minimal structurally valid fixed-arm analysis."""
    identity = {
        "nbf_sha256": ("1" if timing == "wake-trigger" else "2") * 64,
        "transfer_sha256": ("3" if timing == "wake-trigger" else "4") * 64,
        "elf_sha256": ("5" if timing == "wake-trigger" else "6") * 64,
        "control_program_sha256": "7" * 64,
        "bitstream_sha256": "8" * 64,
    }
    replicates = []
    for order in ("enabled-disabled", "disabled-enabled"):
        run = {"order": order}
        for arm, value in (("enabled", enabled_value),
                           ("disabled", disabled_value)):
            run[arm] = {
                "trials": 512,
                "values": {
                    metric: [value] * 512
                    for metric in ("wake_to_entry", "load_cycles",
                                   "wake_to_load")
                },
            }
        run["median_difference_enabled_minus_disabled"] = {
            metric: enabled_value - disabled_value
            for metric in ("wake_to_entry", "load_cycles", "wake_to_load")
        }
        replicates.append(run)
    return {
        "identity": identity,
        "group": 7,
        "timing": timing,
        "mode": 6,
        "footprint": "target",
        "replicates": replicates,
    }


class FixedAbComparisonTests(unittest.TestCase):
    def test_constant_effect_difference(self):
        control = analysis("wake-trigger", 105, 100)
        candidate = analysis("wake-data", 97, 100)
        result = compare(control, candidate, 20, 20)
        metric = result["metrics"]["wake_to_load"]
        self.assertEqual(metric["instruction_only_enabled_minus_disabled"], 5)
        self.assertEqual(metric["joint_enabled_minus_disabled"], -3)
        self.assertEqual(metric["joint_minus_instruction_only"], -8)
        self.assertEqual(metric["iid_bootstrap"]["difference_ci95"], [-8, -8])
        self.assertEqual(
            metric["circular_block_bootstrap"]["difference_ci95"], [-8, -8]
        )
        self.assertNotIn("roundtrip", result["metrics"])

    def test_rejects_mismatched_bitstream(self):
        control = analysis("wake-trigger", 105, 100)
        candidate = analysis("wake-data", 97, 100)
        candidate["identity"]["bitstream_sha256"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "bitstream_sha256"):
            compare(control, candidate, 2, 2)

    def test_rejects_wrong_timing_and_incomplete_arm(self):
        control = analysis("wake-trigger", 105, 100)
        candidate = analysis("wake-data", 97, 100)
        wrong = copy.deepcopy(candidate)
        wrong["timing"] = "late"
        with self.assertRaisesRegex(ValueError, "timing"):
            compare(control, wrong, 2, 2)
        candidate["replicates"][0]["enabled"]["values"]["load_cycles"].pop()
        with self.assertRaisesRegex(ValueError, "512 load_cycles"):
            compare(control, candidate, 2, 2)


if __name__ == "__main__":
    unittest.main()
