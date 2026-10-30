import copy
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = importlib.util.spec_from_file_location(
    "emit_icache_prefix_header", HERE / "emit_icache_prefix_header.py"
)
EMITTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EMITTER)


class IcachePrefixTest(unittest.TestCase):
    def setUp(self):
        self.result = json.loads(
            (ROOT / "logs/cache-resume-trace-model-20261030/results.json").read_text()
        )

    def test_committed_header_matches_model(self):
        generated = EMITTER.render(self.result)
        committed = (
            HERE / "opensbi-platform/blackparrot/icache_prefix.h"
        ).read_text()
        self.assertEqual(generated, committed)
        self.assertEqual(generated.count("UL,"), 63)

    def test_rejects_misaligned_line(self):
        malformed = copy.deepcopy(self.result)
        malformed["fixed_shared_prefix"]["lines"][0]["paddr"] += 1
        with self.assertRaisesRegex(ValueError, "not line aligned"):
            EMITTER.render(malformed)

    def test_enable_switch_reaches_platform_c_compilation(self):
        objects = (
            HERE / "opensbi-platform/blackparrot/objects.mk"
        ).read_text()
        self.assertIn(
            "platform-cflags-y += "
            "-DBP_ICACHE_PREFIX_ENABLE=$(BP_ICACHE_PREFIX_ENABLE)",
            objects,
        )


if __name__ == "__main__":
    unittest.main()
