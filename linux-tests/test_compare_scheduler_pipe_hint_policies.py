#!/usr/bin/env python3
"""Test exact-identity comparison of sustained pipe-hint policies."""

import unittest
from pathlib import Path
import json
import tempfile
from unittest import mock

from compare_scheduler_pipe_hint_policies import compare, main


def result(policy, identity, effects):
    return {
        "config": {"loops": 10, "repeats": 2, "warmup": 32,
                   "configured_entries": 16, "policy": policy},
        "identity": {"elf_sha256": identity},
        "pairs": [
            {"saved_cycles_per_roundtrip": cycles,
             "saved_percent": percent}
            for cycles, percent in effects
        ],
    }


class PipeHintPolicyComparatorTests(unittest.TestCase):
    def deployment_results(self, baseline_policy, comparison_policy):
        samples = [result(baseline_policy, "same", [(10.0, 1.0)]),
                   result(baseline_policy, "same", [(20.0, 2.0)]),
                   result(comparison_policy, "same", [(40.0, 4.0)]),
                   result(comparison_policy, "same", [(50.0, 5.0)])]
        for sample in samples:
            sample["config"].update(workload="lookup", working_set_kib=32,
                                    terminal_handshake=1, sync="futex")
            sample["identity"].update(nbf_sha256="same-nbf", bitstream_sha256="same-bitstream")
        return samples

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_compares_parent_with_explicit_both_direction_registration(self, analyze):
        analyze.side_effect = self.deployment_results("futex-early", "futex-early-both")
        output = compare([Path("p1"), Path("p2")], [Path("b1"), Path("b2")], 100,
                         baseline_policy="futex-early", comparison_policy="futex-early-both")
        self.assertEqual(output["comparison_policy"], "futex-early-both")
        self.assertEqual(output["comparison_minus_baseline"]["saved_cycles_per_roundtrip"], 30.0)
        self.assertEqual(output["comparison_minus_baseline"]["saved_percentage_points"], 3.0)
        self.assertEqual(output["config"]["terminal_handshake"], 1)
        self.assertIn("futex-early-both over futex-early", output["purpose"])
        self.assertNotIn("continuous_minus_baseline", output)
        self.assertNotIn("continuous_replicates", output)

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_compares_retained_preseed_with_deployment_early_refresh(self, analyze):
        for policy in ("futex-early", "futex-early-both"):
            with self.subTest(policy=policy):
                analyze.side_effect = self.deployment_results("preseed", policy)
                output = compare([Path("s1"), Path("s2")], [Path("r1"), Path("r2")], 10,
                                 baseline_policy="preseed", comparison_policy=policy)
                self.assertEqual(output["baseline_policy"], "preseed")
                self.assertEqual(output["comparison_minus_baseline"]["saved_cycles_per_roundtrip"], 30.0)
                self.assertNotIn("continuous_minus_baseline", output)

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_new_policies_reject_workload_endpoint_and_footprint_changes(self, analyze):
        for field, value in (("workload", "parse"), ("terminal_handshake", 0),
                             ("working_set_kib", 256), ("warmup", 64)):
            with self.subTest(field=field):
                samples = self.deployment_results("futex-early", "futex-early-both")
                samples[-1]["config"][field] = value
                analyze.side_effect = samples
                with self.assertRaisesRegex(ValueError, "configuration mismatch"):
                    compare([Path("p1"), Path("p2")], [Path("b1"), Path("b2")], 10,
                            baseline_policy="futex-early", comparison_policy="futex-early-both")

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_new_policies_reject_software_or_physical_identity_change(self, analyze):
        for field in ("elf_sha256", "nbf_sha256", "bitstream_sha256"):
            with self.subTest(field=field):
                samples = self.deployment_results("preseed", "futex-early")
                samples[-1]["identity"][field] = "different"
                analyze.side_effect = samples
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    compare([Path("s1"), Path("s2")], [Path("r1"), Path("r2")], 10,
                            baseline_policy="preseed", comparison_policy="futex-early")

    def test_rejects_insufficient_or_repeated_boot_paths_and_invalid_policies(self):
        for baseline, comparison, kwargs, message in (
                ([Path("a")], [Path("b"), Path("c")], {}, "two independent"),
                ([Path("a"), Path("a")], [Path("b"), Path("c")], {}, "distinct transcript"),
                ([Path("a"), Path("b")], [Path("c"), Path("d")],
                 {"comparison_policy": "unknown"}, "comparison policy"),
                ([Path("a"), Path("b")], [Path("c"), Path("d")],
                 {"baseline_policy": "futex-early", "comparison_policy": "futex-early"}, "must differ")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    compare(baseline, comparison, **kwargs)

    @mock.patch("compare_scheduler_pipe_hint_policies.compare")
    def test_cli_selects_deployment_policies_without_continuous_labels(self, comparison):
        comparison.return_value = {"comparison_policy": "futex-early-both"}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "comparison.json"
            main(["--baseline", "p1", "p2", "--comparison", "b1", "b2",
                  "--baseline-policy", "futex-early", "--comparison-policy", "futex-early-both",
                  "--output", str(output)])
            self.assertEqual(json.loads(output.read_text()), comparison.return_value)
        comparison.assert_called_once_with([Path("p1"), Path("p2")],
                                           [Path("b1"), Path("b2")], 20000,
                                           "futex-early", "futex-early-both")

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_rejects_different_workloads_between_policies(self, analyze):
        samples = [result("preseed", "same", [(10.0, 1.0)]) for _ in range(2)]
        samples += [result("continuous", "same", [(20.0, 2.0)]) for _ in range(2)]
        for index, sample in enumerate(samples):
            sample["config"]["workload"] = "lookup" if index < 2 else "parse"
        analyze.side_effect = samples
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            compare([Path("p1"), Path("p2")],
                    [Path("c1"), Path("c2")], 10, baseline_policy="preseed")

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_reports_continuous_minus_seed(self, analyze):
        analyze.side_effect = [
            result("seed", "same", [(10.0, 1.0), (20.0, 2.0)]),
            result("seed", "same", [(20.0, 2.0), (30.0, 3.0)]),
            result("continuous", "same", [(40.0, 4.0), (50.0, 5.0)]),
            result("continuous", "same", [(50.0, 5.0), (60.0, 6.0)]),
        ]
        output = compare([Path("s1"), Path("s2")],
                         [Path("c1"), Path("c2")], 100)
        self.assertEqual(
            output["continuous_minus_seed"]["saved_cycles_per_roundtrip"],
            30.0,
        )
        self.assertEqual(output["comparison_minus_baseline"], output["continuous_minus_seed"])
        self.assertEqual(output["seed_replicates"], output["baseline_replicates"])
        self.assertEqual(output["continuous_replicates"], output["comparison_replicates"])

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_rejects_nonmatching_elf(self, analyze):
        analyze.side_effect = [
            result("seed", "first", [(10.0, 1.0)]),
            result("seed", "first", [(10.0, 1.0)]),
            result("continuous", "second", [(10.0, 1.0)]),
            result("continuous", "second", [(10.0, 1.0)]),
        ]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            compare([Path("s1"), Path("s2")],
                    [Path("c1"), Path("c2")], 10)

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_compares_continuous_with_preseed_explicitly(self, analyze):
        analyze.side_effect = [
            result("preseed", "same", [(10.0, 1.0)]),
            result("preseed", "same", [(20.0, 2.0)]),
            result("continuous", "same", [(40.0, 4.0)]),
            result("continuous", "same", [(50.0, 5.0)]),
        ]
        output = compare([Path("p1"), Path("p2")],
                         [Path("c1"), Path("c2")], 100,
                         baseline_policy="preseed")
        self.assertEqual(output["baseline_policy"], "preseed")
        self.assertEqual(
            output["continuous_minus_baseline"][
                "saved_cycles_per_roundtrip"],
            30.0,
        )
        self.assertNotIn("continuous_minus_seed", output)

    @mock.patch("compare_scheduler_pipe_hint_policies.analyze")
    def test_compares_matched_with_unmatched_continuous(self, analyze):
        analyze.side_effect = [
            result("continuous-unmatched", "same", [(10.0, 1.0)]),
            result("continuous-unmatched", "same", [(20.0, 2.0)]),
            result("continuous", "same", [(40.0, 4.0)]),
            result("continuous", "same", [(50.0, 5.0)]),
        ]
        output = compare([Path("u1"), Path("u2")],
                         [Path("c1"), Path("c2")], 100,
                         baseline_policy="continuous-unmatched")
        self.assertEqual(output["baseline_policy"],
                         "continuous-unmatched")
        self.assertEqual(
            output["continuous_minus_baseline"][
                "saved_percentage_points"],
            3.0,
        )


if __name__ == "__main__":
    unittest.main()
