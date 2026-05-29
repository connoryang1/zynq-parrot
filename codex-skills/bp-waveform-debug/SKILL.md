---
name: bp-waveform-debug
description: Use when generating or analyzing BlackParrot waveforms, especially to confirm the trace build works, produce a dump from a specific cosim flow, and inspect the right stage-boundary signals.
---

# BlackParrot Waveform Debug

Use this skill when the next step is waveform evidence rather than more structural guessing.

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

Known temporary analyzers from prior ctxtsw work:

- `/tmp/analyze_postfix.py`
  - preferred starting point for regenerated VCDs
  - parses the VCD header and matches ctxtsw signals by name fragments
  - uses a 50 ns clock period by default
- `/tmp/parse_vcd.py`
  - broader signal-discovery scanner
  - confirm the clock period before trusting cycle counts
- `/tmp/parse_ctxtsw.py`, `/tmp/parse_thread_ids.py`, `/tmp/analyze2.py`
  - useful references for old captured VCDs
  - mostly hardcoded to specific VCD identifiers, so update before reuse

For ctxtsw hangs, start with `/tmp/analyze_postfix.py` and compare the smallest
failing case against the nearest passing case. Add signals by name fragment
rather than hardcoded VCD IDs.

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
