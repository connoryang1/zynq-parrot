#!/usr/bin/env python3
"""Build and run the shared-prefix I-cache replay controller gate."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def name(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verilator", type=Path,
                        default=Path("/home/coyang/zynq-parrot/install/bin/verilator"))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = root / "import/black-parrot/bp_top/src/v/bp_icache_replay_ctrl.sv"
    driver = Path(__file__).resolve().with_name("icache_replay_ctrl_driver.cpp")
    command = [str(args.verilator.resolve()), "--cc", "--exe", "--build", "--assert",
               "--trace-fst", "--top-module", "bp_icache_replay_ctrl", "--prefix",
               "Vbp_icache_replay_ctrl", "--Mdir", str(out / "obj"), "-j", "2",
               "-Wno-fatal", str(source), str(driver)]
    (out / "build-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (out / "build.log").open("w") as log:
        subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=180)
    executable = out / "obj/Vbp_icache_replay_ctrl"
    with (out / "run.log").open("w") as log:
        subprocess.run([str(executable)], cwd=out, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    if "[ICACHE-REPLAY-CTRL] PASS:" not in result:
        raise RuntimeError("controller gate exited without its acceptance marker")
    dependencies = {source, driver, Path(__file__).resolve()}
    for line in (out / "obj/Vbp_icache_replay_ctrl__verFiles.dat").read_text().splitlines():
        if line.startswith("S "):
            dependencies.add(Path(shlex.split(line)[-1]))
    waveform = out / "icache-replay-ctrl.fst"
    verification = {
        "scope": "Shared-prefix replay controller only; no UCE/core/FPGA acceptance",
        "source_sha256": {name(path, root): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(dependencies)},
        "artifact_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (out / "run.log", waveform, executable)
        },
        "passed": True,
    }
    (out / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(result, end="")


if __name__ == "__main__":
    main()
