#!/usr/bin/env python3
"""Conditional full-line replay bounds for the measured Linux handoff."""

import json
import math
from pathlib import Path


INSTALL_CYCLES = 17
BEATS_PER_LINE = 8
LATENCY_SWEEP = (21, 41, 57, 65, 82, 164, 200)

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


def transport_bound(lines, slots, response_start):
    """Shared-channel lower bound, including the final eight-beat burst."""
    if not lines:
        return 0
    interval = max(float(BEATS_PER_LINE), float(response_start) / slots)
    return response_start + (lines - 1) * interval + BEATS_PER_LINE


def installer_bound(i_lines, d_lines, response_start, install_cycles=INSTALL_CYCLES):
    """Separate serial I/D installers after the first complete response."""
    return response_start + BEATS_PER_LINE + install_cycles * max(i_lines, d_lines)


def installed_by(deadline, response_start, install_cycles=INSTALL_CYCLES):
    available = deadline - response_start - BEATS_PER_LINE
    return max(0, math.floor(available / install_cycles))


def maximum_response_start_for_bulk(deadline, lines, slots, install_cycles=INSTALL_CYCLES):
    """Largest integer latency whose transport and installer both meet deadline."""
    valid = [
        latency
        for latency in range(deadline + 1)
        if max(
            transport_bound(lines, slots, latency),
            latency + BEATS_PER_LINE + install_cycles * lines,
        ) <= deadline
    ]
    return max(valid) if valid else None


def latency_row(values, response_start):
    total = values["unique_i"] + values["unique_d"]
    install = installer_bound(values["unique_i"], values["unique_d"], response_start)
    slot_sweep = {}
    for slots in range(1, 5):
        transport = transport_bound(total, slots, response_start)
        completion = max(transport, install)
        slot_sweep[str(slots)] = {
            "transport_lower_bound_cycles": transport,
            "separate_installer_lower_bound_cycles": install,
            "aggregate_lower_bound_cycles": completion,
            "fits_elapsed": completion <= values["elapsed"],
        }
    first_ready = response_start + BEATS_PER_LINE + INSTALL_CYCLES
    return {
        "assumed_request_to_first_response_beat_cycles": response_start,
        "earliest_one_line_ready": first_ready,
        "first_i_slack": values["first_i"] - first_ready,
        "first_d_slack": values["first_d"] - first_ready,
        "max_i_installs_before_first_i": installed_by(values["first_i"], response_start),
        "max_d_installs_before_first_d": installed_by(values["first_d"], response_start),
        "ideal_i_bulk_ready": response_start + BEATS_PER_LINE
        + INSTALL_CYCLES * values["unique_i"],
        "ideal_d_bulk_ready": response_start + BEATS_PER_LINE
        + INSTALL_CYCLES * values["unique_d"],
        "slot_sweep": slot_sweep,
    }


def analyze(name, values):
    installer_sensitivity = {}
    for cycles in (17, 19, 21, 25):
        bulk_ready = 41 + BEATS_PER_LINE + cycles * values["unique_i"]
        installer_sensitivity[str(cycles)] = {
            "maximum_response_start_for_first_i": values["first_i"]
            - BEATS_PER_LINE - cycles,
            "maximum_response_start_for_all_i_before_first_i_four_slots":
            maximum_response_start_for_bulk(
                values["first_i"], values["unique_i"], 4, cycles
            ),
            "conditional_41cycle_i_bulk_ready": bulk_ready,
            "conditional_41cycle_i_bulk_slack": values["first_i"] - bulk_ready,
            "conditional_41cycle_max_i_installs_before_first_i":
            installed_by(values["first_i"], 41, cycles),
        }
    return {
        "window": name,
        **values,
        "unique_lines": values["unique_i"] + values["unique_d"],
        "maximum_response_start_for_first_i": values["first_i"]
        - BEATS_PER_LINE - INSTALL_CYCLES,
        "installer_only_maximum_response_start_for_all_i_before_first_i":
        values["first_i"] - BEATS_PER_LINE - INSTALL_CYCLES * values["unique_i"],
        "maximum_response_start_for_all_i_before_first_i_by_slots": {
            str(slots): maximum_response_start_for_bulk(
                values["first_i"], values["unique_i"], slots
            )
            for slots in range(1, 5)
        },
        "maximum_response_start_for_first_d": values["first_d"]
        - BEATS_PER_LINE - INSTALL_CYCLES,
        "installer_sensitivity": installer_sensitivity,
        "latency_sweep": [latency_row(values, latency) for latency in LATENCY_SWEEP],
    }


def main():
    result = {
        "assumptions": {
            "request_to_first_response_beat_cycles": list(LATENCY_SWEEP),
            "axi_beats_per_64_byte_line": BEATS_PER_LINE,
            "installer_cycles_per_line_after_complete_response": INSTALL_CYCLES,
            "installer_cycle_sensitivity": [17, 19, 21, 25],
            "separate_i_d_installers": True,
            "transport_slots_are_shared": True,
            "physical_full_line_response_latency_is_unmeasured": True,
            "physical_41_cycle_value_is_load_to_use_not_full_line": True,
        },
        "windows": [analyze(name, values) for name, values in WINDOWS.items()],
    }
    text = json.dumps(result, indent=2) + "\n"
    Path(__file__).with_name("results.json").write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
