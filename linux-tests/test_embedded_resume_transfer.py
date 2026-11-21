"""Verify embedded-copy declarations and hash-before-execution host behavior.

The console is a local stateful mock; no SSH, shell copy, board, or guest
execution occurs. Emitter subprocesses only read temporary host payloads.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import pexpect

from emit_resume_transfer import commands as compressed_commands
import run_scheduler_pipe_hint as runner

HERE = Path(__file__).resolve().parent


class GuestConsole:
    """Model copied bytes, hash replies, execution, and terminal markers."""
    def __init__(self, args, elf_hash=None, library_hash=None, core=True, bsg=True):
        self.args = args
        self.elf_hash = elf_hash or args.elf_sha256
        self.library_hash = library_hash or (runner.sha256(args.zlib_library)
                                              if args.zlib_library else None)
        self.core = core
        self.bsg = bsg
        self.logfile_read = None
        self.events = []
        self.sent = []
        self.verified = set()
        self.copied = set()
        self.alive = True
        self.exitstatus = None
        self.signalstatus = None
        self.last = None
        self.app = runner.build_guest_command(args)

    def emit(self, text):
        if self.logfile_read is not None:
            self.logfile_read.write(text + "\n")
            self.logfile_read.flush()

    def setwinsize(self, rows, columns):
        self.events.append(("terminal", rows, columns))

    def sendline(self, command):
        self.sent.append(command)
        self.last = command
        self.events.append(("send", command))
        if command == f"cp {runner.EMBEDDED_DIRECTORY}libz.so.1 {runner.GUEST_ZLIB}":
            self.copied.add(runner.GUEST_ZLIB)
        elif command.startswith("cp " + runner.EMBEDDED_DIRECTORY):
            if command != f"cp {runner.EMBEDDED_DIRECTORY}plain {runner.GUEST_ELF}":
                raise AssertionError("unexpected ELF source/destination in mock")
            self.copied.add(runner.GUEST_ELF)
        elif command == self.app:
            required = {runner.GUEST_ELF}
            if self.args.zlib_library:
                required.add(runner.GUEST_ZLIB)
            if self.verified != required:
                raise AssertionError("application command issued before exact guest hashes")
            self.events.append(("execute", command))

    def expect_exact(self, expected):
        if self.last == f"/bin/busybox sha256sum {runner.GUEST_ELF}":
            destination, actual = runner.GUEST_ELF, self.elf_hash
        elif self.last == f"/bin/busybox sha256sum {runner.GUEST_ZLIB}":
            destination, actual = runner.GUEST_ZLIB, self.library_hash
        else:
            raise AssertionError("hash confirmation without the fixed sha256sum command")
        if destination not in self.copied:
            raise AssertionError("guest hash requested before copying payload")
        response = f"{actual}  {destination}"
        self.emit(response)
        if expected != response:
            self.events.append(("wrong_hash", destination))
            raise pexpect.TIMEOUT("mock guest returned a different SHA-256")
        self.verified.add(destination)
        self.events.append(("verified", destination))

    def prompt(self, child, timeout, stage):
        if child is not self:
            raise AssertionError("unexpected console")
        self.events.append(("prompt", stage))

    def expect(self, patterns, timeout):
        if isinstance(patterns, list):
            if not any(event[0] == "execute" for event in self.events):
                raise AssertionError("benchmark marker awaited before execution")
            self.emit("PIPE_HINT_PASS")
            self.events.append(("app_pass",))
            return 0
        if patterns is pexpect.EOF:
            if self.bsg:
                self.emit("BSG PASS")
                self.events.append(("bsg_pass",))
            self.events.append(("eof",))
            self.alive = False
            return 0
        if self.last != "poweroff -f" or patterns.search("CORE[0] PASS") is None:
            raise AssertionError("unexpected terminal expectation")
        if not self.core:
            raise pexpect.TIMEOUT("mock guest never produced CORE PASS")
        self.emit("CORE[0] PASS")
        self.events.append(("core_pass",))
        return 0

    def close(self, force=False):
        self.events.append(("close", force))
        self.alive = False
        self.exitstatus = 0

    def isalive(self):
        return self.alive


class EmbeddedResumeTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="embedded-resume-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.elf = self.root / "exact-elf"
        self.elf.write_bytes(b"exact unchanged mock ELF\0" + bytes(range(256)) * 4)
        self.elf_sha = runner.sha256(self.elf)
        self.library = self.root / "exact-library"
        self.library.write_bytes(b"exact unchanged mock libz\0" + bytes(range(255, -1, -1)))
        self.library_sha = runner.sha256(self.library)
        self.nbf = self.root / "image.nbf"
        self.nbf.write_text("host fixture; never opened by a runner\n")
        self.transfer = self.root / "transfer"
        self.log = self.root / "run.log"

    def write_transfer(self, commands):
        self.transfer.write_text("\n".join(commands) + "\n")

    def argv(self, library=False):
        args = [str(self.nbf), str(self.transfer), self.elf_sha, str(self.log),
                "--bitstream-sha256", "b" * 64, "--loops", "3", "--repeats", "2",
                "--warmup", "2", "--policy", "preseed"]
        return args + (["--zlib-library", str(self.library), "--workload", "deflate"] if library else [])

    def embedded(self, library=False):
        return runner.embedded_commands(self.elf_sha, "plain", self.library_sha if library else None)

    def test_exact_header_source_and_hash_bind_only_three_fixed_commands(self):
        commands = self.embedded(library=True)
        self.assertEqual(commands, [
            f"# bp-resume-embedded-copy-v1 elf_sha256={self.elf_sha} source=plain library_sha256={self.library_sha}",
            f"cp /opt/bp-resume/plain {runner.GUEST_ELF}", f"chmod +x {runner.GUEST_ELF}"])
        self.write_transfer(commands)
        self.assertEqual(runner.validate_transfer(self.transfer, self.elf_sha),
                         {"source": "/opt/bp-resume/plain", "library_sha256": self.library_sha})
        with self.assertRaisesRegex(ValueError, "SHA-256/header mismatch"):
            runner.validate_transfer(self.transfer, "0" * 64)
        self.assertEqual(runner.embedded_description(compressed_commands(self.elf), self.elf_sha), None)

    def test_traversal_and_shell_injection_cannot_enter_source_namespace(self):
        invalid = ("", "../plain", "/plain", "/opt/bp-resume/plain", "plain/other", ".plain", "plain.elf",
                   "plain-other", "Plain", "1plain", "a" * 33, "plain;id", "plain$(id)", "plain`id`",
                   "plain && id", "plain\ntrue", "plain\ttrue", "plain'", "plain ")
        for source in invalid:
            with self.subTest(source=repr(source)):
                with self.assertRaises(ValueError):
                    runner.embedded_commands(self.elf_sha, source)
                crafted = [f"# bp-resume-embedded-copy-v1 elf_sha256={self.elf_sha} source={source}",
                           f"cp /opt/bp-resume/{source} {runner.GUEST_ELF}", f"chmod +x {runner.GUEST_ELF}"]
                self.write_transfer(crafted)
                with self.assertRaises(ValueError):
                    runner.validate_transfer(self.transfer, self.elf_sha)
        for source in ("a", "a" * 32, "plain_resources_2"):
            self.write_transfer(runner.embedded_commands(self.elf_sha, source))
            self.assertEqual(runner.validate_transfer(self.transfer, self.elf_sha)["source"],
                             runner.EMBEDDED_DIRECTORY + source)

    def test_extra_missing_reordered_or_modified_commands_are_rejected(self):
        original = self.embedded()
        changes = [original[:1], original[:2], original[1:], original + ["true"], original + [""],
                   [original[0], original[2], original[1]],
                   [original[0], original[1] + "; true", original[2]],
                   [original[0], original[1].replace("/plain ", "/other "), original[2]],
                   [original[0], original[1].replace(runner.GUEST_ELF, "/tmp/other"), original[2]],
                   [original[0], original[1], original[2].replace("+x", "777")],
                   [original[0], "true", *original[1:]],
                   [original[0], original[1].replace("cp ", "/bin/cp "), original[2]]]
        for commands in changes:
            with self.subTest(commands=commands):
                self.write_transfer(commands)
                with self.assertRaises(ValueError):
                    runner.validate_transfer(self.transfer, self.elf_sha)

    def test_unknown_duplicate_or_malformed_header_fields_and_hashes_are_rejected(self):
        original = self.embedded()
        bad_headers = [original[0].replace("copy-v1", "copy-v2"), " " + original[0], original[0] + " ",
                       original[0] + " source=plain", original[0] + " ignored=1",
                       original[0].replace(self.elf_sha, "A" * 64),
                       original[0].replace(self.elf_sha, "a" * 63),
                       original[0] + " library_sha256=" + "g" * 64,
                       original[0] + " library_sha256=" + self.library_sha + " library_sha256=" + self.library_sha]
        for header in bad_headers:
            with self.subTest(header=header):
                self.write_transfer([header, *original[1:]])
                with self.assertRaises(ValueError):
                    runner.validate_transfer(self.transfer, self.elf_sha)
        for invalid_hash in ("", "a" * 63, "A" * 64, "g" * 64, self.elf_sha + ";true"):
            with self.subTest(hash=invalid_hash):
                with self.assertRaises(ValueError):
                    runner.embedded_commands(invalid_hash, "plain")
                with self.assertRaises(ValueError):
                    runner.embedded_commands(self.elf_sha, "plain", invalid_hash)

    def test_optional_library_declaration_requires_exact_host_library_before_spawn(self):
        for declared, host, changed in ((False, True, False), (True, False, False), (True, True, True)):
            with self.subTest(declared=declared, host=host, changed=changed):
                self.library.write_bytes(b"host library bound before mutation")
                declared_hash = runner.sha256(self.library)
                self.write_transfer(runner.embedded_commands(self.elf_sha, "plain", declared_hash if declared else None))
                if changed:
                    self.library.write_bytes(b"different host library")
                with mock.patch.object(runner.pexpect, "spawn") as spawn:
                    with self.assertRaisesRegex(SystemExit, "exact --zlib-library"):
                        runner.main(self.argv(library=host))
                spawn.assert_not_called()
        self.library.write_bytes(b"matching host library")
        self.write_transfer(runner.embedded_commands(self.elf_sha, "plain", runner.sha256(self.library)))
        runner.validate_args(runner.parse_args(self.argv(library=True)))

    def test_library_commands_are_one_fixed_copy_and_recheck_host_bytes(self):
        self.write_transfer(self.embedded(library=True))
        args = runner.parse_args(self.argv(library=True))
        description = runner.validate_transfer(self.transfer, self.elf_sha)
        self.assertEqual(runner.library_commands(args, description), [f"cp /opt/bp-resume/libz.so.1 {runner.GUEST_ZLIB}"])
        self.library.write_bytes(b"changed after declaration validation")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            runner.library_commands(args, description)
        self.assertEqual(runner.library_commands(args, None), runner.library_transfer(self.library))

    def test_emitter_cli_roundtrips_embedded_with_and_without_library(self):
        for library in (False, True):
            with self.subTest(library=library):
                command = [sys.executable, str(HERE / "emit_resume_transfer.py"), str(self.elf),
                           "--embedded-source", "plain"]
                if library:
                    command += ["--zlib-library", str(self.library)]
                result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=True)
                self.assertEqual(result.stdout.splitlines(), self.embedded(library))
                self.transfer.write_text(result.stdout)
                runner.validate_args(runner.parse_args(self.argv(library)))
                repeat = subprocess.run(command, text=True, capture_output=True, timeout=10, check=True)
                self.assertEqual(result.stdout, repeat.stdout)
        for extra in (["--zlib-library", str(self.library)], ["--embedded-source", "../plain"]):
            result = subprocess.run([sys.executable, str(HERE / "emit_resume_transfer.py"), str(self.elf), *extra],
                                    text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_legacy_plain_and_gzip_wire_formats_remain_strict_and_hash_bound(self):
        encoded = base64.b64encode(self.elf.read_bytes()).decode()
        plain = [f": > {runner.GUEST_ELF}.b64"]
        plain += [f"echo '{encoded[i:i+512]}' >> {runner.GUEST_ELF}.b64" for i in range(0, len(encoded), 512)]
        plain += [f"base64 -d {runner.GUEST_ELF}.b64 > {runner.GUEST_ELF}", f"chmod +x {runner.GUEST_ELF}"]
        for valid in (plain, compressed_commands(self.elf)):
            self.write_transfer(valid)
            self.assertIsNone(runner.validate_transfer(self.transfer, self.elf_sha))
            with self.assertRaises(ValueError):
                runner.validate_transfer(self.transfer, "0" * 64)
            for changed in (valid + ["true"], valid[:1] + ["echo injected; true"] + valid[2:],
                            valid[:-1], [*valid[:-1], valid[-1].replace("+x", "777")],
                            [self.embedded()[0], *valid], ["x" * 769]):
                self.write_transfer(changed)
                with self.assertRaises(ValueError):
                    runner.validate_transfer(self.transfer, self.elf_sha)

    def mock_run(self, library=False, **console_options):
        self.write_transfer(self.embedded(library))
        args = runner.parse_args(self.argv(library))
        child = GuestConsole(args, **console_options)
        with mock.patch.object(runner.pexpect, "spawn", return_value=child) as spawn, mock.patch.object(
                runner, "expect_shell_prompt", side_effect=child.prompt):
            try:
                result = runner.main(self.argv(library))
            except Exception as error:
                result = error
        spawn.assert_called_once()
        status = json.loads(self.log.with_suffix(".log.status.json").read_text())
        return result, child, status

    def test_wrong_guest_elf_hash_fails_and_never_launches_application(self):
        for library in (False, True):
            with self.subTest(library=library):
                result, child, status = self.mock_run(library, elf_hash="0" * 64)
                self.assertIsInstance(result, pexpect.TIMEOUT)
                self.assertEqual(status["status"], "FAIL")
                self.assertNotIn(child.app, child.sent)
                self.assertNotIn("poweroff -f", child.sent)
                self.assertFalse(any(event[0] == "execute" for event in child.events))
                self.assertIn(("wrong_hash", runner.GUEST_ELF), child.events)
                self.assertIn(("close", True), child.events)

    def test_wrong_guest_library_hash_fails_before_elf_transfer_or_application(self):
        result, child, status = self.mock_run(True, library_hash="0" * 64)
        self.assertIsInstance(result, pexpect.TIMEOUT)
        self.assertEqual(status["status"], "FAIL")
        self.assertNotIn(child.app, child.sent)
        self.assertNotIn(runner.GUEST_ELF, child.copied)
        self.assertIn(("wrong_hash", runner.GUEST_ZLIB), child.events)
        self.assertFalse(any(event[0] == "execute" for event in child.events))

    def test_success_verifies_both_guest_hashes_before_execution_and_terminal_passes(self):
        result, child, status = self.mock_run(True)
        self.assertEqual(result, 0)
        self.assertEqual(status["status"], "PASS")
        self.assertEqual(status["transfer_encoding"], "embedded-copy-v1")
        self.assertEqual(status["zlib_transfer_encoding"], "embedded-copy-v1")
        self.assertEqual(status["embedded_elf_source"], "/opt/bp-resume/plain")
        self.assertEqual(status["elf_sha256"], self.elf_sha)
        self.assertEqual(status["zlib_library_sha256"], self.library_sha)
        execute = next(i for i, event in enumerate(child.events) if event[0] == "execute")
        for destination in (runner.GUEST_ELF, runner.GUEST_ZLIB):
            self.assertLess(child.events.index(("verified", destination)), execute)
        self.assertLess(child.events.index(("verified", runner.GUEST_ZLIB)),
                        child.events.index(("verified", runner.GUEST_ELF)))
        self.assertEqual([event[0] for event in child.events if event[0] in
                          ("execute", "app_pass", "core_pass", "bsg_pass", "eof")],
                         ["execute", "app_pass", "core_pass", "bsg_pass", "eof"])
        self.assertEqual(child.sent.count(f"cp /opt/bp-resume/libz.so.1 {runner.GUEST_ZLIB}"), 1)
        self.assertFalse(any("base64" in command or "gunzip" in command for command in child.sent))

    def test_plain_embedded_copy_completes_without_any_library_staging(self):
        result, child, status = self.mock_run()
        self.assertEqual(result, 0)
        self.assertEqual(status["status"], "PASS")
        self.assertEqual(status["transfer_encoding"], "embedded-copy-v1")
        self.assertNotIn("zlib_library_sha256", status)
        self.assertNotIn("zlib_transfer_encoding", status)
        self.assertEqual(child.verified, {runner.GUEST_ELF})
        self.assertFalse(any(runner.GUEST_ZLIB in command for command in child.sent))
        self.assertIn(("core_pass",), child.events)
        self.assertIn(("bsg_pass",), child.events)

    def test_benchmark_pass_cannot_replace_core_or_bsg_completion(self):
        for options in (dict(core=False), dict(bsg=False)):
            with self.subTest(options=options):
                result, child, status = self.mock_run(True, **options)
                self.assertIsInstance(result, Exception)
                self.assertEqual(status["status"], "FAIL")
                self.assertIn(("app_pass",), child.events)
                self.assertIn(child.app, child.sent)


if __name__ == "__main__":
    unittest.main()
