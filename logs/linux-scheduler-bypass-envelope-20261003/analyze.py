#!/usr/bin/env python3
"""Derive the workload envelope for replacing hot Linux handoffs."""
import json
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


SOURCE_PATHS = {
    "linux_scheduler": "logs/linux-hot-scheduler-breakdown-20261003/analysis.json",
    "dynamic_dispatch": "logs/linux-dynamic-context-target-20261003/analysis.json",
    "ready_selection": "logs/linux-atomic-fence-cost-20261003/analysis.json",
    "hosted_context_group": "logs/linux-context-group-fastpath-20261003/analysis.json",
}


def load(relative):
    return json.loads((REPO / relative).read_text())


scheduler = load(SOURCE_PATHS["linux_scheduler"])
dynamic = load(SOURCE_PATHS["dynamic_dispatch"])
selector = load(SOURCE_PATHS["ready_selection"])
hosted = load(SOURCE_PATHS["hosted_context_group"])

linux = scheduler["medians_physical_cycles"]
derived = scheduler["derived_physical_cycles"]
direct = dynamic["median_cycles_per_handoff"]
linux_handoff = (linux["handoff_to_main"] + linux["handoff_to_worker"]) / 2
alternate_task = (
    derived["handoff_to_main_beyond_no_peer_yield"]
    + derived["handoff_to_worker_beyond_no_peer_yield"]
) / 2

costs = {
    "linux_same_mm_handoff_average": linux_handoff,
    "optimistic_kernel_only_floor": linux["sched_yield_no_user_peer"],
    "optimistic_syscall_plus_direct_resident_floor": (
        linux["gettid_syscall"] + direct["register_resident"]
    ),
    "direct_register_resident": direct["register_resident"],
    "direct_register_nonresident": direct["register_nonresident"],
    "general_ready_selector_resident": hosted["comparison"]["resident"]
        ["linux_hosted_cycles_per_handoff"],
    "general_ready_selector_nonresident": hosted["comparison"]["nonresident"]
        ["linux_hosted_cycles_per_handoff"],
    "fair_three_context_round_robin": selector["roundrobin_three_context"]["fpga"]
        ["median_cycles_per_operation"],
}


def speedup(work, handoff):
    return (work + linux_handoff) / (work + handoff)


work_intervals = [0, 100, 500, 1000, 5000, 10000, 50000, 100000]
mode_names = [
    "optimistic_kernel_only_floor",
    "optimistic_syscall_plus_direct_resident_floor",
    "general_ready_selector_resident",
    "general_ready_selector_nonresident",
    "fair_three_context_round_robin",
]
table = []
for work in work_intervals:
    row = {"useful_work_cycles_between_handoffs": work}
    row.update({name: speedup(work, costs[name]) for name in mode_names})
    table.append(row)


def maximum_work_for_speedup(handoff, target):
    # (work + linux) / (work + replacement) >= target
    return (linux_handoff - target * handoff) / (target - 1)


thresholds = {}
for name in ["general_ready_selector_resident", "general_ready_selector_nonresident",
             "fair_three_context_round_robin"]:
    thresholds[name] = {
        f"maximum_work_cycles_for_at_least_{target:g}x":
            maximum_work_for_speedup(costs[name], target)
        for target in (2.0, 1.5, 1.1)
    }

components = {
    "counter_pair": linux["cycle_read_pair"],
    "minimal_syscall_beyond_counter": derived["gettid_minus_counter"],
    "yield_scheduler_path_beyond_minimal_syscall":
        derived["yield_scheduler_path_beyond_gettid"],
    "alternate_task_selection_switch_and_return": alternate_task,
}

assert abs(sum(components.values()) - linux_handoff) < 1e-9
for state in ("resident", "nonresident"):
    accepted = selector["multiready"][state]["fpga"]
    assert accepted["all_rows_correct"] and accepted["custom_pass"]
    assert accepted["core_pass"]
    assert accepted["final_operation_sc_failures_sum"] == 0
fair = selector["roundrobin_three_context"]["fpga"]
assert fair["all_rows_correct"] and fair["all_three_contexts_completed"]
assert fair["custom_pass"] and fair["core_pass"]
assert fair["final_operation_sc_failures_sum"] == 0

result = {
    "source_measurements": {
        name: {
            "path": path,
            "sha256": hashlib.sha256((REPO / path).read_bytes()).hexdigest(),
        }
        for name, path in SOURCE_PATHS.items()
    },
    "linux_handoff_component_cycles": components,
    "linux_handoff_component_fraction": {
        name: value / linux_handoff for name, value in components.items()
    },
    "mode_cost_cycles": costs,
    "switch_only_linux_over_replacement_ratio": {
        name: linux_handoff / value for name, value in costs.items()
        if name != "linux_same_mm_handoff_average"
    },
    "workload_speedup_over_linux": table,
    "useful_work_thresholds": thresholds,
    "wall_time_microseconds_at_18mhz": {
        name: value / 18 for name, value in costs.items()
    },
    "limits": [
        "All values are derived from separately accepted physical FPGA medians; this is not a new board run.",
        "The kernel-only floor assumes the entire measured alternate-task delta can be removed, which is optimistic.",
        "The syscall-plus-direct floor adds a minimal gettid syscall to direct dispatch; a real context ABI can only cost more.",
        "Workload rows model one handoff after a fixed amount of useful work and exclude cache, I/O, fault, and interrupt effects.",
        "The bare-metal selector's retry counters cover only each context's final operation; hosted aggregate retry evidence is recorded separately.",
    ],
}

text = json.dumps(result, indent=2) + "\n"
(HERE / "analysis.json").write_text(text)
print(text, end="")
