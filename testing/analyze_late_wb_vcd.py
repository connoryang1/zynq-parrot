#!/usr/bin/env python3
"""Print the x15 late-writeback/scoreboard timeline from a BlackParrot VCD."""

import argparse


def bits(value):
    if value in ("x", "z") or any(c in value for c in "xz"):
        return None
    return int(value, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("vcd")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument(
        "--all-hazards",
        action="store_true",
        help="also print cycles with any integer source-register match",
    )
    args = parser.parse_args()

    scopes = []
    names = {}
    values = {}
    wanted = {}
    in_header = True
    time = 0
    clock_rise = False

    suffixes = {
        ".be.iwb_pkt.thread_id": "iwb_tid",
        ".be.iwb_pkt.ird_w_v": "iwb_v",
        ".be.iwb_pkt.rd_addr": "iwb_rd",
        ".be.iwb_pkt.rd_data": "iwb_data",
        ".calculator.pipe_long_iwb_pkt.thread_id": "long_tid",
        ".calculator.pipe_long_iwb_pkt.ird_w_v": "long_v",
        ".calculator.pipe_long_iwb_pkt.rd_addr": "long_rd",
        ".calculator.pipe_long_iwb_pkt.rd_data": "long_data",
        ".calculator.pipe_mem_late_wb_pkt.thread_id": "mem_tid",
        ".calculator.pipe_mem_late_wb_pkt.ird_w_v": "mem_v",
        ".calculator.pipe_mem_late_wb_pkt.rd_addr": "mem_rd",
        ".calculator.pipe_mem_late_wb_pkt.rd_data": "mem_data",
        ".detector.score_int_v_li": "score_v",
        ".detector.clear_int_v_li": "clear_v",
        ".detector.retire_thread_id_i": "score_tid",
        ".detector.late_wb_pkt_cast_i.thread_id": "clear_tid",
        ".detector.score_rd_li": "score_rd",
        ".detector.clear_rd_li": "clear_rd",
        ".detector.check_thread_id_li": "check_tid",
        ".detector.irs_match_lo": "irs_match",
        ".detector.hazard_v_o": "hazard",
        ".detector.int_scoreboard.scoreboard_r": "scoreboard",
        ".be.clk_i": "clock",
        ".be.fe_ctxtsw_thread_id_o": "fe_target_tid",
        ".be.scheduler_current_physical_thread_id_li": "current_tid",
        ".fe.controller.ctxtsw_thread_id_r": "fe_captured_tid",
        ".fe.pc_gen.thread_id_r": "fe_pcgen_tid",
        ".be.scheduler.preissue_thread_id_li": "preissue_tid",
        ".be.scheduler.issue_thread_id_li": "issue_tid",
    }

    def report():
        def val(label, default=0):
            return bits(values.get(wanted.get(label, ""), str(default)))

        in_window = args.start <= time and (not args.end or time <= args.end)
        interesting = in_window and (
            bool(args.end)
            or
            (val("iwb_v") and val("iwb_rd") == 15)
            or (val("long_v") and val("long_rd") == 15)
            or (val("mem_v") and val("mem_rd") == 15)
            or (val("score_v") and val("score_rd") == 15)
            or (val("clear_v") and val("clear_rd") == 15)
            or (args.all_hazards and val("irs_match"))
        )
        if not interesting:
            return
        fields = []
        for label in (
            "iwb_v", "iwb_tid", "iwb_rd", "iwb_data",
            "long_v", "long_tid", "long_rd", "long_data",
            "mem_v", "mem_tid", "mem_rd", "mem_data",
            "score_v", "score_tid", "score_rd",
            "clear_v", "clear_tid", "clear_rd",
            "check_tid", "irs_match", "hazard", "scoreboard",
            "fe_target_tid", "current_tid", "fe_captured_tid",
            "fe_pcgen_tid", "preissue_tid", "issue_tid",
        ):
            number = val(label)
            fields.append(f"{label}={'x' if number is None else hex(number)}")
        print(f"t={time} " + " ".join(fields))

    with open(args.vcd, "r", errors="replace", buffering=1024 * 1024) as stream:
        for raw in stream:
            line = raw.rstrip("\n")
            if in_header:
                parts = line.split()
                if line.startswith("$scope "):
                    scopes.append(parts[2])
                elif line.startswith("$upscope"):
                    scopes.pop()
                elif line.startswith("$var "):
                    ident = parts[3]
                    full = ".".join(scopes + [parts[4]])
                    names[ident] = full
                    for suffix, label in suffixes.items():
                        if full.endswith(suffix):
                            wanted[label] = ident
                elif line.startswith("$enddefinitions"):
                    in_header = False
                continue

            if line.startswith("#"):
                if clock_rise:
                    report()
                time = int(line[1:])
                clock_rise = False
            elif line.startswith("b"):
                value, ident = line[1:].split(None, 1)
                if ident in names:
                    values[ident] = value
            elif line and line[0] in "01xz":
                ident = line[1:]
                if ident in names:
                    old = values.get(ident)
                    values[ident] = line[0]
                    if ident == wanted.get("clock") and old == "0" and line[0] == "1":
                        clock_rise = True

    if clock_rise:
        report()


if __name__ == "__main__":
    main()
