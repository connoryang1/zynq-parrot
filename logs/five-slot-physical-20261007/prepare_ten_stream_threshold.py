#!/usr/bin/env python3
"""Generate exact-node-count variants for the ten-stream hardware failure."""

from pathlib import Path
import argparse
import hashlib
import json
import subprocess


repo = Path(__file__).resolve().parents[2]
source = repo / "logs/prefetch-mlatency-20260926/board-collateral/source/candidate-k3"
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)

source_manifest = json.loads((source / "manifest.json").read_text())
base = source / "mt_dependent_stream_benchmark_fpga.nbf"
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(base) == source_manifest["sha256"][base.name]
address = int(source_manifest["config_patch_address"], 0)
patcher = repo / "codex-skills/bp-fpga-synthesis/scripts/patch_nbf_bytes.py"

rows = []
# The first ascending sweep located a 96/97 transition, but fresh-overlay
# controls showed that preceding short runs prime state which a target reset
# does not clear. Generate the whole 64--112 interval so cold and primed
# boundaries can be measured from identical program images.
step_counts = (4, 8, 16, 32, *range(64, 113), 128)
for steps in step_counts:
    nodes = steps * 10
    value = 3 | (10 << 8) | (nodes << 16)
    config = out / f"config-k10-m3-steps{steps}.bin"
    nbf = out / f"dep-k10-m3-steps{steps}.nbf"
    config.write_bytes(value.to_bytes(8, "little"))
    subprocess.run([
        "python3", str(patcher), str(base), str(nbf),
        "--patch", f"{address:#x}:{config}",
    ], check=True)
    rows.append({
        "steps_per_stream": steps,
        "nodes": nodes,
        "config_hex": f"0x{value:016x}",
        "nbf": nbf.name,
        "sha256": digest(nbf),
    })

manifest = {
    "source": str(base.relative_to(repo)),
    "source_sha256": digest(base),
    "config_address": hex(address),
    "rows": rows,
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
