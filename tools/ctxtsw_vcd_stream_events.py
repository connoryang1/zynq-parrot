#!/usr/bin/env python3
"""Stream selected BlackParrot VCD events from stdin.

Designed for ``fst2vcd dump.fst | ...`` so focused waveform analysis does not
materialize a multi-gigabyte VCD.  It reports globally-clocked dispatch and
context-switch commit events, and can stop the upstream conversion after a
cycle bound.
"""

from __future__ import annotations

import argparse
import re
import sys


WATCH = {
    # Newer traces expose the flattened scheduler cast while historical
    # feature checkpoints expose the same packet as a struct under ``be``.
    "dispatch_v": ("be.scheduler.dispatch_pkt_cast_o.v", "be.dispatch_pkt.v"),
    "dispatch_pc": ("be.scheduler.dispatch_pkt_cast_o.pc", "be.dispatch_pkt.pc"),
    "dispatch_tid": ("be.scheduler.dispatch_pkt_cast_o.thread_id", "be.dispatch_pkt.thread_id"),
    "dispatch_ctxtsw": ("be.scheduler.dispatch_pkt_cast_o.ctxtsw_v", "be.dispatch_pkt.ctxtsw_v"),
    "dispatch_target_ctx": (
        "be.scheduler.dispatch_pkt_cast_o.ctxtsw_target_tid",
        "be.dispatch_pkt.ctxtsw_target_tid",
    ),
    "commit_ctxtsw": ("be.calculator.commit_pkt_cast_o.ctxtsw", "be.commit_pkt.ctxtsw"),
    "commit_pc": ("be.calculator.commit_pkt_cast_o.pc", "be.commit_pkt.pc"),
    "commit_instret": ("be.calculator.commit_pkt_cast_o.instret", "be.commit_pkt.instret"),
    "cache_state": ("context_cache_state_r",),
    "cache_miss": ("context_cache_miss_v_li",),
    "cache_miss_ctx": ("context_cache_miss_context_id_li",),
    "cache_target_ctx": ("context_cache_target_context_id_r",),
    "cache_victim_ctx": ("context_cache_victim_context_id_r",),
    "cache_reg": ("context_cache_reg_idx_r",),
    "cache_drain_safe": ("context_cache_drain_safe_li",),
    "cache_launch": ("context_cache_launch_v_li",),
    "target_resident": ("ctxtsw_target_resident_v_li",),
    "capture": ("ctxtsw_capture_v_li",),
    "finalize": ("ctxtsw_token_finalize_v_li",),
    "pending_v": ("pending_ctxtsw_v_r",),
    "pending_sent": ("pending_ctxtsw_sent_r",),
    "current_tid": ("current_physical_thread_id_lo", "current_thread_id_lo"),
    "current_ctx": ("current_context_id_r",),
    "pending_prev_tid": (
        "pending_ctxtsw_prev_physical_thread_id_r",
        "pending_ctxtsw_prev_thread_id_r",
    ),
    "pending_target_tid": (
        "pending_ctxtsw_physical_thread_id_r",
        "pending_ctxtsw_thread_id_r",
    ),
    "fast_old_tid": (
        "fast_ctxtsw_old_physical_thread_id_lo",
        "fast_ctxtsw_old_thread_id_lo",
    ),
    "fast_target_tid": (
        "fast_ctxtsw_physical_thread_id_lo",
        "fast_ctxtsw_thread_id_lo",
    ),
    "retire_tid": ("retire_thread_id_lo",),
    "fe_yumi": ("fe_ctxtsw_yumi_i",),
}


def parse_value(raw: str) -> int | None:
    return int(raw, 2) if raw and set(raw) <= {"0", "1"} else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pc", action="append", type=lambda value: int(value, 0), default=[])
    parser.add_argument("--min-cycle", type=int, default=0)
    parser.add_argument("--max-cycle", type=int)
    parser.add_argument("--period", type=int, default=50_000)
    parser.add_argument("--show-signals", action="store_true")
    parser.add_argument("--all-commits", action="store_true")
    args = parser.parse_args()

    selected: dict[str, str] = {}
    widths: dict[str, int] = {}
    scopes: list[str] = []
    scope_re = re.compile(r"\$scope\s+\w+\s+(\S+)")
    var_re = re.compile(r"\$var\s+\w+\s+(\d+)\s+(\S+)\s+(.+?)\s+\$end")

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
            if match:
                width, code, name = match.groups()
                full = ".".join(scopes + [name.split()[0]])
                for label, fragments in WATCH.items():
                    if any(fragment in full for fragment in fragments) and label not in selected:
                        selected[label] = code
                        widths[code] = int(width)

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
    last_dispatch = None
    last_cache_state = None
    last_commit = 0
    last_commit_record = None
    last_capture = 0
    last_fe_yumi = 0
    current_time = 0
    in_values = False

    def sample() -> None:
        nonlocal last_dispatch, last_cache_state, last_commit, last_commit_record, last_capture, last_fe_yumi
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            return
        dispatch = values.get("dispatch_v") == 1
        pc = values.get("dispatch_pc")
        tid = values.get("dispatch_tid")
        identity = (
            pc,
            tid,
            values.get("dispatch_ctxtsw"),
            values.get("dispatch_target_ctx"),
        ) if dispatch else None
        if dispatch and pc in args.pc and identity != last_dispatch:
            print(
                f"cycle={cycle} dispatch pc=0x{pc:x} tid={tid}"
                f" ctxtsw={values.get('dispatch_ctxtsw')} target_ctx={values.get('dispatch_target_ctx')}"
                f" resident={values.get('target_resident')}"
            )
        last_dispatch = identity
        cache_state = values.get("cache_state")
        if cache_state != last_cache_state and cache_state is not None:
            print(
                f"cycle={cycle} cache_state={cache_state} current_ctx={values.get('current_ctx')}"
                f" current_tid={values.get('current_tid')} miss={values.get('cache_miss')}"
                f" miss_ctx={values.get('cache_miss_ctx')} target_ctx={values.get('cache_target_ctx')}"
                f" victim_ctx={values.get('cache_victim_ctx')} reg={values.get('cache_reg')}"
                f" drain_safe={values.get('cache_drain_safe')} launch={values.get('cache_launch')}"
            )
        last_cache_state = cache_state
        commit = values.get("commit_ctxtsw") == 1
        if commit and not last_commit:
            print(
                f"cycle={cycle} commit_ctxtsw cache_state={values.get('cache_state')}"
                f" current={values.get('current_tid')}/{values.get('current_ctx')}"
                f" retire={values.get('retire_tid')} target_ctx={values.get('dispatch_target_ctx')}"
                f" resident={values.get('target_resident')} miss={values.get('cache_miss')}"
                f" pending={values.get('pending_v')}/{values.get('pending_sent')}"
                f" prev={values.get('pending_prev_tid')} target={values.get('pending_target_tid')}"
            )
        last_commit = int(commit)
        commit_record = (values.get("commit_pc"), values.get("current_ctx"))
        if args.all_commits and values.get("commit_instret") == 1 and commit_record != last_commit_record:
            commit_pc = values.get("commit_pc")
            print(
                f"cycle={cycle} commit pc={'x' if commit_pc is None else f'0x{commit_pc:x}'}"
                f" current={values.get('current_tid')}/{values.get('current_ctx')}"
            )
        last_commit_record = commit_record if values.get("commit_instret") == 1 else None
        capture = values.get("capture") == 1
        if capture and not last_capture:
            print(
                f"cycle={cycle} capture current={values.get('current_tid')}/{values.get('current_ctx')}"
                f" fast_old={values.get('fast_old_tid')} fast_target={values.get('fast_target_tid')}"
                f" pending={values.get('pending_v')}/{values.get('pending_sent')}"
                f" finalize={values.get('finalize')}"
            )
        last_capture = int(capture)
        fe_yumi = values.get("fe_yumi") == 1
        if fe_yumi and not last_fe_yumi:
            print(
                f"cycle={cycle} fe_yumi current={values.get('current_tid')}/{values.get('current_ctx')}"
                f" pending={values.get('pending_v')}/{values.get('pending_sent')}"
                f" prev={values.get('pending_prev_tid')} target={values.get('pending_target_tid')}"
            )
        last_fe_yumi = int(fe_yumi)

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
    sample()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
