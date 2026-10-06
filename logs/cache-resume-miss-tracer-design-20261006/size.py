#!/usr/bin/env python3
"""Size a physical I/D demand-miss recorder for the current FPGA endpoint."""

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    paddr_bits = 34
    line_bytes = 64
    line_offset_bits = int(math.log2(line_bytes))
    line_address_bits = paddr_bits - line_offset_bits
    timestamp_bits = 32
    metadata_bits = 64 - timestamp_bits - line_address_bits
    depth_per_cache = 256
    record_bits = 64
    bits_per_cache = depth_per_cache * record_bits
    ramb18_bits = 18_432
    ramb18_per_cache = math.ceil(bits_per_cache / ramb18_bits)

    current_ramb36 = 82
    current_ramb18 = 3
    total_bram_tiles = 140
    added_ramb18 = 2 * ramb18_per_cache
    current_tiles = current_ramb36 + current_ramb18 / 2
    projected_tiles = current_ramb36 + (current_ramb18 + added_ramb18) / 2

    i_equiv = 174.47368421052633
    d_equiv = 143.16666666666666
    result = {
        "record": {
            "physical_address_bits": paddr_bits,
            "line_offset_bits": line_offset_bits,
            "line_address_bits": line_address_bits,
            "timestamp_bits": timestamp_bits,
            "metadata_bits_remaining": metadata_bits,
            "record_bits": record_bits,
            "timestamp_wrap_cycles": 2**timestamp_bits,
            "timestamp_wrap_seconds_at_18MHz": 2**timestamp_bits / 18_000_000,
        },
        "buffers": {
            "organization": "independent I and D 256x64 simple dual-port memories",
            "depth_per_cache": depth_per_cache,
            "bits_per_cache": bits_per_cache,
            "ramb18_per_cache": ramb18_per_cache,
            "added_ramb18": added_ramb18,
            "simultaneous_i_d_capture": True,
        },
        "coverage": {
            "instruction_refill_equivalents": i_equiv,
            "data_refill_equivalents": d_equiv,
            "instruction_depth_margin": depth_per_cache - math.ceil(i_equiv),
            "data_depth_margin": depth_per_cache - math.ceil(d_equiv),
            "instruction_depth_margin_percent": (depth_per_cache / math.ceil(i_equiv) - 1) * 100,
            "data_depth_margin_percent": (depth_per_cache / math.ceil(d_equiv) - 1) * 100,
        },
        "fpga": {
            "current_slice_luts": 50_016,
            "available_slice_luts": 53_200,
            "current_lut_headroom": 53_200 - 50_016,
            "current_ramb36": current_ramb36,
            "current_ramb18": current_ramb18,
            "current_bram_tiles": current_tiles,
            "projected_ramb18": current_ramb18 + added_ramb18,
            "projected_bram_tiles": projected_tiles,
            "available_bram_tiles": total_bram_tiles,
            "projected_bram_utilization_percent": projected_tiles / total_bram_tiles * 100,
            "current_routed_wns_ns": 4.827,
        },
        "capture_point": {
            "module": "import/black-parrot/bp_top/src/v/bp_unicore_lite.sv",
            "i_event": "mem_fwd_v_o[0] && mem_fwd_ready_and_i[0]",
            "d_event": "mem_fwd_v_o[1] && mem_fwd_ready_and_i[1]",
            "filter": "BedRock memory read with payload.prefetch == 0",
            "stored_address": "mem_fwd_header_o[source].addr[33:6]",
        },
        "limits": [
            "Refill-equivalent counts are not literal miss counts; overflow bits remain mandatory.",
            "The BRAM estimate assumes each independent 256x64 simple dual-port array maps to one RAMB18.",
            "LUT and placement impact require synthesis; 3,184 LUTs of arithmetic headroom do not guarantee slice fit.",
            "Request timestamps establish replay deadlines but do not directly report response completion or cache hits.",
        ],
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
