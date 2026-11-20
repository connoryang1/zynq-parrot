"""Check matrix identity and result validation without executing a simulator."""
from pathlib import Path
import tempfile
import unittest

from run_resume_retention_matrix import (
    MODEL, ROOT, guest_metrics, model_identity, patch_full_nbf, runtime_control,
    sha256, transport_scope,
)


class RetentionMatrixValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="retention-matrix-identity-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "obj_dir").mkdir()
        (self.root / "obj_dir" / MODEL).write_bytes(b"never executed")
        self.log = self.root / "build.log"
        self.stamp = self.root / "obj_dir/.build_config-nt2-nc4-cfge_bp_custom_cfg-trace1-axipipe-lat40-q4-icapture"
        self.stamp.touch()
        self.command = (
            "verilator --cc --trace-fst +define+BP_NUM_THREADS=2 "
            "+define+BP_NUM_CONTEXTS=4 +define+BP_AXI_MEM_PIPELINED "
            "+define+BP_CUSTOM_BASE_CFG=bp_unicore_zynqparrot_cfg_p "
            "+define+HP0_DATA_WIDTH=32 +define+ACLK_MHZ=20 "
            "+define+BP_AXI_MEM_READ_LATENCY=40 +define+BP_AXI_MEM_READ_QUEUE_DEPTH=4 "
            "+define+BP_ICACHE_REPLAY_DEMAND_CAPTURE=0 "
            + str(ROOT / "cosim/black-parrot-minimal-example/ps.cpp") + " "
            + str(ROOT / "cosim/black-parrot-minimal-example/v/top.v") + "\n")
        self.log.write_text(self.command)

    def test_macro_zero_is_enabled_ifdef_and_never_an_off_control(self):
        result = model_identity(self.root, self.log, "on", 40)
        self.assertEqual(result["capture"], "on")
        self.stamp.rename(self.stamp.with_name(self.stamp.name[:-len("-icapture")]))
        with self.assertRaisesRegex(ValueError, "capture mode"):
            model_identity(self.root, self.log, "off", 40)

    def test_rejects_model_stamp_latency_or_ambiguous_stamps(self):
        with self.assertRaisesRegex(ValueError, "model stamps"):
            model_identity(self.root, self.log, "on", 200)
        (self.root / "obj_dir/.build_config-stale").touch()
        with self.assertRaisesRegex(ValueError, "ambiguous model stamps"):
            model_identity(self.root, self.log, "on", 40)

    def test_rejects_build_command_topology_and_multiple_builds(self):
        self.log.write_text(self.command.replace("BP_NUM_CONTEXTS=4", "BP_NUM_CONTEXTS=2"))
        with self.assertRaisesRegex(ValueError, "topology/latency/depth"):
            model_identity(self.root, self.log, "on", 40)
        self.log.write_text(self.command * 2)
        with self.assertRaisesRegex(ValueError, "one exact"):
            model_identity(self.root, self.log, "on", 40)

    def test_runtime_patch_and_checksum_are_bound_to_requested_mode(self):
        text = (
            "ps.cpp: runtime patch address=0x80001230 value=0x1\n"
            "Mode: 0x1\nPrefix operations: 0x60\nResume cycles: 0x256\n"
            "Prefix checksum: 0x60\n")
        result = guest_metrics(text, 1, 0x80001230)
        self.assertEqual(result["resume_core_global_cycles"], 0x256)
        with self.assertRaisesRegex(ValueError, "checksum"):
            guest_metrics(text.replace("Prefix checksum: 0x60", "Prefix checksum: 0x61"), 1, 0x80001230)
        with self.assertRaisesRegex(ValueError, "runtime patch"):
            guest_metrics(text, 1, 0x80001238)
        with self.assertRaisesRegex(ValueError, "mode/operation"):
            guest_metrics(text, 0, 0x80001230)

    def test_tee_log_falls_back_to_actual_hashed_verilator_command_record(self):
        self.log.write_text("C++ build complete; Make's echoed command was outside tee\n")
        verfiles = self.root / "obj_dir" / (MODEL + "__verFiles.dat")
        # The real C record stores arguments without the executable name.
        arguments = self.command.strip().split(" ", 1)[1]
        verfiles.write_text('# Verilator dependency manifest\nC "' + arguments + '"\n')
        parsed = model_identity(self.root, self.log, "on", 40)
        source = parsed["verilator_command_source"]
        self.assertEqual(source["kind"], "verilator-command-record")
        self.assertEqual(source["path"], str(verfiles.resolve()))
        self.assertEqual(source["sha256"], sha256(verfiles))
        self.assertEqual(parsed["verilator_command"], arguments)
        self.assertEqual(self.log.read_text(), "C++ build complete; Make's echoed command was outside tee\n")

    def test_manifest_fallback_rejects_wrong_flags_or_missing_trace(self):
        self.log.write_text("completed build output\n")
        verfiles = self.root / "obj_dir" / (MODEL + "__verFiles.dat")
        for replacement in (self.command.replace("BP_AXI_MEM_READ_LATENCY=40", "BP_AXI_MEM_READ_LATENCY=200"),
                            self.command.replace("BP_NUM_CONTEXTS=4", "BP_NUM_CONTEXTS=2"),
                            self.command.replace("BP_ICACHE_REPLAY_DEMAND_CAPTURE=0", "UNRELATED=1"),
                            self.command.replace("--trace-fst", "--trace")):
            with self.subTest(command=replacement):
                verfiles.write_text('C "' + replacement.strip() + '"\n')
                with self.assertRaises(ValueError):
                    model_identity(self.root, self.log, "on", 40)

    def test_full_transport_binds_64_bit_gp_ports_and_actual_sources(self):
        full_command = (self.command.replace("HP0_DATA_WIDTH=32", "HP0_DATA_WIDTH=64")
                        .replace("black-parrot-minimal-example", "black-parrot-example")
                        .replace("--cc", "--cc +define+GP1_ENABLE=1 +define+GP2_ENABLE=1 "
                                 "+define+HP1_ENABLE=1 +define+WATCHDOG_ENABLE"))
        self.log.write_text(full_command)
        identity = model_identity(self.root, self.log, "on", 40, "full-burst")
        self.assertEqual(identity["axi_data_width_bits"], 64)
        self.assertEqual(identity["transport"], "full-burst")
        for wrong in (full_command.replace("HP0_DATA_WIDTH=64", "HP0_DATA_WIDTH=32"),
                      full_command.replace("GP2_ENABLE=1", "GP2_ENABLE=0"),
                      full_command.replace("black-parrot-example/ps.cpp", "black-parrot-minimal-example/ps.cpp")):
            with self.subTest(command=wrong):
                self.log.write_text(wrong)
                with self.assertRaises(ValueError):
                    model_identity(self.root, self.log, "on", 40, "full-burst")
        self.assertIn("functional/capacity diagnostic only", transport_scope("minimal-axil"))

    def test_offline_full_patch_reconstructs_exact_bytes_and_other_records(self):
        address = 0x80001230
        original = ("02_0000000000200008_0000000000000001\n"
                    "03_0000000080001228_0123456789abcdef\n"
                    "03_0000000080001230_ffffffffffffffff\n"
                    "03_0000000080001238_ffeeddccbbaa0099\n"
                    "fe_0000000000000000_0000000000000000\n"
                    "ff_0000000000000000_0000000000000000\n")

        def reconstruct(text):
            memory = {}
            for line in text.splitlines():
                op, target, value = line.split("_")
                if op != "03":
                    continue
                for offset, byte in enumerate(int(value, 16).to_bytes(8, "little")):
                    memory[int(target, 16) + offset] = byte
            return memory

        for mode in range(4):
            patched = patch_full_nbf(original, address, mode)
            memory = reconstruct(original)
            for offset, byte in enumerate(mode.to_bytes(8, "little")):
                memory[address + offset] = byte
            self.assertEqual(reconstruct(patched), memory)
            old_lines, new_lines = original.splitlines(), patched.splitlines()
            self.assertEqual([index for index, pair in enumerate(zip(old_lines, new_lines))
                              if pair[0] != pair[1]], [2])
        for text, target, mode in ((original, address + 1, 0), (original, address, 4),
                                   (original.replace("ffffffffffffffff", "fffffffffffffffe"), address, 0),
                                   (original.replace("03_0000000080001230_ffffffffffffffff\n", ""), address, 0)):
            with self.subTest(target=target, mode=mode):
                with self.assertRaises(ValueError):
                    patch_full_nbf(text, target, mode)

    def test_full_native_time_bounds_and_marker_without_minimal_patch_hook(self):
        for seconds in (240, 600):
            command, patch = runtime_control("/never/executed", "full-burst", seconds, 0x80001230, 2)
            self.assertEqual(command[1], "+c_args=prog.nbf " + str(seconds * 1000))
            self.assertEqual(patch["TARGET_RUNTIME_MS"], seconds * 1000)
            self.assertFalse(any(name.startswith("BSG_") for name in patch))
            text = ("ps.cpp: limiting target runtime to " + str(seconds * 1000) + " ms\n"
                    "Mode: 0x2\nPrefix operations: 0x60\nResume cycles: 0x100\nPrefix checksum: 0x60\n")
            self.assertEqual(guest_metrics(text, 2, 0x80001230, "full-burst", seconds)
                             ["resume_core_global_cycles"], 0x100)
            with self.assertRaisesRegex(ValueError, "native target runtime"):
                guest_metrics(text.replace(str(seconds * 1000), "0"), 2, 0x80001230, "full-burst", seconds)
        for seconds in (0, -1, 120, 601):
            with self.assertRaisesRegex(ValueError, "native timeout"):
                runtime_control("/never/executed", "full-burst", seconds, 0x80001230, 0)
        command, patch = runtime_control("/never/executed", "minimal-axil", 240, 0x80001230, 0)
        self.assertEqual(command[1], "+c_args=prog.nbf")
        self.assertEqual(patch["BSG_TRACE_TIMEOUT_S"], "240")
        self.assertEqual(patch["BSG_RUNTIME_PATCH_VALUE"], "0")


if __name__ == "__main__":
    unittest.main()
