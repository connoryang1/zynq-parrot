"""Host checks for the completed-data oracle transcript analyzer."""

import unittest

import analyze_scheduler_data_oracle_best_case as analyzer


class DataOracleAnalyzerTest(unittest.TestCase):
    @staticmethod
    def transcript(nonzero_fault=False, corrupt_mode=False):
        lines = ["DATA_ORACLE_CHILD PASS", "INFO:    CORE PASS", "INFO:    BSG PASS"]
        conditions = ((16, "independent"), (16, "dependent"),
                      (32, "independent"), (32, "dependent"))
        for footprint, shape in conditions:
            lines.append(
                f"DATA_ORACLE_FAULTS footprint={footprint} shape={shape} "
                f"faults={1 if nonzero_fault and footprint == 16 and shape == 'independent' else 0}"
            )
            for trial in range(128):
                mode = (0, 1, 1, 0)[trial & 3]
                if corrupt_mode and footprint == 16 and shape == "independent" and trial == 1:
                    mode = 0
                load = 40 if mode else 100
                entry = 1000
                wake_to_load = entry + load
                lines.append(
                    f"DATA_ORACLE trial={trial} footprint={footprint} shape={shape} "
                    f"mode={mode} oracle_cost=80 wake_to_entry={entry} "
                    f"load_cycles={load} wake_to_load={wake_to_load} "
                    f"roundtrip={wake_to_load + 100}"
                )
        lines.append("DATA_ORACLE_PARENT PASS")
        return "\n".join(lines)

    def test_balanced_transcript(self):
        result = analyzer.summarize(self.transcript())
        metric = result["conditions"]["16_independent"]["metrics"]["load_cycles"]
        self.assertEqual(100, metric["cold_median_cycles"])
        self.assertEqual(40, metric["oracle_median_cycles"])
        self.assertEqual(2.5, metric["median_ratio_cold_over_oracle"])
        self.assertEqual(60, metric["paired_median_saved_cycles"])
        self.assertEqual([60.0, 60.0], metric["paired_95pct_ci_saved_cycles"])

    def test_rejects_measured_fault(self):
        with self.assertRaisesRegex(ValueError, "minor faults"):
            analyzer.summarize(self.transcript(nonzero_fault=True))

    def test_rejects_unbalanced_block(self):
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            analyzer.summarize(self.transcript(corrupt_mode=True))


if __name__ == "__main__":
    unittest.main()
