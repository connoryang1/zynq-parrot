#!/usr/bin/env python3
"""Print focused BE detector hazard state for a VCD cycle window."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v", "disp_v"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "disp_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "disp_tid"),
    ("be.scheduler.issue_pkt_cast_o.pc", "issue_pc"),
    ("be.scheduler.issue_pkt_cast_o.thread_id", "issue_tid"),
    ("be.scheduler.issue_pkt_cast_o.csrw", "issue_csrw"),
    ("be.scheduler.issue_pkt_cast_o.decode.csr_w_v", "issue_csr_w"),
    ("be.scheduler.issue_pkt_cast_o.decode.pipe_mem_early_v", "issue_mem_e"),
    ("be.scheduler.issue_pkt_cast_o.decode.pipe_mem_final_v", "issue_mem_f"),
    ("be.detector.check_thread_id_li", "det_tid"),
    ("be.detector.decode.pipe_mem_early_v", "det_mem_e"),
    ("be.detector.decode.pipe_mem_final_v", "det_mem_f"),
    ("be.detector.csr_rs1_haz_v", "csr_rs1_haz"),
    ("be.detector.csr_trans_haz_v", "csr_trans_haz"),
    ("be.detector.control_haz_v", "control_haz"),
    ("be.detector.hazard_v_o", "hazard"),
    ("be.detector.dep_thread_id_r[0]", "dep0_tid"),
    ("be.detector.dep_status_r[0].trans_info_v", "dep0_trans"),
    ("be.detector.dep_thread_id_r[1]", "dep1_tid"),
    ("be.detector.dep_status_r[1].trans_info_v", "dep1_trans"),
    ("be.detector.dep_thread_id_r[2]", "dep2_tid"),
    ("be.detector.dep_status_r[2].trans_info_v", "dep2_trans"),
    ("be.detector.dep_thread_id_r[3]", "dep3_tid"),
    ("be.detector.dep_status_r[3].trans_info_v", "dep3_trans"),
    ("be.calculator.reservation_r.pc", "res_pc"),
    ("be.calculator.reservation_r.v", "res_v"),
    ("be.calculator.reservation_r.thread_id", "res_tid"),
    ("be.calculator.pipe_mem.eaddr", "mem_eaddr"),
    ("be.calculator.pipe_mem.trans_info_cast_i.translation_en", "mem_trans_en"),
    ("be.calculator.pipe_mem.trans_info_cast_i.priv_mode", "mem_priv"),
    ("be.calculator.pipe_mem.trans_info_cast_i.base_ppn", "mem_base_ppn"),
    ("be.calculator.commit_pkt_cast_o.pc", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.instret", "instret"),
    ("be.calculator.commit_pkt_cast_o.csrw", "commit_csrw"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.is_debug_mode", "csr0_debug"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.dcsr_lo.mprven", "csr0_mprven"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.dcsr_li.mprven", "csr0_li_mprven"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.dcsr_n.mprven", "csr0_n_mprven"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.csr_w_v_li", "csr0_w"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.csr_addr_li", "csr0_addr"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.csr_data_li", "csr0_data"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.mstatus_lo.mprv", "csr0_mprv"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.mstatus_lo.mpp", "csr0_mpp"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.satp_lo.mode", "csr0_satp_mode"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.satp_lo.asid", "csr0_asid"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.satp_lo.ppn", "csr0_ppn"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.trans_info_cast_o.translation_en", "csr0_trans_en"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.is_debug_mode", "csr1_debug"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.dcsr_lo.mprven", "csr1_mprven"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.dcsr_li.mprven", "csr1_li_mprven"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.dcsr_n.mprven", "csr1_n_mprven"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.csr_w_v_li", "csr1_w"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.csr_addr_li", "csr1_addr"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.csr_data_li", "csr1_data"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.mstatus_lo.mprv", "csr1_mprv"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.mstatus_lo.mpp", "csr1_mpp"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.satp_lo.mode", "csr1_satp_mode"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.satp_lo.asid", "csr1_asid"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.satp_lo.ppn", "csr1_ppn"),
    ("be.calculator.pipe_sys.csr.gen_csr[1].csr_inst.trans_info_cast_o.translation_en", "csr1_trans_en"),
]


def parse_header(path: str):
    scopes: list[str] = []
    signals: list[tuple[str, str]] = []
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")
    var_re = re.compile(r"\$var\s+\w+\s+\d+\s+(\S+)\s+(.+?)\s+\$end")
    with open(path, "r", errors="replace", buffering=8 * 1024 * 1024) as f:
        for line in f:
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
                match = var_re.search(line.rstrip())
                if match:
                    code, raw = match.groups()
                    signals.append((code, ".".join(scopes + [raw.split()[0]])))
    return signals


def parse_value(value: str):
    if not value or any(ch not in "01" for ch in value):
        return None
    return int(value, 2)


def fmt(value):
    if value is None:
        return "x"
    return f"0x{value:x}" if value > 9 else str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, required=True)
    parser.add_argument("--max-cycle", type=int, required=True)
    parser.add_argument("--changed-only", action="store_true")
    args = parser.parse_args()

    code_to_labels: dict[str, list[str]] = {}
    found: set[str] = set()
    for code, full in parse_header(args.vcd):
        for suffix, label in WATCH:
            if full.endswith(suffix) and label not in found:
                code_to_labels.setdefault(code, []).append(label)
                found.add(label)

    labels = [label for _suffix, label in WATCH if label in found]
    missing = [label for _suffix, label in WATCH if label not in found]
    if missing:
        print("missing: " + " ".join(missing))
    print("cycle " + " ".join(labels))

    values: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    last_row = None
    skip_until_time = max(0, (args.min_cycle - 8) * args.period)

    def apply_line(line: str):
        if not line:
            return
        if line[0] in "bB":
            parts = line.split()
            if len(parts) != 2:
                return
            value, code = parts[0][1:], parts[1]
        elif line[0] in "01xXzZ":
            value, code = line[0], line[1:]
        else:
            return
        if code not in code_to_labels:
            return
        parsed = parse_value(value)
        for label in code_to_labels[code]:
            values[label] = parsed

    def maybe_print():
        nonlocal last_row
        cycle = current_time // args.period
        if not (args.min_cycle <= cycle <= args.max_cycle):
            return
        row = [fmt(values.get(label)) for label in labels]
        if args.changed_only and row == last_row:
            return
        print(str(cycle) + " " + " ".join(row))
        last_row = row

    with open(args.vcd, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
        for raw in f:
            line = raw.rstrip()
            if not in_values:
                if "$dumpvars" in line:
                    in_values = True
                continue
            if not line:
                continue
            if line[0] == "#":
                maybe_print()
                current_time = int(line[1:])
                if current_time > skip_until_time:
                    skip_until_time = 0
                if current_time // args.period > args.max_cycle:
                    break
            else:
                apply_line(line)
    maybe_print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
