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
    "dispatch_v": "be.scheduler.dispatch_pkt_cast_o.v",
    "dispatch_pc": "be.scheduler.dispatch_pkt_cast_o.pc",
    "dispatch_tid": "be.scheduler.dispatch_pkt_cast_o.thread_id",
    "dispatch_ctxtsw": "be.scheduler.dispatch_pkt_cast_o.ctxtsw_v",
    "commit_ctxtsw": "be.calculator.commit_pkt_cast_o.ctxtsw",
    "cache_state": "context_cache_state_r",
    "capture": "ctxtsw_capture_v_li",
    "finalize": "ctxtsw_token_finalize_v_li",
    "pending_v": "pending_ctxtsw_v_r",
    "pending_sent": "pending_ctxtsw_sent_r",
    "current_tid": "current_physical_thread_id_lo",
    "pending_prev_tid": "pending_ctxtsw_prev_physical_thread_id_r",
    "pending_target_tid": "pending_ctxtsw_physical_thread_id_r",
    "fast_old_tid": "fast_ctxtsw_old_physical_thread_id_lo",
    "fast_target_tid": "fast_ctxtsw_physical_thread_id_lo",
    "retire_tid": "retire_thread_id_lo",
    "fe_yumi": "fe_ctxtsw_yumi_i",
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
                for label, fragment in WATCH.items():
                    if fragment in full and label not in selected:
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
    last_commit = 0
    last_capture = 0
    last_fe_yumi = 0
    current_time = 0
    in_values = False

    def sample() -> None:
        nonlocal last_dispatch, last_commit, last_capture, last_fe_yumi
        cycle = current_time // args.period
        if cycle < args.min_cycle:
            return
        dispatch = values.get("dispatch_v") == 1
        pc = values.get("dispatch_pc")
        tid = values.get("dispatch_tid")
        identity = (pc, tid, values.get("dispatch_ctxtsw")) if dispatch else None
        if dispatch and pc in args.pc and identity != last_dispatch:
            print(f"cycle={cycle} dispatch pc=0x{pc:x} tid={tid} ctxtsw={values.get('dispatch_ctxtsw')}")
        last_dispatch = identity
        commit = values.get("commit_ctxtsw") == 1
        if commit and not last_commit:
            print(
                f"cycle={cycle} commit_ctxtsw cache_state={values.get('cache_state')}"
                f" current={values.get('current_tid')} retire={values.get('retire_tid')}"
                f" pending={values.get('pending_v')}/{values.get('pending_sent')}"
                f" prev={values.get('pending_prev_tid')} target={values.get('pending_target_tid')}"
            )
        last_commit = int(commit)
        capture = values.get("capture") == 1
        if capture and not last_capture:
            print(
                f"cycle={cycle} capture current={values.get('current_tid')}"
                f" fast_old={values.get('fast_old_tid')} fast_target={values.get('fast_target_tid')}"
                f" pending={values.get('pending_v')}/{values.get('pending_sent')}"
                f" finalize={values.get('finalize')}"
            )
        last_capture = int(capture)
        fe_yumi = values.get("fe_yumi") == 1
        if fe_yumi and not last_fe_yumi:
            print(
                f"cycle={cycle} fe_yumi current={values.get('current_tid')}"
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
