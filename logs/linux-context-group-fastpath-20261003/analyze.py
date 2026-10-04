#!/usr/bin/env python3
"""Analyze persistent Linux-hosted context-group selector runs."""
import hashlib
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SAMPLES = 128
HANDOFFS_PER_SAMPLE = 256
NOMINAL_SELECTOR_OPS_PER_RUN = 2 * SAMPLES * HANDOFFS_PER_SAMPLE


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(path, expected_marker):
    text = path.read_text(errors="replace").replace("\r", "")
    summary_pattern = re.compile(
        r"CONTEXT_GROUP mode/min/median/p95/max/cycles_x100_per_handoff/"
        r"source_sc_failures/peer_sc_failures: "
        r"(resident|nonresident) " + r" ".join([r"(\d+)"] * 7))
    raw_pattern = re.compile(
        r"CONTEXT_GROUP_RAW mode=(resident|nonresident)((?: \d+)+)")
    summaries = {}
    for match in summary_pattern.finditer(text):
        mode = match.group(1)
        values = [int(value) for value in match.groups()[1:]]
        summaries[mode] = dict(zip(
            ["minimum", "median", "p95", "maximum", "display_x100",
             "source_sc_failures", "peer_sc_failures"], values))
    raw = {
        match.group(1): [int(value) for value in match.group(2).split()]
        for match in raw_pattern.finditer(text)
    }
    assert summaries.keys() == {"resident", "nonresident"}
    assert raw.keys() == summaries.keys()
    for mode, values in raw.items():
        assert len(values) == SAMPLES
        ordered = sorted(values)
        expected = {
            "minimum": ordered[0],
            "median": int(statistics.median(ordered)),
            "p95": ordered[(95 * SAMPLES) // 100],
            "maximum": ordered[-1],
        }
        assert all(summaries[mode][name] == value
                   for name, value in expected.items())
        summaries[mode].update({
            "samples": len(values),
            "median_cycles_per_handoff":
                statistics.median(values) / HANDOFFS_PER_SAMPLE,
            "p95_cycles_per_handoff_window":
                ordered[(95 * SAMPLES) // 100] / HANDOFFS_PER_SAMPLE,
            "aggregate_windows_over_2x_median": sum(
                value > 2 * statistics.median(values) for value in values),
        })
    return {
        "sha256": sha256(path),
        "marker_present": expected_marker in text,
        "core_pass": "CORE[0] PASS" in text,
        "probe_exit": int(re.search(r"PROBE_EXIT=(\d+)", text).group(1)),
        "modes": summaries,
    }


accepted = parse(HERE / "board.log", "[LINUX-CONTEXT-GROUP] PASS")
rejected = parse(HERE / "zero-retry-policy-rejection.log",
                 "[LINUX-CONTEXT-GROUP] FAIL")
status = json.loads((HERE / "board-status.json").read_text())
assert status["status"] == "PASS" and accepted["marker_present"]
assert accepted["core_pass"] and accepted["probe_exit"] == 0
assert rejected["marker_present"] and rejected["core_pass"]
assert rejected["probe_exit"] == 1

accepted_failures = sum(
    mode["source_sc_failures"] + mode["peer_sc_failures"]
    for mode in accepted["modes"].values())
rejected_failures = sum(
    mode["source_sc_failures"] + mode["peer_sc_failures"]
    for mode in rejected["modes"].values())
assert accepted_failures == 0 and rejected_failures == 1

baremetal = json.loads(
    (REPO / "logs/linux-atomic-fence-cost-20261003/analysis.json").read_text())
scheduler = json.loads(
    (REPO / "logs/linux-hot-scheduler-breakdown-20261003/analysis.json").read_text())
linux_scheduler_average = statistics.mean([
    scheduler["medians_physical_cycles"]["handoff_to_main"],
    scheduler["medians_physical_cycles"]["handoff_to_worker"],
])
baremetal_cycles = {
    state: baremetal["multiready"][state]["fpga"]
        ["median_aggregate_cycles"] / 258
    for state in ("resident", "nonresident")
}

comparison = {}
for state in ("resident", "nonresident"):
    hosted = accepted["modes"][state]["median_cycles_per_handoff"]
    comparison[state] = {
        "linux_hosted_cycles_per_handoff": hosted,
        "baremetal_cycles_per_handoff": baremetal_cycles[state],
        "linux_hosted_minus_baremetal_cycles": hosted - baremetal_cycles[state],
        "linux_hosted_percent_over_baremetal":
            100 * (hosted / baremetal_cycles[state] - 1),
        "linux_scheduler_over_linux_hosted_ratio":
            linux_scheduler_average / hosted,
        "microseconds_per_handoff_at_18mhz": hosted / 18,
    }

result = {
    "configuration": {
        "samples_per_mode_per_run": SAMPLES,
        "handoffs_per_sample": HANDOFFS_PER_SAMPLE,
        "timed_handoffs_per_run": NOMINAL_SELECTOR_OPS_PER_RUN,
        "spectator_context_ready_bit_preserved": True,
    },
    "accepted_run": accepted,
    "zero_retry_policy_rejection": rejected,
    "retry_observation_across_two_runs": {
        "nominal_selector_operations": 2 * NOMINAL_SELECTOR_OPS_PER_RUN,
        "observed_sc_failures": accepted_failures + rejected_failures,
        "failures_per_million_nominal_operations":
            1_000_000 * (accepted_failures + rejected_failures)
            / (2 * NOMINAL_SELECTOR_OPS_PER_RUN),
    },
    "comparison": comparison,
    "limits": [
        "The accepted PASS proves its context, register, syscall, ready-word, spectator-bit, exit, and core checks.",
        "The rejected transcript reports one recovered SC failure but does not print each hidden state predicate separately.",
        "The two runs retain normal Linux interrupts but do not identify which asynchronous event caused timing outliers or the one reservation failure.",
        "This is a userspace prototype inside one Linux process; Linux does not yet allocate, protect, reclaim, or account for the context group.",
    ],
}

output = json.dumps(result, indent=2) + "\n"
(HERE / "analysis.json").write_text(output)
print(output, end="")
