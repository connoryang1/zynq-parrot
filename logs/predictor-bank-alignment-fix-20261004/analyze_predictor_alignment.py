#!/usr/bin/env python3
"""Check predictor-bank request/result provenance in the filtered VCD."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from cache_overlap_vcd import rising_edges  # noqa: E402
from prefetch_overlap_vcd import bit, read_header  # noqa: E402

HERE = Path(__file__).resolve().parent
VCD = HERE / "predictor-input-selected.vcd"
NAMES = {
    "clock": "be.clk_i",
    "redirect": "fe.pc_gen.redirect_v_i",
    "redirect_thread_v": "fe.pc_gen.redirect_thread_id_v_i",
    "redirect_thread": "fe.pc_gen.redirect_thread_id_i",
    "yumi": "fe.pc_gen.icache_yumi_i",
    "owner": "fe.pc_gen.thread_id_r",
    "request_bank": "fe.pc_gen.predictor_r_thread_id",
    "result_bank": "fe.pc_gen.predictor_result_thread_id_r",
    "bht0_read": "fe.pc_gen.bht_gen[0].bht_inst.r_v_i",
    "bht1_read": "fe.pc_gen.bht_gen[1].bht_inst.r_v_i",
    "btb0_read": "fe.pc_gen.btb_gen[0].btb_inst.r_v_i",
    "btb1_read": "fe.pc_gen.btb_gen[1].btb_inst.r_v_i",
}


def main():
    failures = []
    redirects = []
    accepted_reads = 0
    result_checks = 0
    expected_result = None
    with VCD.open() as stream:
        selected, timescale = read_header(stream, NAMES)
        for cycle, timestamp, values in rising_edges(stream, selected):
            # The pre-edge result must correspond to the previous accepted read.
            if expected_result is not None:
                result_checks += 1
                actual = bit(values, "result_bank")
                if actual != expected_result["bank"]:
                    failures.append({
                        "kind": "result_provenance",
                        "cycle": cycle,
                        "expected": expected_result,
                        "actual": actual,
                    })
            expected_result = None

            yumi = bit(values, "yumi")
            request_bank = bit(values, "request_bank")
            bank_reads = {
                0: (bit(values, "bht0_read"), bit(values, "btb0_read")),
                1: (bit(values, "bht1_read"), bit(values, "btb1_read")),
            }
            expected_reads = {
                bank: (int(yumi and bank == request_bank),) * 2 for bank in (0, 1)
            }
            if bank_reads != expected_reads:
                failures.append({
                    "kind": "request_bank_enable",
                    "cycle": cycle,
                    "request_bank": request_bank,
                    "yumi": yumi,
                    "actual": bank_reads,
                    "expected": expected_reads,
                })
            if yumi:
                accepted_reads += 1
                expected_result = {"bank": request_bank, "from_cycle": cycle}

            if bit(values, "redirect") and bit(values, "redirect_thread_v"):
                target = bit(values, "redirect_thread")
                row = {
                    "cycle": cycle,
                    "timestamp": timestamp,
                    "old_owner": bit(values, "owner"),
                    "target": target,
                    "request_bank": request_bank,
                    "accepted": bool(yumi),
                }
                redirects.append(row)
                if request_bank != target:
                    failures.append({"kind": "redirect_target_request", **row})

    summary = {
        "status": "PASS" if not failures else "FAIL",
        "timescale": timescale,
        "context_redirects": len(redirects),
        "accepted_predictor_reads": accepted_reads,
        "checked_result_provenance": result_checks,
        "redirects": redirects,
        "failures": failures,
    }
    (HERE / "predictor-alignment.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("redirects", "failures")}, indent=2))
    if failures:
        print(json.dumps(failures[:10], indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
