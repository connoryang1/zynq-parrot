"""Test strict fixed-arm pipe replay table comparison analysis."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from analyze_scheduler_physical_preview_table_ab import analyze
from test_analyze_scheduler_physical_preview_fixed_ab import IDENTITY, write_run


class TableAnalyzerTest(unittest.TestCase):
    def test_opposite_order_tables_report_known_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current1 = write_run(root, "current1", "enabled", 100)
            candidate1 = write_run(root, "candidate1", "enabled", 90)
            current2 = write_run(root, "current2", "enabled", 102)
            candidate2 = write_run(root, "candidate2", "enabled", 92)
            candidate_nbf = "5" * 64
            for path in (candidate1, candidate2):
                status_path = path.with_suffix(".log.status.json")
                status = json.loads(status_path.read_text())
                status["nbf_sha256"] = candidate_nbf
                status_path.write_text(json.dumps(status) + "\n")
            args = argparse.Namespace(
                current_nbf_sha256=IDENTITY["nbf_sha256"],
                candidate_nbf_sha256=candidate_nbf,
                transfer_sha256=IDENTITY["transfer_sha256"],
                elf_sha256=IDENTITY["elf_sha256"],
                control_program_sha256=IDENTITY["control_program_sha256"],
                group=7,
                replicate=[
                    ("current-candidate", str(current1), str(candidate1)),
                    ("candidate-current", str(current2), str(candidate2)),
                ],
                iid_resamples=100,
                block_resamples=100,
            )
            result = analyze(args)
        metric = result["metrics"]["wake_to_entry"]
        self.assertEqual(metric["replicate_stratified_point_estimate"], -10)
        self.assertEqual(
            metric["pooled_median_difference_candidate_minus_current"], -10
        )
        self.assertEqual(metric["iid_bootstrap"]["fraction_enabled_faster"], 1)

    def test_equal_nbf_identities_are_rejected(self):
        args = argparse.Namespace(
            current_nbf_sha256=IDENTITY["nbf_sha256"],
            candidate_nbf_sha256=IDENTITY["nbf_sha256"],
            transfer_sha256=IDENTITY["transfer_sha256"],
            elf_sha256=IDENTITY["elf_sha256"],
            control_program_sha256=IDENTITY["control_program_sha256"],
            group=7,
            replicate=[
                ("current-candidate", "a", "b"),
                ("candidate-current", "c", "d"),
            ],
            iid_resamples=10,
            block_resamples=10,
        )
        with self.assertRaisesRegex(ValueError, "must differ"):
            analyze(args)


if __name__ == "__main__":
    unittest.main()
