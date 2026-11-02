"""Test strict one-versus-four-line fixed-arm effect comparison."""

import copy
import unittest

from compare_scheduler_physical_preview_line_count_fixed_ab import compare


def analysis(lines, enabled_value, disabled_value):
    """Build a minimal complete strict-analysis-shaped fixture."""
    metrics = (
        "wake_to_entry", "load_cycles", "wake_to_load", "roundtrip",
        "child_post_load", "return_handoff",
    )
    replicates = []
    for order in ("enabled-disabled", "disabled-enabled"):
        values = {
            "enabled": {metric: [enabled_value] * 512 for metric in metrics},
            "disabled": {metric: [disabled_value] * 512 for metric in metrics},
        }
        replicates.append({
            "order": order,
            "enabled": {"trials": 512, "values": values["enabled"]},
            "disabled": {"trials": 512, "values": values["disabled"]},
            "median_difference_enabled_minus_disabled": {
                metric: enabled_value - disabled_value for metric in metrics
            },
        })
    return {
        "timing": "wake-early-data",
        "mode": 1,
        "footprint": "target",
        "lines": lines,
        "group": 7,
        "identity": {
            "nbf_sha256": "1" * 64,
            "transfer_sha256": "2" * 64,
            "elf_sha256": "3" * 64,
            "control_program_sha256": "4" * 64,
            "bitstream_sha256": "5" * 64,
        },
        "replicates": replicates,
    }


class LineCountComparisonTest(unittest.TestCase):
    def test_known_four_minus_one_effect(self):
        one = analysis(1, 90, 100)
        four = analysis(4, 70, 100)
        result = compare(one, four, 10, 10)
        metric = result["metrics"]["load_cycles"]
        self.assertEqual(metric["one_line_enabled_minus_disabled"], -10)
        self.assertEqual(metric["four_line_enabled_minus_disabled"], -30)
        self.assertEqual(metric["four_minus_one"], -20)
        self.assertEqual(metric["circular_block_bootstrap"]["difference_ci95"],
                         [-20, -20])

    def test_rejects_wrong_shape_and_identity(self):
        one = analysis(1, 90, 100)
        four = analysis(4, 70, 100)
        wrong = copy.deepcopy(four)
        wrong["lines"] = 3
        with self.assertRaisesRegex(ValueError, "lines=4"):
            compare(one, wrong, 10, 10)
        wrong = copy.deepcopy(four)
        wrong["identity"]["bitstream_sha256"] = "6" * 64
        with self.assertRaisesRegex(ValueError, "bitstream_sha256"):
            compare(one, wrong, 10, 10)


if __name__ == "__main__":
    unittest.main()
