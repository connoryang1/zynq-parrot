#!/usr/bin/env python3
"""Focused VCD timeline for BlackParrot context-switch diagnosis."""

from __future__ import annotations

import argparse
import re


WATCH = [
    ("fe.pc_gen.pc_if1_r", "pc_if1_r"),
    ("pc_if2_r", "pc_if2_r"),
    ("fe.icache.state_r", "ic_state"),
    ("fe.icache.state_n", "ic_state_n"),
    ("fe.icache.abort_miss_r", "ic_abort"),
    ("fe.icache.abort_miss", "ic_abort_comb"),
    ("fe.icache.abort_complete", "ic_abort_done"),
    ("fe.icache.paddr_tv_r", "ic_paddr_tv"),
    ("fe.icache.tag_mem_addr_li", "ic_tag_addr"),
    ("fe.icache.hit_or_repl_way", "ic_repl_way"),
    ("fe.icache.metadata_hit_r", "ic_meta_hit"),
    ("fe.icache.metadata_hit_index_r", "ic_meta_hit_way"),
    ("fe.icache.abort_miss_way_one_hot", "ic_abort_way"),
    ("fe.icache.force_i", "ic_force"),
    ("fe.icache.cache_req_yumi_i", "ic_req_yumi"),
    ("fe.icache.cache_req_critical_i", "ic_req_critical"),
    ("fe.icache.cache_req_last_i", "ic_req_last"),
    ("fe.icache.critical_recv", "ic_critical_recv"),
    ("fe.icache.complete_recv", "ic_complete_recv"),
    ("fe.icache.data_mem_pkt_v_i", "ic_data_pkt_v"),
    ("fe.icache.data_mem_pkt_yumi_o", "ic_data_pkt_yumi"),
    ("fe.icache.tag_mem_pkt_v_i", "ic_tag_pkt_v"),
    ("fe.icache.tag_mem_pkt_yumi_o", "ic_tag_pkt_yumi"),
    ("fe.icache.tag_mem_fast_read", "ic_tag_fast_read"),
    ("fe.icache.hit_v_o", "ic_hit"),
    ("fe.icache.miss_v_o", "ic_miss"),
    ("fe.realigner.if2_pc_i", "real_if2_pc"),
    ("fe.realigner.if2_data_i", "real_if2_data"),
    ("fe.realigner.if2_pc_sel", "real_if2_sel"),
    ("fe.realigner.if2_instr", "real_if2_instr"),
    ("fe.realigner.if2_count", "real_if2_count"),
    ("fe.realigner.partial_v_r", "real_partial_v"),
    ("fe.realigner.partial_pc_r", "real_partial_pc"),
    ("fe.realigner.partial_instr_r", "real_partial_instr"),
    ("fe.realigner.assembled_count_o", "real_asm_count"),
    ("fe.realigner.assembled_pc_o", "real_asm_pc"),
    ("fe.realigner.assembled_instr_o", "real_asm_instr"),
    ("fe.realigner.if2_yumi_o", "real_if2_yumi"),
    ("fetch_v_i", "fetch_v"),
    ("fe.controller.fe_queue_v_o", "feq_v"),
    ("be.scheduler.issue_ctxtsw_v", "issue_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.v", "dispatch_v"),
    ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "dispatch_ctxtsw"),
    ("be.scheduler.dispatch_pkt_cast_o.pc", "dispatch_pc"),
    ("be.scheduler.dispatch_pkt_cast_o.exception.illegal_instr", "dispatch_illegal"),
    ("be.scheduler.dispatch_pkt_cast_o.exception.mispredict", "dispatch_mispredict"),
    ("be.scheduler.dispatch_pkt_cast_o.instr.t.itype.imm12", "dispatch_imm12"),
    ("be.scheduler.dispatch_pkt_cast_o.instr.t.itype.rs1", "dispatch_rs1_addr"),
    ("be.scheduler.dispatch_pkt_cast_o.instr.t.itype.opcode", "dispatch_opcode"),
    ("be.scheduler.dispatch_pkt_cast_o.rs1", "dispatch_rs1"),
    ("be.scheduler.dispatch_pkt_cast_o.rs2", "dispatch_rs2"),
    ("be.scheduler.hazard_v_i", "hazard"),
    ("be.detector.data_haz_v", "data_haz"),
    ("be.detector.control_haz_v", "control_haz"),
    ("be.detector.struct_haz_v", "struct_haz"),
    ("fe_queue_roll_li", "roll"),
    ("fe_queue_clr_li", "iq_clr"),
    ("be.scheduler.fe_queue_ready_and_o", "iq_ready"),
    ("be.scheduler.issue_queue.ack", "iq_ack"),
    ("be.scheduler.issue_queue.preissue_v", "preissue_v"),
    ("be.scheduler.issue_queue.preissue_entry_sel", "preissue_entry"),
    ("be.scheduler.issue_queue.bypass_preissue", "bypass_preissue"),
    ("be.scheduler.issue_queue.bypass_issue", "bypass_issue"),
    ("be.scheduler.issue_queue.issue_pc", "iq_issue_pc"),
    ("be.scheduler.issue_queue.issue_instr", "iq_issue_instr"),
    ("be.scheduler.issue_queue.preissue_pkt_r.instr", "preissue_instr_r"),
    ("be.scheduler.issue_queue.fe_queue_lo.pc", "iq_feq_pc"),
    ("be.scheduler.issue_queue.fe_queue_lo.count", "iq_feq_count"),
    ("be.scheduler.issue_queue.fe_queue_lo.instr", "iq_feq_instr"),
    ("be.scheduler.issue_queue.fe_queue_cast_i.pc", "iq_in_pc"),
    ("be.scheduler.issue_queue.fe_queue_cast_i.count", "iq_in_count"),
    ("be.scheduler.issue_queue.fe_queue_cast_i.instr", "iq_in_instr"),
    ("be.scheduler.issue_queue.preissue_pkt_cast_o.thread_id", "preissue_tid"),
    ("be.scheduler.issue_pkt_cast_o.thread_id", "issue_tid"),
    ("be.scheduler.dispatch_pkt_cast_o.thread_id", "dispatch_tid"),
    ("be.scheduler.suppress_iss_i", "suppress"),
    ("be.scheduler.issue_queue.rptr_r.mem$", "iq_rmem"),
    ("be.scheduler.issue_queue.rptr_r.entry$", "iq_rentry"),
    ("be.scheduler.issue_queue.wptr_r.mem$", "iq_wmem"),
    ("be.scheduler.issue_queue.wptr_r.entry$", "iq_wentry"),
    ("be.scheduler.issue_queue.cptr_r.mem$", "iq_cmem"),
    ("be.scheduler.issue_queue.cptr_r.entry$", "iq_centry"),
    ("be.calculator.fast_ctxtsw_v_o", "fast_ctxtsw"),
    ("be.calculator.cache_req_v_o", "dc_req_v"),
    ("be.calculator.cache_req_yumi_i", "dc_req_yumi"),
    ("be.calculator.pipe_mem.cache_req_cast_o.addr", "dc_req_addr"),
    ("be.calculator.pipe_mem.cache_req_cast_o.data", "dc_req_data"),
    ("be.calculator.pipe_mem.cache_req_cast_o.msg_type", "dc_req_msg"),
    ("be.calculator.pipe_mem.uncached_store_req", "dc_uc_store"),
    ("be.calculator.pipe_mem.nonblocking_req", "dc_nonblock"),
    ("be.calculator.pipe_mem.nonblocking_sent", "dc_nonblock_sent"),
    ("be.calculator.pipe_mem.paddr_tv_r", "dc_paddr_tv"),
    ("be.calculator.pipe_mem.st_data_tv_r", "dc_st_data_tv"),
    ("pipe_mem_dcache_miss_lo", "dc_miss"),
    ("pipe_mem_dcache_replay_lo", "dc_replay"),
    ("mem_busy_lo", "mem_busy"),
    ("mem_ordered_lo", "mem_ordered"),
    ("be.calculator.reservation_r.v", "res_v"),
    ("be.calculator.reservation_r.pc", "res_pc"),
    ("be.calculator.reservation_r.decode.dcache_r_v", "res_dcr"),
    ("be.calculator.reservation_r.decode.dcache_w_v", "res_dcw"),
    ("be.calculator.reservation_r.isrc1", "res_isrc1"),
    ("be.calculator.reservation_r.isrc2", "res_isrc2"),
    ("be.calculator.pipe_sys.retire_pkt.dcache_replay$", "retire_replay"),
    ("be.calculator.pipe_sys.retire_pkt.vaddr$", "retire_vaddr"),
    ("be.calculator.pipe_sys.retire_npc_r$", "retire_npc"),
    ("be.calculator.commit_pkt_cast_o.pc$", "commit_pc"),
    ("be.calculator.commit_pkt_cast_o.vaddr$", "commit_vaddr"),
    ("be.calculator.commit_pkt_cast_o.instr.t.itype.opcode$", "commit_opcode"),
    ("be.calculator.commit_pkt_cast_o.instret$", "commit_instret"),
    ("be.calculator.commit_pkt_cast_o.queue_v$", "commit_queue_v"),
    ("be.calculator.commit_pkt_cast_o.ctxtsw$", "commit_ctxtsw"),
    ("be.calculator.commit_pkt_cast_o.npc_w_v$", "commit_npc_w"),
    ("be.calculator.commit_pkt_cast_o.thread_id$", "commit_tid"),
    ("be.calculator.pipe_flush_v$", "pipe_flush"),
    ("be.calculator.exc_stage_n[0].v$", "exn0_v"),
    ("be.calculator.exc_stage_n[1].v$", "exn1_v"),
    ("be.calculator.exc_stage_n[2].v$", "exn2_v"),
    ("be.calculator.exc_stage_n[3].v$", "exn3_v"),
    ("be.calculator.exc_stage_n[0].queue_v$", "exn0_q"),
    ("be.calculator.exc_stage_n[1].queue_v$", "exn1_q"),
    ("be.calculator.exc_stage_n[2].queue_v$", "exn2_q"),
    ("be.calculator.exc_stage_n[0].nspec_v$", "exn0_nspec"),
    ("be.calculator.exc_stage_n[1].nspec_v$", "exn1_nspec"),
    ("be.calculator.exc_stage_n[2].nspec_v$", "exn2_nspec"),
    ("be.calculator.exc_stage_r[0].v$", "exr0_v"),
    ("be.calculator.exc_stage_r[1].v$", "exr1_v"),
    ("be.calculator.exc_stage_r[2].v$", "exr2_v"),
    ("be.calculator.exc_stage_r[3].v$", "exr3_v"),
    ("be.calculator.exc_stage_r[0].queue_v$", "exr0_q"),
    ("be.calculator.exc_stage_r[1].queue_v$", "exr1_q"),
    ("be.calculator.exc_stage_r[2].queue_v$", "exr2_q"),
    ("be.calculator.exc_stage_r[0].nspec_v$", "exr0_nspec"),
    ("be.calculator.exc_stage_r[1].nspec_v$", "exr1_nspec"),
    ("be.calculator.exc_stage_r[2].nspec_v$", "exr2_nspec"),
    ("be.calculator.pipe_sys.retire_v_i$", "retire_v_i"),
    ("be.calculator.pipe_sys.retire_queue_v_i$", "retire_q_i"),
    ("be.calculator.pipe_sys.retire_ctxtsw_r$", "retire_ctxtsw_r"),
    ("be.calculator.pipe_sys.retire_nctxtsw_r$", "retire_nctxtsw_r"),
    ("be.calculator.pipe_sys.retire_instr_r.t.itype.opcode$", "retire_opcode"),
    ("be.calculator.pipe_sys.retire_ninstr_r.t.itype.opcode$", "retire_nopcode"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.pc$", "commit_pc0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.npc$", "commit_npc0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.dcache_replay", "commit_replay0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.dcache_miss", "commit_dmiss0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.vaddr", "commit_vaddr0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.exception", "commit_exc0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.instr.t.itype.imm12", "commit_imm12_0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.instr.t.itype.opcode", "commit_opcode0"),
    ("switch_commit_v", "switch_commit"),
    ("be.director.expected_npc_o", "expected_npc"),
    ("be.director.npc_r", "dir_npc_r"),
    ("be.director.br_pkt_cast_i.v", "br_v"),
    ("be.director.br_pkt_cast_i.npc", "br_npc"),
    ("be.director.br_pkt_cast_i.bspec", "br_bspec"),
    ("be.director.npc_mismatch_v", "npc_mismatch"),
    ("poison_isd_o", "poison"),
    ("be.director.state_r", "dir_state"),
    ("fe_cmd_v_li", "dir_cmd_v"),
    ("be.director.fe_cmd_li.opcode", "dir_cmd_op"),
    ("fe.controller.fe_cmd_v_i", "fe_cmd_v"),
    ("fe.controller.fe_cmd_yumi_o", "fe_cmd_yumi"),
    ("fe.controller.fe_cmd_cast_i.opcode", "fe_cmd_op"),
    ("redirect_v_o", "redirect_v"),
    ("redirect_npc_o", "redirect_npc"),
    ("current_thread_id_lo", "cur_tid"),
    ("pending_ctxtsw_v_r", "pending_v"),
    ("pending_ctxtsw_sent_r", "sent"),
    ("pending_ctxtsw_prev_thread_id_r", "pending_prev_tid"),
    ("pending_ctxtsw_thread_id_r", "pending_tid"),
    ("pending_ctxtsw_resume_npc_r", "pending_resume_npc"),
    ("pending_ctxtsw_npc_r", "pending_npc"),
    ("context_npc_r[0]", "ctx_npc0"),
    ("context_npc_r[1]", "ctx_npc1"),
    ("ctxtsw_target_npc_lo", "ctxtsw_target_npc"),
    ("fast_ctxtsw_resume_npc_lo", "fast_resume_npc"),
    ("fast_ctxtsw_target_npc_lo", "fast_target_npc"),
    ("fe_ctxtsw_npc_o", "sideband_npc"),
    ("ctxtsw_launch_lo", "launch"),
    ("fe_ctxtsw_v_o", "sideband_v"),
    ("fe_ctxtsw_yumi_i", "sideband_yumi"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.instret", "instret0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.ctxtsw", "commit_ctxtsw0"),
    ("be.calculator.pipe_sys.csr.gen_csr[0].csr_inst.commit_pkt_cast_o.npc_w_v", "commit_npc_w0"),
]


def parse_header(path: str):
    signals = []
    scopes: list[str] = []
    var_re = re.compile(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+(.+?)\s+\$end")
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")
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
                    full = ".".join(scopes + [name])
                    signals.append((code, full, int(width)))
    return signals


def select(signals):
    selected = {}
    found = {}
    for code, full, width in signals:
        for fragment, label in WATCH:
            suffix_match = fragment.endswith("$") and full.endswith(fragment[:-1])
            contains_match = not fragment.endswith("$") and fragment in full
            if (suffix_match or contains_match) and label not in found:
                selected.setdefault(code, []).append((label, full, width))
                found[label] = full
    return selected, found


def fmt(value: str, width: int) -> str:
    if re.fullmatch(r"[01]+", value or ""):
        if width == 1:
            return value
        return f"0x{int(value, 2):x}"
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int, default=2_000_000)
    parser.add_argument("--all", action="store_true", help="print all selected signal changes")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    selected, found = select(parse_header(args.vcd))
    print("selected:")
    for label, full in sorted(found.items()):
        print(f"  {label:16s} {full}")
    missing = [label for _, label in WATCH if label not in found]
    if missing:
        print("missing: " + ", ".join(missing))
    if args.list:
        return 0

    values: dict[str, str] = {}
    current_time = 0
    in_values = False
    min_time = args.min_cycle * args.period
    max_time = args.max_cycle * args.period
    with open(args.vcd, "r", errors="replace", buffering=16 * 1024 * 1024) as f:
        for line in f:
            line = line.rstrip()
            if not in_values:
                if "$dumpvars" in line:
                    in_values = True
                continue
            if not line:
                continue
            if line[0] == "#":
                current_time = int(line[1:])
                if current_time > max_time:
                    break
                continue
            if current_time < min_time:
                continue

            code = None
            value = None
            if line[0] in "bB":
                parts = line.split()
                if len(parts) == 2:
                    value, code = parts[0][1:], parts[1]
            elif line[0] in "01xXzZ":
                value, code = line[0], line[1:]

            if code not in selected or value is None:
                continue
            for label, _, width in selected[code]:
                text = fmt(value, width)
                if values.get(label) == text:
                    continue
                values[label] = text
                interesting = args.all or any(
                    key in label
                    for key in (
                        "ctxtsw",
                        "commit",
                        "retire",
                        "pipe_flush",
                        "exn",
                        "exr",
                        "dispatch",
                        "fast",
                        "cmd",
                        "redirect",
                        "roll",
                        "poison",
                        "mismatch",
                        "cur_tid",
                        "pending",
                        "sideband",
                        "ic_",
                    )
                )
                if interesting:
                    cyc = current_time // args.period
                    print(f"cyc={cyc:8d} {label:16s} {text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
