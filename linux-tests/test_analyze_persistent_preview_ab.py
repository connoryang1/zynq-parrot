"""Test strict validation for persistent preview A/B transcripts."""

import argparse
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from analyze_persistent_preview_ab import analyze, load_run


SHA_NBF = "1" * 64
SHA_TRANSFER = "2" * 64
SHA_ELF = "3" * 64
SHA_CONTROL = "4" * 64
SHA_BITSTREAM = "5" * 64
IDENTITY = {
    "nbf_sha256": SHA_NBF,
    "transfer_sha256": SHA_TRANSFER,
    "elf_sha256": SHA_ELF,
    "control_program_sha256": SHA_CONTROL,
    "bitstream_sha256": SHA_BITSTREAM,
    "prefix_lines": [0x1000],
}


def write_run(directory, name, mode, base):
    """Write one minimal valid serialized-run transcript and status."""
    path = Path(directory) / name
    value = 6 if mode == "wake-trigger" else 0
    rows = []
    for sample in range(1, 202):
        rows.extend((
            f"SAMPLE={sample}",
            "TRACE_HEADER cpu=0 window=1 start=0 peer_begin=0 peer_wake=0 "
            f"peer_block=0 resume=0 elapsed={base + sample} i_count=16 "
            "d_count=4 i_overflow=0 d_overflow=0 armed=0 status=0x0",
            f"TRACE_PASS records=20 elapsed={base + sample}",
        ))
    text = "\n".join((
        f"BITSTREAM_SHA256={SHA_BITSTREAM}",
        f"TRACE_PREVIEW mode={mode} value={value}",
        *rows,
        "TRACE_CAPTURE_PASS samples=201 allow_overflow=1",
        "TRACE_RECORD seq=0 side=I index=0 cycle=0 relative=0 message=0x0 "
        "paddr=0x000001000 raw=0x0",
        "TRACE_FINAL_ADDRESSES records=20 i_overflow=0 d_overflow=0",
        "TRACE_CAPTURE_EXIT rc=0",
        "INFO: CORE PASS",
        "INFO: BSG PASS",
        "",
    ))
    path.write_text(text)
    status = {
        "status": "PASS",
        "nbf_sha256": SHA_NBF,
        "transfer_sha256": SHA_TRANSFER,
        "elf_sha256": SHA_ELF,
        "control_program_sha256": SHA_CONTROL,
        "bitstream_sha256": SHA_BITSTREAM,
        "window": "to-peer",
        "samples": 201,
        "program": "cache-miss",
        "cache_preview_mode": mode,
        "cache_summary_only": True,
        "cache_allow_overflow": True,
        "cache_final_addresses": True,
    }
    path.with_suffix(path.suffix + ".status.json").write_text(
        json.dumps(status) + "\n"
    )
    return path


class PersistentPreviewAnalysisTest(unittest.TestCase):
    def test_load_discards_exactly_one_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(directory, "enabled.log", "wake-trigger", 100)
            result = load_run(path, "enabled", IDENTITY)
            self.assertEqual(result["analyzed_samples"], 200)
            self.assertEqual(result["elapsed"][0], 102)

    def test_status_mode_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(directory, "enabled.log", "wake-trigger", 100)
            status = path.with_suffix(".log.status.json")
            data = json.loads(status.read_text())
            data["cache_preview_mode"] = "disabled"
            status.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "cache_preview_mode"):
                load_run(path, "enabled", IDENTITY)

    def test_status_bitstream_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(directory, "enabled.log", "wake-trigger", 100)
            status = path.with_suffix(".log.status.json")
            data = json.loads(status.read_text())
            data["bitstream_sha256"] = "6" * 64
            status.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "bitstream_sha256"):
                load_run(path, "enabled", IDENTITY)

    def test_bitstream_log_marker_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(directory, "enabled.log", "wake-trigger", 100)
            path.write_text(path.read_text().replace(
                f"BITSTREAM_SHA256={SHA_BITSTREAM}\n", ""
            ))
            with self.assertRaisesRegex(ValueError, "BITSTREAM_SHA256"):
                load_run(path, "enabled", IDENTITY)

    def test_compressed_log_uses_plain_log_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_run(directory, "enabled.log", "wake-trigger", 100)
            compressed = path.with_suffix(".log.gz")
            with path.open("rb") as source, gzip.open(compressed, "wb") as target:
                target.write(source.read())
            path.unlink()
            result = load_run(compressed, "enabled", IDENTITY)
            self.assertEqual(result["analyzed_samples"], 200)

    def test_two_opposite_order_replicates_are_analyzed(self):
        with tempfile.TemporaryDirectory() as directory:
            enabled1 = write_run(directory, "enabled1.log", "wake-trigger", 100)
            disabled1 = write_run(directory, "disabled1.log", "disabled", 200)
            enabled2 = write_run(directory, "enabled2.log", "wake-trigger", 110)
            disabled2 = write_run(directory, "disabled2.log", "disabled", 210)
            args = argparse.Namespace(
                nbf_sha256=SHA_NBF,
                transfer_sha256=SHA_TRANSFER,
                elf_sha256=SHA_ELF,
                control_program_sha256=SHA_CONTROL,
                bitstream_sha256=SHA_BITSTREAM,
                prefix_json=Path(directory) / "prefix.json",
                replicate=[
                    ("enabled-disabled", str(enabled1), str(disabled1)),
                    ("disabled-enabled", str(enabled2), str(disabled2)),
                ],
                iid_resamples=100,
                block_resamples=100,
            )
            args.prefix_json.write_text(json.dumps({
                "fixed_shared_prefix": {"lines": [{"paddr": 0x1000}]}
            }))
            result = analyze(args)
            self.assertEqual(result["pooled"]["samples_per_arm"], 400)
            self.assertEqual(
                result["replicate_stratified"]["point_estimate"], -100
            )


if __name__ == "__main__":
    unittest.main()
