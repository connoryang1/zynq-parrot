#!/usr/bin/env python3
"""Check that simulator verdicts cannot hide failures behind success markers."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from check_run import TEST_MARKERS, check_transcript


PASS = "BSG-INFO: CORE PASS\nBSG-INFO: BSG PASS\n"
GPIO = (
    "[14623150000] %Fatal: bsg_nonsynth_dpi_gpio.sv:64: Assertion failed "
    "in TOP.gpio: BSG ERROR: final block executed before fini() was called\n"
    "%Error: /source/bsg_nonsynth_dpi_gpio.sv:64: Verilog $stop\n"
    "Aborting...\n"
)


class TranscriptTests(unittest.TestCase):
    def test_selected_program_must_complete_before_core_pass(self):
        for name, marker in TEST_MARKERS.items():
            with self.subTest(name=name):
                check_transcript(marker + "\n" + PASS + GPIO, 2, name)
                for text in (PASS, PASS + marker, "prefix " + marker + "\n" + PASS):
                    with self.assertRaises(ValueError):
                        check_transcript(text, test=name)
        with self.assertRaises(ValueError):
            check_transcript(PASS, test="removed_test")

    def test_wrong_program_and_handoff_variant_are_rejected(self):
        for wrong in ("mt_ctxtsw_smoke_test", "mt_umode_nonresident_handoff_test",
                      "mt_umode_nonresident_sv39_handoff_test"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                check_transcript(TEST_MARKERS[wrong] + "\n" + PASS,
                                 test="mt_umode_nonresident_sv39_data_handoff_test")

    def test_pass(self):
        check_transcript(PASS)
        check_transcript(PASS.replace("CORE PASS", "CORE[0] PASS"))
        check_transcript("trace timeout armed for 120 seconds\n" + PASS)

    def test_incomplete(self):
        for text in ("", "BSG PASS\n", "CORE PASS\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_transcript(text)

    def test_failure_markers(self):
        for marker in ("CORE FAIL", "CORE[0] FAIL", "BSG FAIL", "[BSG-FAIL]",
                       "trace timeout reached", "target runtime limit reached after 100 ms"):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                check_transcript(marker + "\n" + PASS)

    def test_other_errors_before_or_after_pass(self):
        for error in ("%Fatal: unrelated.sv: Assertion failed", "%Error: broken",
                      "Assertion `pointer != NULL' failed", "Aborting...", "ERROR: build failed"):
            for text in (error + "\n" + PASS, PASS + error + "\n"):
                with self.subTest(text=text), self.assertRaises(ValueError):
                    check_transcript(text)

    def test_known_shutdown(self):
        check_transcript(PASS + GPIO)
        check_transcript(PASS + GPIO, 134)
        check_transcript(PASS + GPIO, 2)  # Recursive Make returns its own status.

    def test_shutdown_requires_both_prior_passes_and_exact_errors(self):
        for text in (GPIO + PASS, "CORE PASS\n" + GPIO + "BSG PASS\n",
                     "BSG PASS\n" + GPIO, PASS + GPIO + "%Error: unrelated\n",
                     PASS + GPIO.replace("Verilog $stop", "different failure"),
                     PASS + GPIO.replace("Aborting...\n", "")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_transcript(text, 2)

    def test_nonzero_without_known_shutdown(self):
        with self.assertRaises(ValueError):
            check_transcript(PASS, 2)

    def test_missing_and_empty_file_cli(self):
        helper = Path(__file__).with_name("check_run.py")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            for exists in (False, True):
                if exists:
                    path.touch()
                result = subprocess.run([sys.executable, str(helper), str(path)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(result.returncode, 1)
                self.assertIn(b"INVALID RUN", result.stderr)


class HarnessTests(unittest.TestCase):
    def test_real_makefile_rejects_another_programs_success(self):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            sim = base / "sim"
            sim.mkdir()
            (base / "riscv" / "bp-tests").mkdir(parents=True)
            (sim / "Makefile").write_text(
                ".PHONY: build run\nbuild:\n\t@true\n"
                "run:\n\t@cp fixture.log run.log\n\t@cat run.log\n")
            command = ["make", "-C", str(root / "testing"), "TOP=" + str(root),
                       "SIM_DIR=" + str(sim), "LOG_DIR=" + str(base / "logs"),
                       "ZP_RISCV_DIR=" + str(base / "riscv"), "CC=true",
                       "run-mt_ctxtsw_smoke_test"]
            for marker, expected in (("", False),
                                     (TEST_MARKERS["mt_csr_isolation_test"], False),
                                     (TEST_MARKERS["mt_ctxtsw_smoke_test"], True)):
                with self.subTest(marker=marker):
                    (sim / "fixture.log").write_text(marker + "\n" + PASS)
                    result = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, timeout=10)
                    self.assertEqual(result.returncode == 0, expected, result.stdout)

    def test_model_stamp_round_trip(self):
        """Changing A -> B -> A must recreate A, never retain B's identity."""
        make_dir = Path(__file__).resolve().parents[1] / "cosim" / "mk"
        env = os.environ.copy()
        for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as directory:
            for contexts in (4, 8, 4):
                stamp = ".build_config-nt2-nc{}-cfgtest-trace1".format(contexts)
                result = subprocess.run(
                    ["make", "-C", directory, "-f", str(make_dir / "Makefile.verilator"),
                     "COSIM_MK_DIR=" + str(make_dir), "NUM_THREADS=2",
                     "NUM_CONTEXTS=" + str(contexts), "CFG=test", "TRACE=1",
                     "BUILD_COLLATERAL=", "obj_dir/" + stamp],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(sorted(p.name for p in (Path(directory) / "obj_dir").iterdir()),
                                 [stamp])

    def test_real_makefile_default_and_failed_build(self):
        """Exercise the real harness with exclusively temporary fake outputs."""
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            sim, logs, riscv = (base / name for name in ("sim", "logs", "riscv"))
            sim.mkdir()
            logs.mkdir()
            (riscv / "bp-tests").mkdir(parents=True)
            (sim / "Makefile").write_text(
                ".PHONY: build run\nbuild:\n\t@false\n"
                "run:\n\t@touch entered-run\n")
            stale_log = sim / "run.log"
            stale_log.write_text(PASS + GPIO)
            sentinel = logs / "keep.log"
            sentinel.write_text("must survive bare make")
            command = ["make", "-C", str(root / "testing"), "TOP=" + str(root),
                       "SIM_DIR=" + str(sim), "LOG_DIR=" + str(logs),
                       "ZP_RISCV_DIR=" + str(riscv), "CC=true"]
            result = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn(b"Targets:", result.stdout)
            self.assertTrue(sentinel.exists(), "bare make must not clean logs")
            self.assertEqual(stale_log.read_text(), PASS + GPIO)

            result = subprocess.run(command + ["run-mt_ctxtsw_smoke_test"], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(b"model build failed", result.stdout)
            self.assertFalse(stale_log.exists(), "old success must be removed before building")
            self.assertFalse((sim / "entered-run").exists(), "failed model must never run")


if __name__ == "__main__":
    unittest.main()
