#!/usr/bin/env python3
"""Stream focused FP-register events from a BlackParrot VCD on stdin.

Intended usage::

    fst2vcd dump.fst | python3 tools/fp_regfile_vcd_events.py --reg 1

The script avoids materializing a potentially multi-gigabyte VCD and reports
the physical-thread tag and data at the FP register-file write/read boundary.
"""

from __future__ import annotations

import argparse
import re
import sys


WATCH = {
    "write_v": ".be.scheduler.fp_regfile.rd_w_v_i",
    "write_tid": ".be.scheduler.fp_regfile.rd_thread_id_i",
    "write_reg": ".be.scheduler.fp_regfile.rd_addr_i",
    "write_data": ".be.scheduler.fp_regfile.rd_data_i",
    "read_v": ".be.scheduler.fp_regfile.rs_r_v_i",
    "read0_tid": ".be.scheduler.fp_regfile.rs_thread_id_i[0]",
    "read0_reg": ".be.scheduler.fp_regfile.rs_addr_i[0]",
    "read0_data": ".be.scheduler.fp_regfile.rs_data_o[0]",
    "dispatch_v": ".be.scheduler.dispatch_pkt_cast_o.v",
    "dispatch_tid": ".be.scheduler.dispatch_pkt_cast_o.thread_id",
    "dispatch_pc": ".be.scheduler.dispatch_pkt_cast_o.pc",
    "current_tid": ".be.current_physical_thread_id_lo",
    "current_vctx": ".be.current_virtual_context_id_r",
    "dispatch_rs1": ".be.scheduler.dispatch_pkt_cast_o.rs1",
    "iwb_v": ".be.iwb_pkt.ird_w_v",
    "iwb_tid": ".be.iwb_pkt.thread_id",
    "iwb_reg": ".be.iwb_pkt.rd_addr",
    "iwb_data": ".be.iwb_pkt.rd_data",
    "ctxtsw": ".be.commit_pkt.ctxtsw",
}


def parse_value(raw: str) -> int | None:
    return int(raw, 2) if raw and set(raw) <= {"0", "1"} else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reg", type=int, default=1,
                        help="FP register number, or -1 for every FP write/read")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--pc", type=lambda value: int(value, 0),
                        help="also report dispatch operand data for this PC")
    parser.add_argument("--all-dispatch", action="store_true",
                        help="report every dispatch in the selected cycle window")
    parser.add_argument("--int-reg", type=int,
                        help="also report integer writeback to this register")
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--show-signals", action="store_true")
    args = parser.parse_args()

    selected: dict[str, str] = {}
    scopes: list[str] = []
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")
    var_re = re.compile(r"\$var\s+\w+\s+\d+\s+(\S+)\s+(.+?)\s+\$end")

    for raw in sys.stdin:
        line = raw.rstrip()
        if "$enddefinitions" in line:
            break
        if "$scope" in line:
            match = scope_re.search(line)
            if match:
                scopes.append(match.group(1))
        elif "$upscope" in line:
            if scopes:
                scopes.pop()
        elif "$var" in line:
            match = var_re.search(line)
            if not match:
                continue
            code, name = match.groups()
            full = ".".join(scopes + [name.split()[0]])
            for label, suffix in WATCH.items():
                if full.endswith(suffix) and label not in selected:
                    selected[label] = code

    missing = sorted(set(WATCH) - set(selected))
    if missing:
        print("missing: " + ", ".join(missing), file=sys.stderr)
    if args.show_signals:
        for label in sorted(selected):
            print(f"signal {label}={selected[label]}", file=sys.stderr)

    labels_by_code: dict[str, list[str]] = {}
    for label, code in selected.items():
        labels_by_code.setdefault(code, []).append(label)

    values: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    last_write = None
    last_read = None
    last_dispatch = None
    last_iwb = None
    samples = 0
    selected_changes = 0
    write_asserts = 0

    def sample() -> None:
        nonlocal last_write, last_read, last_dispatch, last_iwb, samples, write_asserts
        samples += 1
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            return
        if args.max_cycle is not None and cycle > args.max_cycle:
            return

        write = None
        write_reg = values.get("write_reg")
        if (values.get("write_v") == 1
                and (args.reg < 0 or write_reg == args.reg)):
            write_asserts += 1
            write = (write_reg, values.get("write_tid"), values.get("write_data"))
        if write is not None and write != last_write:
            data = write[2]
            data_text = "x" if data is None else f"0x{data:x}"
            print(
                f"cycle={cycle} fp_write f{write[0]} tid={write[1]} data={data_text}"
                f" current_tid={values.get('current_tid')} vctx={values.get('current_vctx')}"
            )
        last_write = write

        read_v = values.get("read_v")
        read = None
        read_reg = values.get("read0_reg")
        if (read_v is not None and (read_v & 1)
                and (args.reg < 0 or read_reg == args.reg)):
            read = (
                read_reg,
                values.get("read0_tid"),
                values.get("read0_data"),
                values.get("dispatch_pc"),
                values.get("dispatch_tid"),
            )
        if read is not None and read != last_read:
            data = read[2]
            data_text = "x" if data is None else f"0x{data:x}"
            pc_text = "x" if read[3] is None else f"0x{read[3]:x}"
            print(
                f"cycle={cycle} fp_read f{read[0]} tid={read[1]} data={data_text}"
                f" dispatch_pc={pc_text} dispatch_tid={read[4]}"
                f" current_tid={values.get('current_tid')} vctx={values.get('current_vctx')}"
            )
        last_read = read

        dispatch = None
        dispatch_pc = values.get("dispatch_pc")
        if ((args.pc is not None or args.all_dispatch)
                and values.get("dispatch_v") == 1
                and (args.all_dispatch or dispatch_pc == args.pc)):
            dispatch = (
                dispatch_pc,
                values.get("dispatch_tid"),
                values.get("dispatch_rs1"),
            )
        if dispatch is not None and dispatch != last_dispatch:
            data = dispatch[2]
            data_text = "x" if data is None else f"0x{data:x}"
            pc_text = "x" if dispatch[0] is None else f"0x{dispatch[0]:x}"
            print(
                f"cycle={cycle} dispatch pc={pc_text} tid={dispatch[1]}"
                f" rs1={data_text} current_tid={values.get('current_tid')}"
                f" vctx={values.get('current_vctx')}"
            )
        last_dispatch = dispatch

        iwb = None
        if (args.int_reg is not None and values.get("iwb_v") == 1
                and values.get("iwb_reg") == args.int_reg):
            iwb = (values.get("iwb_tid"), values.get("iwb_data"))
        if iwb is not None and iwb != last_iwb:
            data = iwb[1]
            data_text = "x" if data is None else f"0x{data:x}"
            print(
                f"cycle={cycle} int_write x{args.int_reg} tid={iwb[0]}"
                f" data={data_text} current_tid={values.get('current_tid')}"
                f" vctx={values.get('current_vctx')}"
            )
        last_iwb = iwb

    for raw in sys.stdin:
        line = raw.rstrip()
        if not in_values:
            if "$dumpvars" in line:
                in_values = True
            continue
        if not line:
            continue
        if line[0] == "#":
            sample()
            current_time = int(line[1:])
            if args.max_cycle is not None and current_time // args.period > args.max_cycle:
                return 0
            continue
        if line[0] in "bB":
            parts = line.split()
            if len(parts) != 2:
                continue
            value, code = parse_value(parts[0][1:]), parts[1]
        elif line[0] in "01xXzZ":
            value, code = parse_value(line[0]), line[1:]
        else:
            continue
        for label in labels_by_code.get(code, []):
            values[label] = value
            selected_changes += 1
    sample()
    if args.show_signals:
        print(
            f"summary samples={samples} selected_changes={selected_changes}"
            f" write_assert_samples={write_asserts}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
