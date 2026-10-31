"""Host checks for the combined completed-cache oracle analyzer."""

import unittest

import analyze_scheduler_combined_oracle_best_case as analyzer


class CombinedOracleAnalyzerTest(unittest.TestCase):
    @staticmethod
    def transcript(faults=0, corrupt_mode=False, schedule="rotated"):
        lines = [
            "COMBINED_ORACLE_CHILD PASS",
            "INFO:    CORE PASS",
            "INFO:    BSG PASS",
            f"COMBINED_ORACLE_FAULTS faults={faults}",
        ]
        for trial in range(256):
            mode = analyzer.expected_mode(trial, schedule)
            if corrupt_mode and trial == 1:
                mode = (mode + 1) & 3
            code = 40 if mode & 1 else 100
            data = 20 if mode & 2 else 80
            useful = code + data
            entry = 1000
            lines.append(
                f"COMBINED_ORACLE trial={trial} mode={mode} prep_cost=90 "
                f"wake_to_entry={entry} code_cycles={code} data_cycles={data} "
                f"useful_cycles={useful} wake_to_useful={entry + useful} "
                f"roundtrip={entry + useful + 100}"
            )
        lines.append("COMBINED_ORACLE_PARENT PASS")
        return "\n".join(lines)

    def test_balanced_factorial_transcript(self):
        result = analyzer.summarize(self.transcript())
        code = result["metrics"]["code_cycles"]
        data = result["metrics"]["data_cycles"]
        useful = result["metrics"]["useful_cycles"]
        self.assertEqual(100, code["median_cycles_by_mode"]["cold"])
        self.assertEqual(40, code["median_cycles_by_mode"]["instruction"])
        self.assertEqual(60, code["cold_minus_mode"]["instruction"]
                         ["paired_median_saved_cycles"])
        self.assertEqual(60, data["cold_minus_mode"]["data"]
                         ["paired_median_saved_cycles"])
        self.assertEqual(120, useful["cold_minus_mode"]["combined"]
                         ["paired_median_saved_cycles"])
        self.assertEqual([120.0, 120.0], useful["cold_minus_mode"]["combined"]
                         ["paired_95pct_ci_saved_cycles"])

    def test_rejects_faults(self):
        with self.assertRaisesRegex(ValueError, "zero measured-fault"):
            analyzer.summarize(self.transcript(faults=1))

    def test_rejects_unbalanced_block(self):
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            analyzer.summarize(self.transcript(corrupt_mode=True))

    def test_fixed_schedule_diagnostic(self):
        result = analyzer.summarize(self.transcript(schedule="fixed"), "fixed")
        self.assertEqual("fixed", result["schedule"])


if __name__ == "__main__":
    unittest.main()
