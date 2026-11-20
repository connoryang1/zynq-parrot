#!/usr/bin/env python3
"""Verify fail-closed transfer handling for the sustained pipe-hint runner."""

import base64
import hashlib
import gzip
from pathlib import Path
import tempfile
import unittest

from run_scheduler_pipe_hint import (
    GUEST_ELF,
    build_guest_command,
    parse_args,
    validate_args,
    validate_transfer,
    library_transfer,
    GUEST_ZLIB,
)


class PipeHintRunnerTests(unittest.TestCase):
    def test_compressed_transfer_roundtrip_and_rejection(self):
        from emit_resume_transfer import commands
        with tempfile.TemporaryDirectory() as directory:
            elf, transfer = Path(directory) / "elf", Path(directory) / "transfer"
            payload = bytes(range(256)) * 100
            elf.write_bytes(payload)
            generated = commands(elf)
            transfer.write_text("\n".join(generated) + "\n")
            expected = hashlib.sha256(payload).hexdigest()
            validate_transfer(transfer, expected)
            self.assertEqual(generated, commands(elf))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_transfer(transfer, "0" * 64)
            transfer.write_text("\n".join(generated).replace("gunzip -c", "gunzip -f") + "\n")
            with self.assertRaisesRegex(ValueError, "unexpected shell"):
                validate_transfer(transfer, expected)
            generated[1] = generated[1].replace(generated[1].split("'")[1], "AAAA")
            transfer.write_text("\n".join(generated) + "\n")
            with self.assertRaisesRegex(ValueError, "gzip ELF"):
                validate_transfer(transfer, expected)

    def test_abi_probe_has_its_own_exact_command(self):
        for capability in ("absent", "present"):
            args = parse_args([
                "image.nbf", "transfer", "a" * 64, "result.log",
                "--bitstream-sha256", "b" * 64,
                "--retention-probe", capability,
            ])
            self.assertEqual(build_guest_command(args), GUEST_ELF + " " + capability)
            args.zlib_library = Path("library")
            with self.assertRaisesRegex(ValueError, "probe requires its own ELF"):
                validate_args(args)

    def test_optional_library_has_only_bounded_fixed_destination_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library"
            payload = bytes(range(256)) * 11
            path.write_bytes(payload)
            commands = library_transfer(path)
            self.assertEqual(commands[0], f": > {GUEST_ZLIB}.b64")
            self.assertEqual(commands[-2], f"base64 -d {GUEST_ZLIB}.b64 > {GUEST_ZLIB}.gz")
            self.assertEqual(commands[-1], f"/bin/busybox gunzip -c {GUEST_ZLIB}.gz > {GUEST_ZLIB}")
            self.assertTrue(all(len(command) <= 768 for command in commands))
            encoded = "".join(command.split("'")[1] for command in commands[1:-2])
            self.assertEqual(gzip.decompress(base64.b64decode(encoded)), payload)
            self.assertEqual(commands, library_transfer(path))

    def test_retention_and_deflate_arguments_bind_optional_library(self):
        for policy in ("retention-rr", "retention-first"):
            args = parse_args([
                "image.nbf", "transfer", "a" * 64, "result.log",
                "--bitstream-sha256", "b" * 64, "--policy", policy,
                "--workload", "deflate", "--working-set-kib", "32",
                "--zlib-library", "exact-libz.so.1",
            ])
            command = build_guest_command(args)
            self.assertTrue(command.startswith("LD_LIBRARY_PATH=/tmp " + GUEST_ELF))
            self.assertIn(policy, command)
            self.assertTrue(command.endswith("pipe plain 32 deflate"))

    def test_seed_policy_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--policy", "seed",
        ])
        self.assertEqual(args.policy, "seed")

    def test_warmup_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--warmup", "256",
        ])
        self.assertEqual(args.warmup, 256)

    def test_preseed_policy_is_accepted(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--policy", "preseed",
        ])
        self.assertEqual(args.policy, "preseed")

    def test_futex_sync_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
        ])
        self.assertEqual(args.sync, "futex")

    def test_resume_leg_profile_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
            "--profile", "legs",
        ])
        self.assertEqual(args.profile, "legs")

    def test_working_set_is_bound_into_runner_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
            "--working-set-kib", "256",
        ])
        self.assertEqual(args.working_set_kib, 256)
        self.assertTrue(build_guest_command(args).endswith("futex plain 256"))
        self.assertEqual(args.workload, "scan")

    def test_natural_workload_is_appended_without_changing_scan_abi(self):
        for workload in ("scan", "lookup", "parse", "chase"):
            with self.subTest(workload=workload):
                args = parse_args([
                    "image.nbf", "transfer", "a" * 64, "result.log",
                    "--bitstream-sha256", "b" * 64,
                    "--working-set-kib", "32", "--workload", workload,
                ])
                suffix = "pipe plain 32" + (f" {workload}" if workload != "scan" else "")
                self.assertTrue(build_guest_command(args).endswith(suffix))

    def test_legacy_cli_rejects_natural_workload(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--workload", "lookup",
            "--legacy-four-arg-cli",
        ])
        with self.assertRaisesRegex(ValueError, "requires pipe/plain"):
            validate_args(args)

    def test_accepts_unmatched_continuous_policy(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "continuous-unmatched",
        ])
        self.assertEqual(args.policy, "continuous-unmatched")

    def test_futex_early_policy_requires_futex(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "futex-early",
        ])
        with self.assertRaisesRegex(ValueError, "requires futex"):
            validate_args(args)

    def test_accepts_futex_early_policy_with_futex(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "futex-early", "--sync", "futex",
        ])
        self.assertEqual(args.policy, "futex-early")

    def test_both_directions_is_explicit_and_requires_futex(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64,
            "--policy", "futex-early-both", "--workload", "lookup",
        ])
        with self.assertRaisesRegex(ValueError, "requires futex"):
            validate_args(args)
        args.sync = "futex"
        self.assertIn(" futex-early-both ", build_guest_command(args))

    def test_legacy_terminal_protocol_must_be_selected_explicitly(self):
        common = ["image.nbf", "transfer", "a" * 64, "result.log",
                  "--bitstream-sha256", "b" * 64]
        self.assertFalse(parse_args(common).legacy_no_terminal_handshake)
        old = parse_args(common + ["--legacy-no-terminal-handshake"])
        self.assertTrue(old.legacy_no_terminal_handshake)
        self.assertEqual(build_guest_command(old), build_guest_command(parse_args(common)))

    def test_resume_leg_profile_rejects_pipe_sync(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--profile", "legs",
        ])
        with self.assertRaisesRegex(ValueError, "requires futex"):
            validate_args(args)

    def test_legacy_four_arg_cli_omits_new_mode_arguments(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--policy", "preseed",
            "--warmup", "256", "--legacy-four-arg-cli",
        ])
        self.assertEqual(
            build_guest_command(args),
            f"{GUEST_ELF} 512 8 preseed 256",
        )

    def test_legacy_four_arg_cli_rejects_new_futex_mode(self):
        args = parse_args([
            "image.nbf", "transfer", "a" * 64, "result.log",
            "--bitstream-sha256", "b" * 64, "--sync", "futex",
            "--legacy-four-arg-cli",
        ])
        with self.assertRaisesRegex(ValueError, "requires pipe/plain"):
            validate_args(args)

    def test_status_uses_pointer_copy_abi(self):
        source = (Path(__file__).resolve().parent
                  / "scheduler_pipe_hint_benchmark.c").read_text()
        self.assertIn("(unsigned long)&status", source)
        self.assertNotIn("PR_BP_PREVIEW_ICACHE_STATUS, 0UL", source)

    def test_parent_resume_leg_stops_before_working_set(self):
        source = (Path(__file__).resolve().parent
                  / "scheduler_pipe_hint_benchmark.c").read_text()
        futex = source.split("static struct cell_result run_futex_cell", 1)[1]
        measured = futex.split("begin = cycle();", 1)[1].split(
            "end = cycle();", 1)[0]
        resume = measured.index(
            "parent_resume += cycle() - shared->child_launch;")
        working_set = measured.index(
            "parent_checksum += resume_workload_run(")
        self.assertLess(resume, working_set)

    def test_futex_early_patch_excludes_internal_wake_callers(self):
        patch = (Path(__file__).resolve().parent / "kernel-patches" /
                 "0026-blackparrot-early-futex-instruction-replay.patch").read_text()
        self.assertIn("--- a/kernel/futex/syscalls.c", patch)
        self.assertIn("this at syscall dispatch excludes internal", patch)
        self.assertNotIn("--- a/kernel/futex/waitwake.c", patch)

    def test_transfer_binds_exact_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer"
            payload = b"exact pipe benchmark"
            encoded = base64.b64encode(payload).decode()
            path.write_text(
                f": > {GUEST_ELF}.b64\n"
                f"echo '{encoded}' >> {GUEST_ELF}.b64\n"
                f"base64 -d {GUEST_ELF}.b64 > {GUEST_ELF}\n"
                f"chmod +x {GUEST_ELF}\n"
            )
            validate_transfer(path, hashlib.sha256(payload).hexdigest())
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_transfer(path, "0" * 64)

    def test_transfer_rejects_extra_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer"
            path.write_text(
                f": > {GUEST_ELF}.b64\n"
                "uname -a\n"
                f"base64 -d {GUEST_ELF}.b64 > {GUEST_ELF}\n"
                f"chmod +x {GUEST_ELF}\n"
            )
            with self.assertRaisesRegex(ValueError, "unexpected"):
                validate_transfer(path, "0" * 64)

    def test_transfer_rejects_oversize_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer"
            path.write_text("x" * 769 + "\n")
            with self.assertRaisesRegex(ValueError, "exceeds 768"):
                validate_transfer(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
