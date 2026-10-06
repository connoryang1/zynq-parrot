#!/usr/bin/env python3
"""Summarize the cold M-mode trap path from a confirmed-closed FST."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prefetch_overlap_vcd import read_header  # noqa: E402
from cache_overlap_vcd import rising_edges  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fst", type=Path)
    parser.add_argument("--confirmed-closed", action="store_true", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    names = {
        "clock": "be.clk_i",
        "reset": "be.reset_i",
        "dispatch_v": "be.scheduler.dispatch_pkt_cast_o.v",
        "dispatch_pc": "be.scheduler.dispatch_pkt_cast_o.pc",
        "dispatch_thread": "be.scheduler.dispatch_pkt_cast_o.thread_id",
        "commit_pc": "be.calculator.commit_pkt_cast_o.pc",
        "commit_npc": "be.calculator.commit_pkt_cast_o.npc",
        "commit_instret": "be.calculator.commit_pkt_cast_o.instret",
        "commit_exception": "be.calculator.commit_pkt_cast_o.exception",
        "commit_npc_w": "be.calculator.commit_pkt_cast_o.npc_w_v",
        "retire_pc": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.retire_pkt_cast_i.npc",
        "retire_queue": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.retire_pkt_cast_i.queue_v",
        "retire_instret": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.retire_pkt_cast_i.instret",
        "retire_ecall_m": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.retire_pkt_cast_i.exception.ecall_m",
        "exception_code_valid": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.exception_ecode_v_li",
        "exception_code": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.exception_ecode_li",
        "exception_redirect": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.exception_v_lo",
        "mtvec": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.mtvec_r.word_addr",
        "mepc": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.mepc_reg.data_o",
        "mcause": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.mcause_reg.data_o",
        "apc": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.apc_r",
        "core_npc": "be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.core_npc",
    }

    first = subprocess.Popen(["fst2vcd", str(args.fst)], stdout=subprocess.PIPE, text=True)
    try:
        selected, timescale = read_header(first.stdout, names)
    finally:
        first.stdout.close()
        first.terminate()
        first.wait()

    ids_path = args.fst.with_suffix(".machine-trap.ids")
    ids_path.write_text("\n".join(sorted({item[0] for item in selected.values()})) + "\n")
    awk = (
        'BEGIN {while ((getline k < ARGV[1]) > 0) wanted[k]=1; ARGV[1]=""} '
        '!body {print; if ($1=="$enddefinitions") body=1; next} '
        'substr($0,1,1)=="#" {print; next} '
        'substr($0,1,1)=="b" {if ($2 in wanted) print; next} '
        '{if (substr($0,2) in wanted) print}'
    )
    producer = subprocess.Popen(["fst2vcd", str(args.fst)], stdout=subprocess.PIPE)
    filtered = subprocess.Popen(
        ["awk", awk, str(ids_path)], stdin=producer.stdout,
        stdout=subprocess.PIPE, text=True,
    )
    producer.stdout.close()

    events = []
    last = None
    try:
        resolved, filtered_timescale = read_header(filtered.stdout, names)
        if resolved != selected or filtered_timescale != timescale:
            raise RuntimeError("filtered trace header mismatch")
        for cycle, timestamp, values in rising_edges(filtered.stdout, resolved):
            # Keep state transitions plus all activity in the test's main and
            # handler window.  The final state is retained even for a loop.
            key = tuple(values[name] for name in names if name not in {"clock", "reset"})
            near_test = any(
                0x80000220 <= values[name] <= 0x800003D0
                for name in ("dispatch_pc", "commit_pc", "retire_pc", "apc", "core_npc")
                if values[name] is not None
            )
            active = any(values[name] == 1 for name in (
                "retire_ecall_m", "exception_code_valid", "exception_redirect", "commit_exception"
            ))
            if near_test or active or key != last:
                events.append({"cycle": cycle, "timestamp": timestamp, **values})
            last = key
    finally:
        filtered.stdout.close()
        filtered.terminate()
        filtered.wait()
        producer.terminate()
        producer.wait()

    result = {
        "timescale": timescale,
        "signals": {name: full for name, (_, full) in selected.items()},
        "event_count": len(events),
        "events": events,
    }
    output = args.output or args.fst.with_suffix(".machine-trap.json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)
    for event in events[-24:]:
        print(
            event["cycle"], hex(event["dispatch_pc"]), hex(event["commit_pc"]),
            hex(event["retire_pc"]), event["retire_ecall_m"],
            event["exception_code_valid"], event["exception_code"],
            event["exception_redirect"], hex(event["mtvec"]),
            hex(event["mepc"]), hex(event["core_npc"]),
        )


if __name__ == "__main__":
    main()
