#!/usr/bin/env python3
"""Dump selected VCD signals as one row per cycle.

This is intentionally small and dependency-free so it can be used on the large
TRACE=1 VCDs generated while debugging context-switch timing.
"""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("be.scheduler.dispatch_pkt_cast_o.v$", "disp_v"),
    ("be.scheduler.dispatch_pkt_cast_o.pc$", "disp_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id$", "disp_tid"),
    ("be.scheduler.issue_pkt_cast_o.thread_id$", "issue_tid"),
    ("be.scheduler.issue_thread_id_li$", "issue_tid_li"),
    ("be.scheduler.preissue_pkt.thread_id$", "preissue_tid"),
    ("be.scheduler.dispatch_pkt_cast_o.rs1$", "disp_rs1"),
    ("be.scheduler.dispatch_pkt_cast_o.rs2$", "disp_rs2"),
    ("be.scheduler.dispatch_pkt_cast_o.instr$", "disp_instr"),
    ("be.scheduler.dispatch_pkt_cast_o.ispec_v$", "disp_ispec"),
    ("be.calculator.reservation_r.v$", "res_v"),
    ("be.calculator.reservation_r.pc$", "res_pc"),
    ("be.calculator.reservation_r.thread_id$", "res_tid"),
    ("be.calculator.reservation_r.isrc1$", "res_isrc1"),
    ("be.calculator.reservation_r.isrc2$", "res_isrc2"),
    ("be.calculator.reservation_r.ispec_v$", "res_ispec"),
    ("be.calculator.reservation_r.instr$", "res_instr"),
    ("be.calculator.pipe_int_catchup_mispredict_lo$", "catchup_misp"),
    ("be.calculator.pipe_int_catchup_npc_lo$", "catchup_npc"),
    ("be.calculator.pipe_mem.dcache_data$", "dcache_data"),
    ("be.calculator.pipe_mem.dcache_idata$", "dcache_idata"),
    ("be.calculator.pipe_mem.dcache_v$", "dcache_v"),
    ("be.calculator.pipe_mem.dcache_pkt.thread_id$", "dcache_req_tid"),
    ("be.calculator.pipe_mem.dcache_thread_id$", "dcache_ret_tid"),
    ("be.calculator.pipe_mem.dcache_thread_id_r$", "dcache_ret_tid_r"),
    ("be.calculator.pipe_mem.dcache.v_tl_r$", "dc_v_tl"),
    ("be.calculator.pipe_mem.dcache.v_tv_r$", "dc_v_tv"),
    ("be.calculator.pipe_mem.dcache.thread_id_tl_r$", "dc_tid_tl"),
    ("be.calculator.pipe_mem.dcache.thread_id_tv_r$", "dc_tid_tv"),
    ("be.calculator.pipe_mem.dcache.fill_thread_id_r$", "dc_fill_tid"),
    ("be.calculator.pipe_mem.dcache.paddr_tl$", "dc_paddr_tl"),
    ("be.calculator.pipe_mem.dcache.paddr_tv_r$", "dc_paddr_tv"),
    ("be.calculator.pipe_mem.dcache.ptag_i$", "dc_ptag_i"),
    ("be.calculator.pipe_mem.dcache.ptag_v_i$", "dc_ptag_v"),
    ("be.calculator.pipe_mem.dcache.ptag_uncached_i$", "dc_ptag_uc"),
    ("be.calculator.pipe_mem.dcache.ptag_dram_i$", "dc_ptag_dram"),
    ("be.calculator.pipe_mem.dcache.is_ready$", "dc_ready"),
    ("be.calculator.pipe_mem.dcache.state_r$", "dc_state"),
    ("be.calculator.pipe_mem.dcache.load_hit_tv$", "dc_load_hit"),
    ("be.calculator.pipe_mem.dcache.store_hit_tv$", "dc_store_hit"),
    ("be.calculator.pipe_mem.dcache.load_hit_way_tv$", "dc_hit_way"),
    ("be.calculator.pipe_mem.dcache.ld_data_dword_raw$", "dc_raw"),
    ("be.calculator.pipe_mem.dcache.ld_data_dword_merged$", "dc_merged"),
    ("be.calculator.pipe_mem.dcache.final_data_tv$", "dc_final"),
    ("be.calculator.pipe_mem.dcache.uncached_tv_r$", "dc_uncached"),
    ("be.calculator.pipe_mem.dcache.load_req$", "dc_load_req"),
    ("be.calculator.pipe_mem.dcache.store_req$", "dc_store_req"),
    ("be.calculator.pipe_mem.dcache.uncached_load_req$", "dc_uc_load_req"),
    ("be.calculator.pipe_mem.dcache.uncached_store_req$", "dc_uc_store_req"),
    ("be.calculator.pipe_mem.dcache.blocking_req$", "dc_block_req"),
    ("be.calculator.pipe_mem.dcache.blocking_sent$", "dc_block_sent"),
    ("be.calculator.pipe_mem.dcache.nonblocking_req$", "dc_nb_req"),
    ("be.calculator.pipe_mem.dcache.nonblocking_sent$", "dc_nb_sent"),
    ("be.calculator.pipe_mem.dcache.engine_miss_tv$", "dc_engine_miss"),
    ("be.calculator.pipe_mem.dcache.cache_req_v_o$", "dcache_req_v"),
    ("blackparrot.dcache_uce.cache_req_v_i$", "uce_req_v"),
    ("blackparrot.dcache_uce.cache_req_yumi_o$", "uce_req_yumi"),
    ("blackparrot.dcache_uce.cache_req_v_r$", "uce_req_r_v"),
    ("blackparrot.dcache_uce.cache_req_done$", "uce_req_done"),
    ("blackparrot.dcache_uce.cache_req_r.msg_type$", "uce_req_r_type"),
    ("blackparrot.dcache_uce.cache_req_cast_i.msg_type$", "uce_req_i_type"),
    ("blackparrot.dcache_uce.cache_req_cast_i.addr$", "uce_req_i_addr"),
    ("blackparrot.dcache_uce.cache_req_r.addr$", "uce_req_r_addr"),
    ("blackparrot.dcache_uce.fsm_fwd_v_lo$", "uce_fwd_v"),
    ("blackparrot.dcache_uce.fsm_fwd_ready_then_li$", "uce_fwd_ready"),
    ("blackparrot.dcache_uce.fsm_fwd_last_lo$", "uce_fwd_last"),
    ("blackparrot.dcache_uce.fsm_rev_yumi_lo$", "uce_rev_yumi"),
    ("blackparrot.dcache_uce.fsm_rev_last_li$", "uce_rev_last"),
    ("blackparrot.dcache_uce.credit_count_lo$", "uce_credit"),
    ("blackparrot.dcache_uce.cache_req_credits_full_o$", "uce_credit_full"),
    ("blackparrot.dcache_uce.cache_req_credits_empty_o$", "uce_credit_empty"),
    ("be.calculator.pipe_mem.dcache.cache_hit_tv$", "dc_cache_hit"),
    ("be.calculator.pipe_mem.dcache.any_miss_tv$", "dc_any_miss"),
    ("be.calculator.pipe_mem.dcache.decode_tv_r.store_op$", "dc_store_op"),
    ("be.calculator.pipe_mem.dcache.decode_tv_r.load_op$", "dc_load_op"),
    ("be.calculator.pipe_mem.dcache.decode_tv_r.byte_op$", "dc_byte_op"),
    ("be.calculator.pipe_mem.dcache.st_data_tv_r$", "dc_st_data_tv"),
    ("be.calculator.pipe_mem.eaddr$", "mem_eaddr"),
    ("be.calculator.pipe_mem.dtlb_v_lo$", "mem_dtlb_v"),
    ("be.calculator.pipe_mem.dtlb_ptag_lo$", "mem_dtlb_ptag"),
    ("be.calculator.pipe_mem.dtlb_ptag_uncached_lo$", "mem_dtlb_uc"),
    ("be.calculator.pipe_mem.dtlb_ptag_dram_lo$", "mem_dtlb_dram"),
    ("be.calculator.pipe_mem.trans_info_cast_i.translation_en$", "mem_trans_en"),
    ("be.calculator.pipe_mem.trans_info_cast_i.priv_mode$", "mem_priv"),
    ("be.calculator.pipe_mem.trans_info_cast_i.base_ppn$", "mem_base_ppn"),
    ("be.calculator.pipe_mem.dcache_busy_lo$", "mem_dcache_busy"),
    ("be.calculator.pipe_mem.dcache_ordered_lo$", "mem_dcache_ord"),
    ("be.calculator.mem_busy_o$", "mem_busy"),
    ("be.calculator.mem_ordered_o$", "mem_ordered"),
    ("be.calculator.pipe_mem.early_v_o$", "mem_early_v"),
    ("be.calculator.pipe_mem.early_data_o$", "mem_early_data"),
    ("be.calculator.pipe_mem.final_v_o$", "mem_final_v"),
    ("be.calculator.pipe_mem.final_data_o$", "mem_final_data"),
    ("be.calculator.pipe_mem.cache_replay_v_o$", "mem_replay"),
    ("be.calculator.pipe_mem.late_wb_v_o$", "mem_late_v"),
    ("be.calculator.pipe_mem.late_wb_pkt_cast_o.thread_id$", "mem_late_tid"),
    ("be.calculator.pipe_mem.late_wb_pkt_cast_o.rd_addr$", "mem_late_rd"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.translation_en$", "commit_trans_en"),
    ("be.calculator.commit_pkt_cast_o.instret$", "instret"),
    ("be.calculator.commit_pkt_cast_o.npc_w_v$", "commit_npc_w"),
    ("be.calculator.commit_pkt_cast_o.vaddr$", "commit_vaddr"),
    ("be.director.br_pkt_cast_i.v$", "br_v"),
    ("be.director.br_pkt_cast_i.npc$", "br_npc"),
    ("be.director.npc_mismatch_v$", "npc_mismatch"),
    ("be.director.expected_npc_o$", "expected_npc"),
    ("be.director.npc_r$", "dir_npc"),
    ("be.director.poison_isd_o$", "poison"),
    ("be.detector.irs1_ispec_v$", "det_irs1_ispec"),
    ("be.detector.irs2_ispec_v$", "det_irs2_ispec"),
    ("be.detector.irs1_sb_raw_haz_v$", "det_irs1_sb"),
    ("be.detector.irs2_sb_raw_haz_v$", "det_irs2_sb"),
    ("be.detector.ird_sb_waw_haz_v$", "det_ird_waw"),
    ("be.detector.irs1_data_haz_v$", "det_irs1_haz"),
    ("be.detector.irs2_data_haz_v$", "det_irs2_haz"),
    ("be.detector.irs_match_lo$", "det_irs_match"),
    ("be.detector.ird_match_lo$", "det_ird_match"),
    ("be.detector.check_thread_id_li$", "det_check_tid"),
    ("be.detector.check_rs1_li$", "det_check_rs1"),
    ("be.detector.check_rs2_li$", "det_check_rs2"),
    ("be.detector.check_rd_li$", "det_check_rd"),
    ("be.detector.score_int_v_li$", "det_score_i"),
    ("be.detector.clear_int_v_li$", "det_clear_i"),
    ("be.detector.late_wb_pkt_cast_i.thread_id$", "det_clear_tid"),
    ("be.detector.clear_rd_li$", "det_clear_rd"),
    ("be.detector.data_haz_v$", "det_data_haz"),
    ("be.detector.hazard_v_o$", "det_hazard"),
    ("be.scheduler.fe_queue_roll_li$", "roll"),
    ("be.scheduler.current_thread_id_i$", "sched_cur_tid"),
    ("be.scheduler.retire_thread_id_i$", "sched_ret_tid"),
    ("be.scheduler.fe_queue_clr_li$", "iq_clr"),
    ("be.calculator.pipe_flush_v$", "pipe_flush"),
    ("be.calculator.cache_req_v_o$", "dc_req_v"),
    ("be.calculator.cache_req_yumi_i$", "dc_req_yumi"),
    ("be.calculator.pipe_mem.cache_req_cast_o.addr$", "dc_req_addr"),
    ("be.calculator.pipe_mem.cache_req_cast_o.data$", "dc_req_data"),
]


def parse_header(path: str):
    scopes: list[str] = []
    signals = []
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")
    var_re = re.compile(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+(.+?)\s+\$end")
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
                    width, code, raw = match.groups()
                    name = raw.split()[0]
                    signals.append((code, ".".join(scopes + [name]), int(width)))
    return signals


def select(signals):
    selected: dict[str, list[tuple[str, int]]] = {}
    found: dict[str, str] = {}
    for code, full, width in signals:
        for fragment, label in WATCH:
            match = full.endswith(fragment[:-1]) if fragment.endswith("$") else fragment in full
            if match and label not in found:
                selected.setdefault(code, []).append((label, width))
                found[label] = full
    return selected, found


def parse_value(value: str):
    if not value or any(ch not in "01" for ch in value):
        return None
    return int(value, 2)


def apply_line(line: str, selected, values):
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
    if code not in selected:
        return
    parsed = parse_value(value)
    for label, _width in selected[code]:
        values[label] = parsed


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
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    if args.list:
        for label, full in sorted(found.items()):
            print(f"{label:16s} {full}")
        missing = [label for _, label in WATCH if label not in found]
        if missing:
            print("missing: " + ", ".join(missing))
        return 0

    values: dict[str, int | None] = {}
    current_time = 0
    in_values = False
    labels = [label for _, label in WATCH if label in found]
    print("cycle " + " ".join(labels))

    def capture():
        cycle = current_time // args.period
        if args.min_cycle <= cycle <= args.max_cycle:
            return cycle, f"{cycle} " + " ".join(fmt(values.get(label)) for label in labels)
        return None, None
    pending_cycle = None
    pending_row = None

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
                cycle, row = capture()
                if row is not None:
                    pending_cycle = cycle
                    pending_row = row
                next_time = int(line[1:])
                next_cycle = next_time // args.period
                if pending_row is not None and pending_cycle != next_cycle:
                    print(pending_row)
                    pending_cycle = None
                    pending_row = None
                current_time = next_time
                if current_time // args.period > args.max_cycle:
                    break
            else:
                apply_line(line, selected, values)
    cycle, row = capture()
    if row is not None:
        pending_cycle = cycle
        pending_row = row
    if pending_row is not None:
        print(pending_row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
