import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "sel4" / "run_blackparrot_rpc_sim.sh"


class Sel4RpcRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.work = Path(self.temporary.name)
        self.image = self.work / "image.nbf"
        self.image.write_bytes(b"test nbf\n")
        self.model = self.work / "model"
        self.model.write_text(
            "#!/bin/sh\n"
            "echo 'SEL4_RPC_ADAPTER path=hardware calls=256 total_cycles=512 cycles_per_call=2'\n"
            "echo 'SEL4_RPC_ADAPTER path=software-fallback calls=8 total_cycles=24 cycles_per_call=3'\n"
            "echo 'Test SEL4IPCRPC0002 passed'\n"
        )
        self.model.chmod(0o755)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        pgrep = self.bin / "pgrep"
        pgrep.write_text("#!/bin/sh\nexit \"${FAKE_PGREP_STATUS:-1}\"\n")
        pgrep.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self, pgrep_status):
        environment = os.environ.copy()
        environment.update({
            "BLACKPARROT_SIM": str(self.model),
            "FAKE_PGREP_STATUS": str(pgrep_status),
            "PATH": str(self.bin) + os.pathsep + environment["PATH"],
        })
        return environment

    def test_identity_header_survives_model_output(self):
        output = self.work / "result.log"
        result = subprocess.run(
            [str(RUNNER), str(self.image), str(output)],
            env=self.environment(1), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        transcript = output.read_text()
        model_hash = hashlib.sha256(self.model.read_bytes()).hexdigest()
        image_hash = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.assertTrue(transcript.startswith("SEL4_RPC_SIM "))
        self.assertIn(f"model_sha256={model_hash}", transcript)
        self.assertIn(f"image_sha256={image_hash}", transcript)
        self.assertEqual(transcript.count("Test SEL4IPCRPC0002 passed"), 1)

    def test_concurrent_rejection_preserves_existing_log(self):
        output = self.work / "result.log"
        output.write_text("preserve me\n")
        result = subprocess.run(
            [str(RUNNER), str(self.image), str(output)],
            env=self.environment(0), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simulator is already running", result.stdout)
        self.assertEqual(output.read_text(), "preserve me\n")


if __name__ == "__main__":
    unittest.main()
