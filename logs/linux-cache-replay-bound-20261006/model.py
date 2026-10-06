#!/usr/bin/env python3
"""Optimistic replay-capacity bounds for the measured Linux handoff traces."""

import json
import math
from pathlib import Path


MEMORY_CYCLES = 41
INSTALL_CYCLES = 17

WINDOWS = {
    "source_to_peer": {
        "elapsed": 11_379,
        "unique_i": 48,
        "unique_d": 3,
        "first_i": 1_006,
        "first_d": 2_920,
        "last_i": 11_422,
        "last_d": 7_080,
    },
    "peer_to_source": {
        "elapsed": 28_883,
        "unique_i": 215,
        "unique_d": 10,
        "first_i": 82,
        "first_d": 1_107,
        "last_i": 28_879,
        "last_d": 28_546,
    },
}


def transport_bound(lines, slots):
    """Work-conserving continuous lower bound used by RL-022."""
    if not lines:
        return 0
    return MEMORY_CYCLES * (1 + (lines - 1) / slots)


def installer_bound(i_lines, d_lines):
    """Separate ideal I/D installers, each serial after its first response."""
    return MEMORY_CYCLES + INSTALL_CYCLES * max(i_lines, d_lines)


def installed_by(deadline):
    """Maximum lines one installer could finish by a demand deadline."""
    return max(0, math.floor((deadline - MEMORY_CYCLES) / INSTALL_CYCLES))


def analyze(name, values):
    total = values["unique_i"] + values["unique_d"]
    slot_sweep = {}
    install = installer_bound(values["unique_i"], values["unique_d"])
    for slots in range(1, 5):
        transport = transport_bound(total, slots)
        slot_sweep[str(slots)] = {
            "transport_lower_bound_cycles": transport,
            "separate_installer_lower_bound_cycles": install,
            "aggregate_lower_bound_cycles": max(transport, install),
            "fits_elapsed": max(transport, install) <= values["elapsed"],
        }
    first_ready = MEMORY_CYCLES + INSTALL_CYCLES
    i_bulk_ready = MEMORY_CYCLES + INSTALL_CYCLES * values["unique_i"]
    d_bulk_ready = MEMORY_CYCLES + INSTALL_CYCLES * values["unique_d"]
    return {
        "window": name,
        **values,
        "unique_lines": total,
        "earliest_one_line_ready": first_ready,
        "first_i_slack": values["first_i"] - first_ready,
        "first_d_slack": values["first_d"] - first_ready,
        "ideal_i_bulk_ready": i_bulk_ready,
        "ideal_d_bulk_ready": d_bulk_ready,
        "i_bulk_slack_at_first_i": values["first_i"] - i_bulk_ready,
        "d_bulk_slack_at_first_d": values["first_d"] - d_bulk_ready,
        "max_i_installs_before_first_i": installed_by(values["first_i"]),
        "max_d_installs_before_first_d": installed_by(values["first_d"]),
        "four_slot_bulk_headroom": values["elapsed"]
        - slot_sweep["4"]["aggregate_lower_bound_cycles"],
        "slot_sweep": slot_sweep,
    }


def main():
    result = {
        "assumptions": {
            "memory_service_cycles": MEMORY_CYCLES,
            "installer_cycles_per_line": INSTALL_CYCLES,
            "cache_lines_are_64_bytes": True,
            "separate_i_d_installers": True,
            "transport_slots_are_shared": True,
        },
        "windows": [analyze(name, values) for name, values in WINDOWS.items()],
    }
    text = json.dumps(result, indent=2) + "\n"
    Path(__file__).with_name("results.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
