#!/usr/bin/env python3
"""Static descriptive figure from the pinned CLOSED comparison; never runs a model."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import StrMethodFormatter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
INPUT = ROOT / "research/resume-data-reuse-latency200-20261120/closed-comparison/results.json"
INPUT_SHA = "acbdd8a0d32617e69b9601cc5b594cc4780b288c53cec18f86dfd59b317c3f1f"
ELF_SHA = "f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd"
NBF_SHA = "18dbba12d432e6cfde94e7a16887d52f4e6edf0114b21a4fd227c0fbe4bc103d"
CAPTION = (
    "Same checked 32 KiB private lookup corpus per actor; 4 logical actors / 2 resident slots; capture off.\n"
    "Model: one L2 bank, 64-bit beats, queue depth 4. Physical reference: two L2 banks; no FPGA projection.\n"
    "A: complete timed ring, 32 requests and handoffs. B: median across 1,711 accepted timed D-cache misses.\n"
    "First accepted D-cache fill beat is not necessarily the requested critical word or load-ready time.\n"
    "Separate descriptive metrics; no causal stall partition or projected prefetch speedup."
)


def record(path):
    path = Path(path)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    assert record(INPUT)["sha256"] == INPUT_SHA, "closed comparison changed"
    data = json.loads(INPUT.read_text())
    assert data["state"] == "closed-complete-fixed-footprint-latency-comparison"
    assert all(data["fixed_input_identities"].values())
    assert data["timed_reference_semantic_sequence_identical"]
    for label in ("40", "200"):
        session_binding = data["input_bindings"][label]["session.json"]
        path = Path(session_binding["path"])
        assert record(path)["sha256"] == session_binding["sha256"], "session changed"
        session = json.loads(path.read_text())
        assert session["program"]["elf"]["sha256"] == ELF_SHA
        assert session["runtime_nbf"]["sha256"] == NBF_SHA
        assert session["footprint_kib"] == 32
        assert (session["physical_slots"], session["logical_contexts"]) == (2, 4)
    versions = {}
    for line in (HERE / "requirements.txt").read_text().splitlines():
        name, expected = line.split("==")
        actual = importlib.metadata.version(name)
        assert actual == expected, f"dependency mismatch: {name} {actual} != {expected}"
        versions[name] = actual
    ring = [data["complete_ring_cycles"][label] for label in ("40", "200")]
    first = [data["service_intervals"][label]["timed_ring"]["misses_accepted_in_window"]
             ["miss_to_first_accepted_beat_cycles"]["median"] for label in ("40", "200")]
    assert ring == [431132, 705445] and first == [61, 221]
    for label in ("40", "200"):
        assert data["service_intervals"][label]["timed_ring"]["misses_accepted_in_window"]["misses"] == 1711
    rows = []
    for label, complete, response in zip((40, 200), ring, first):
        rows += [dict(panel="A", setting_model_ticks=label, metric="complete_timed_ring", scope="32_requests_and_handoffs", units="core_global_cycles", value=complete),
                 dict(panel="B", setting_model_ticks=label, metric="median_accepted_D_miss_to_first_accepted_Dcache_fill_beat", scope="1711_timed_D_misses", units="core_global_cycles", value=response)]
    with (out / "data.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "closed-resume-latency-20261120"})
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 6.2))
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.36, top=0.84, wspace=0.46)
    colors = ["#376895", "#b16a38"]
    specs = [("A  Complete fixed ring", ring, 800000, [0, 200000, 400000, 600000, 800000],
              "Complete ring (core-global cycles)"),
             ("B  Median accepted D-miss service", first, 260, [0, 50, 100, 150, 200, 250],
              "Miss → first accepted D-fill beat (cycles)")]
    for ax, (title, values, high, ticks, ylabel) in zip(axes, specs):
        bars = ax.bar([0, 1], values, width=0.54, color=colors, zorder=3)
        ax.set_title(title, loc="left", fontsize=12, pad=15)
        ax.set_xticks([0, 1], ["40", "200"])
        ax.set_xlabel("Configured first-response setting (model ticks)", labelpad=10)
        ax.set_ylabel(ylabel, labelpad=9)
        ax.set_ylim(0, high)
        ax.set_yticks(ticks)
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.grid(axis="y", color="#dddddd", linewidth=0.7, zorder=0)
        ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=5, fontsize=11)
    fig.suptitle("Controlled memory latency: one fixed, complete synthetic workload", fontsize=14, y=0.96)
    fig.text(0.10, 0.26, CAPTION, fontsize=9.1, va="top", linespacing=1.6)
    fixed_date = datetime(2026, 11, 20, tzinfo=timezone.utc)
    fig.savefig(out / "latency-summary.svg", metadata={"Date": fixed_date.isoformat(), "Description": CAPTION})
    svg = out / "latency-summary.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    fig.savefig(out / "latency-summary.png", dpi=200, metadata={"Description": CAPTION})
    fig.savefig(out / "latency-summary.pdf", metadata={"CreationDate": fixed_date, "ModDate": fixed_date, "Subject": CAPTION})
    plt.close(fig)
    manifest = {"state": "closed-descriptive-two-panel-figure", "input": record(INPUT),
                "workload_identity": {"elf_sha256": ELF_SHA, "patched_nbf_sha256": NBF_SHA,
                    "private_bytes_per_actor": 32768, "logical_actors": 4, "resident_slots": 2,
                    "model_l2_banks": 1, "physical_reference_l2_banks": 2,
                    "memory_beat_bits": 64, "memory_queue_depth": 4, "capture": "off"},
                "source": record(__file__), "dependency_lock": record(HERE / "requirements.txt"),
                "python": platform.python_version(), "dependencies": versions,
                "font": record(font_manager.findfont("DejaVu Sans")),
                "caption": CAPTION, "outputs": {name: record(out / name) for name in
                    ("data.csv", "latency-summary.svg", "latency-summary.png", "latency-summary.pdf")}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Wrote two-panel figure, CSV and bound manifest to", out)


if __name__ == "__main__":
    main()
