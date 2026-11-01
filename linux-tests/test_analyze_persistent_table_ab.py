"""Test strict identity and ordering checks for persistent replay-table A/Bs."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from analyze_persistent_table_ab import analyze, load_run


SHA_CURRENT = "1" * 64
SHA_CANDIDATE = "2" * 64
SHA_TRANSFER = "3" * 64
SHA_ELF = "4" * 64
SHA_CONTROL = "5" * 64
IDENTITY = {
    "current_nbf_sha256": SHA_CURRENT,
    "candidate_nbf_sha256": SHA_CANDIDATE,
    "transfer_sha256": SHA_TRANSFER,
    "elf_sha256": SHA_ELF,
    "control_program_sha256": SHA_CONTROL,
}


def write_run(directory, name, arm, base):
    """Write one minimal valid wake-trigger table run and runner status."""
    path = Path(directory) / name
    rows = []
    for sample in range(1, 202):
        rows.extend((
            f"SAMPLE={sample}",
            "TRACE_HEADER cpu=0 window=1 start=0 peer_begin=0 peer_wake=0 "
            f"peer_block=0 resume=0 elapsed={base + sample} i_count=16 "
            "d_count=4 i_overflow=0 d_overflow=0 armed=0 status=0x0",
            f"TRACE_PASS records=20 elapsed={base + sample}",
        ))
    path.write_text("\n".join((
        "TRACE_PREVIEW mode=wake-trigger value=6",
        *rows,
        "TRACE_CAPTURE_PASS samples=201 allow_overflow=1",
        "TRACE_RECORD seq=0 side=I index=0 cycle=0 relative=0 message=0x0 "
        "paddr=0x000001000 raw=0x0",
        "TRACE_FINAL_ADDRESSES records=20 i_overflow=0 d_overflow=0",
        "TRACE_CAPTURE_EXIT rc=0",
        "INFO: CORE[0] PASS",
        "INFO: BSG PASS",
        "",
    )))
    status = {
        "status": "PASS",
        "nbf_sha256": IDENTITY[f"{arm}_nbf_sha256"],
        "transfer_sha256": SHA_TRANSFER,
        "elf_sha256": SHA_ELF,
        "control_program_sha256": SHA_CONTROL,
        "window": "to-peer",
        "samples": 201,
        "program": "cache-miss",
        "cache_preview_mode": "wake-trigger",
        "cache_summary_only": True,
        "cache_allow_overflow": True,
        "cache_final_addresses": True,
    }
    path.with_suffix(path.suffix + ".status.json").write_text(
        json.dumps(status) + "\n"
    )
    return path


class PersistentTableAnalysisTest(unittest.TestCase):
    def test_load_requires_arm_specific_nbf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(directory, "candidate.log", "candidate", 100)
            status_path = path.with_suffix(".log.status.json")
            status = json.loads(status_path.read_text())
            status["nbf_sha256"] = SHA_CURRENT
            status_path.write_text(json.dumps(status))
            with self.assertRaisesRegex(ValueError, "nbf_sha256"):
                load_run(path, "candidate", IDENTITY, [0x1000])

    def test_two_opposite_orders_are_analyzed(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate1 = write_run(directory, "candidate1.log", "candidate", 100)
            current1 = write_run(directory, "current1.log", "current", 200)
            candidate2 = write_run(directory, "candidate2.log", "candidate", 110)
            current2 = write_run(directory, "current2.log", "current", 210)
            current_prefix = Path(directory) / "current.json"
            candidate_prefix = Path(directory) / "candidate.json"
            prefix = {"fixed_shared_prefix": {"lines": [{"paddr": 0x1000}]}}
            current_prefix.write_text(json.dumps(prefix))
            candidate_prefix.write_text(json.dumps(prefix))
            args = argparse.Namespace(
                current_nbf_sha256=SHA_CURRENT,
                candidate_nbf_sha256=SHA_CANDIDATE,
                transfer_sha256=SHA_TRANSFER,
                elf_sha256=SHA_ELF,
                control_program_sha256=SHA_CONTROL,
                current_prefix_json=current_prefix,
                candidate_prefix_json=candidate_prefix,
                replicate=[
                    ("current-candidate", str(candidate1), str(current1)),
                    ("candidate-current", str(candidate2), str(current2)),
                ],
                iid_resamples=100,
                block_resamples=100,
            )
            result = analyze(args)
            self.assertEqual(result["pooled"]["samples_per_arm"], 400)
            self.assertEqual(
                result["replicate_stratified"]["point_estimate"], -100
            )

    def test_duplicate_order_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "prefix.json"
            prefix.write_text(json.dumps({
                "fixed_shared_prefix": {"lines": [{"paddr": 0x1000}]}
            }))
            args = argparse.Namespace(
                current_nbf_sha256=SHA_CURRENT,
                candidate_nbf_sha256=SHA_CANDIDATE,
                transfer_sha256=SHA_TRANSFER,
                elf_sha256=SHA_ELF,
                control_program_sha256=SHA_CONTROL,
                current_prefix_json=prefix,
                candidate_prefix_json=prefix,
                replicate=[("current-candidate", "a", "b")] * 2,
                iid_resamples=1,
                block_resamples=1,
            )
            with self.assertRaisesRegex(ValueError, "opposite boot orders"):
                analyze(args)


if __name__ == "__main__":
    unittest.main()
