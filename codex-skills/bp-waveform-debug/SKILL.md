---
name: bp-waveform-debug
description: Use when generating or analyzing BlackParrot waveforms, especially to confirm the trace build works, produce a dump from a specific cosim flow, and inspect the right stage-boundary signals.
---

This skill selects trace boundaries and maintained waveform tools for BlackParrot
debugging. It keeps architectural handoff measurements separate from benchmark
loop spacing and avoids relying on historical signal IDs or temporary scripts.

# BlackParrot Waveform Debug

## Goal

- confirm the trace-capable build works
- produce a real waveform file from the intended workload
- inspect stage boundaries, not an undifferentiated sea of signals

## Build and Run Discipline

- use the exact cosim flow that reproduces the issue
- if the local wrapper expects `dump.fst`, honor that
- verify the dump file exists and is nontrivial before trying to view it

## For Minimal-Example Verilator

Prefer this sequence:

1. export `TRACE=1`
2. rebuild the traced simulator if needed
3. run the target workload
4. confirm `dump.fst` exists
5. only then open the viewer

## Stage-Boundary Thinking

Before adding signals, decide which boundary matters:

- dispatch
- reservation / execute
- commit
- FE command enqueue / consume
- FE restart
- first visible target-thread execution

## Signal Strategy

Start with a narrow set tied to the hypothesis.

For ctxtsw, examples include:

- dispatch-time ctxtsw classification
- delayed/retired ctxtsw bit
- `commit_pkt.ctxtsw`
- director FE command valid / consume
- current BE thread id
- FE thread id / restart PC

## Ctxtsw Analyzer Tools

Use `tools/ctxtsw_vcd_stream_events.py` for globally clocked dispatch/commit
events, and `tools/vcd_cycle_dump.py` for a selected cycle window. Inspect their
`--help` and the actual trace hierarchy/time units before choosing bounds.
The streaming tool consumes `fst2vcd` output without expanding the entire trace
onto disk. Keep exact endpoints explicit; old automatic report tools assumed
the obsolete `0x081` context CSR and were retired to the Git archive.

## FP Register Boundary Analysis

For resident or nonresident FP-state failures, stream the compressed waveform
through the checked-in analyzer instead of expanding it to a multi-gigabyte
VCD:

```bash
fst2vcd cosim/black-parrot-minimal-example/verilator/dump.fst \
  | python3 -u tools/fp_regfile_vcd_events.py --reg 1
```

Use `--pc <address>` to report the operand actually presented at dispatch and
`--int-reg <n>` for FP-to-integer completion/writeback. Use `--all-dispatch`
only with a narrow `--min-cycle` / `--max-cycle` window. The raw synchronous
register-file read request and `rs_data_o` are one stage apart; treat the
dispatch operand as the architectural consumption boundary.

For ctxtsw hangs, compare the smallest failing case against the nearest passing
case with the maintained streaming tool. Add signals by name fragment rather
than hardcoded VCD IDs; do not rely on files left in `/tmp` by an earlier session.

## Ctxtsw First-Pass Signals

Keep the first waveform pass small:

- token: `pending_ctxtsw_v_r`, `pending_ctxtsw_sent_r`, `ctxtsw_launch_pending_r`
- launch/accept: `ctxtsw_launch_lo`, `fe_ctxtsw_v_o`, `fe_ctxtsw_yumi_i`
- commit: `commit_pkt.ctxtsw`, `commit_pkt.npc_w_v`, `commit_pkt.instret`
- ownership: `current_thread_id_lo`, pending previous/target thread ids
- director/queue: `state_r`, `poison_isd_o`, `suppress_iss_o`, `clear_iss_o`,
  `fe_queue_roll_li`, `npc_mismatch_v`

## Reporting

After waveform preparation, report:

- exact run command
- whether the dump was produced
- dump path and size
- which stage boundary will be inspected next
