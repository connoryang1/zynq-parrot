# Context Switch Forwarding Investigation Log

This document records what has already been tried or learned while debugging
ctxtsw forwarding. Keep this updated whenever a test, waveform, code audit, or
RTL experiment changes our understanding.

The purpose is to avoid repeating old experiments and to separate facts from
hypotheses.

## Current Working Theory

ISD-level forwarding can overlap some frontend work, but correctness currently
depends on preserving commit-time cleanup and preventing the FE I-cache from
exposing a partially completed miss fill after a redirect.

The first robust repair was conservative: hold `bp_fe_icache` in `e_miss` after
`force_i` until the outstanding fill reaches `complete_recv`. That fixed the
dense gap8 hang, but regressed the single-switch estimate toward the
`0x16`-`0x1b` range because redirected context switches could no longer abort an
outstanding I-cache miss.

The current speed experiment is narrower: on `force_i` during an I-cache miss,
return the I-cache to `e_ready`, invalidate the abandoned victim way, and drain
the old fill response while suppressing its tag/data/stat writes. This keeps
the stale-fill hazard from reappearing in tested cases, but performance remains
layout sensitive: the original microbench and gap1 still pay a large refill tail,
while gap8/gap14 can expose a much lower one-way estimate.

Older stacked sideband/fast-path experiments showed `mt_ctxtsw_smoke_test`
passing while `mt_ctxtsw_microbench_gap14` timed out. The first concrete
corruption observed in that failing log was an illegal/wrong instruction at
`pc=0x800002da`, where the binary contains:

```text
800002d6: 00007797  auipc a5,0x7
800002da: 75a78793  addi  a5,a5,1882
800002de: 472d      li    a4,11
```

The failing run retired `instr=0x4d56dfd3` at `pc=0x800002da` with
`vaddr=0x800002e2`. A later failure also showed a wrong instruction around
`bp_print_string` at `pc=0x800055a6`. This points at FE fetch/realign/queue
state or redirect metadata corruption after a sideband switch, rather than a
simple pending-token overwrite.

IF2 forwarding should wait until ISD forwarding is fully characterized. Moving
the detection earlier will otherwise hide or amplify the same cleanup bug.

Latest verified result on branch `ctxtsw-isd-repair`:

- RTL diff:
  - `bp_be_director.sv`: commit-time ctxtsw FE command uses
    `e_op_state_reset` instead of reissuing `e_op_context_switch`.
  - `bp_be_scheduler.sv`: ctxtsw commit clears the FE queue and suppresses
    npc-write rollback.
  - `bp_fe_icache.sv`: `e_miss` no longer exits early on `force_i`; it waits
    for `complete_recv`.
- Root cause for the remaining gap8 hang:
  - A redirected/forced I-cache miss could be abandoned while the returning fill
    continued to update tag/data state.
  - Waveform evidence showed PC `0x80005594` later hitting with stale garbage
    data (`0xd0c29ab0...`) instead of the NBF contents at that address.
  - No D-cache store to the `0x80005xxx` code range was observed, so this was
    an I-cache fill/validity hazard rather than self-modifying data corruption.
- Verified tests with clean rebuilds and `TRACE=1`:
  - `mt_ctxtsw_smoke_test`: PASS
  - `mt_ctxtsw_microbench_gap8`: PASS, warm estimates `0x2d`, `0x44`, min
    single-switch estimate `0x16`
  - `mt_ctxtsw_microbench`: PASS, warm min round trip `0x2f`, min single-switch
    estimate `0x17`
  - `mt_ctxtsw_microbench_gap14`: PASS, min single-switch estimate `0x1b`
  - `mt_regfile_test`: PASS architecturally, but console output remains visibly
    corrupted around printed strings
  - `make -j24 prep_lite`: PASS

Latest checkpoint:

- RTL diff:
  - `bp_fe_icache.sv`: adds `abort_miss_r`, invalidates the aborted miss victim
    way on `force_i`, returns from `e_miss` to `e_ready`, and drains the old fill
    with slow tag/data/stat writes suppressed until `cache_req_last_i`.
- Verified tests with clean rebuilds and `TRACE=1`:
  - `mt_ctxtsw_microbench_gap1`: PASS, warm min single-switch estimate `0x36`
  - `mt_ctxtsw_microbench_gap4`: PASS, warm min single-switch estimate `0x34`
  - `mt_ctxtsw_microbench_gap8`: PASS, warm min single-switch estimate `0x6`
  - `mt_ctxtsw_microbench_gap14`: PASS, warm min single-switch estimate `0x6`
  - `mt_ctxtsw_microbench`: PASS, warm min round-trip `0x6c`, estimate `0x36`
  - `mt_ctxtsw_partial_unroll_benchmark`: PASS, cycles/switch `0x6`
  - `mt_ctxtsw_smoke_test`: PASS
  - `mt_regfile_test`: PASS
  - `mt_csr_isolation_test`: PASS
  - `mt_frf_isolation_test`: PASS
- Waveform evidence:
  - Conservative gap8 trace `/tmp/gap8_final_candidate.vcd`: context-switch
    redirect collides with `icache.state_r=e_miss`; I-cache waits roughly from
    cycle `294052` to `294105` for `complete_recv`.
  - Abort+invalidate gap8 trace `/tmp/gap8_icache_abort_inval.vcd`: redirect
    starts abort at cycle `294573`, old fill drains by `294602`, and stale
    instruction data (`0xd0c29ab0...`) does not reappear in the focused trace.
  - Microbench abort+invalidate trace `/tmp/microbench_abort_inval.vcd`: dense
    switches still encounter miss/abort/fill windows after some redirects, so
    the benchmark remains around `0x8` per switch instead of the `0x4` unrolled
    throughput.
  - Partial-unroll abort+invalidate trace
    `/tmp/partial_unroll_abort_inval.vcd`: tightly staggered ctxtsw sequences
    remain possible; observed issue/commit/switch cadence supports the measured
    `0x4` cycles/switch.

Interpretation:

- The hang/corrupt-instruction failure is fixed by holding the I-cache in miss
  until the fill completes.
- The abort+invalidate experiment recovers most of that conservative
  performance loss without reintroducing the stale-fill hazard in tested cases.
- Not every benchmark is slow: gap8/gap14 can still show a `0x6` one-way
  estimate, but the original microbench and gap1 are much slower. The slowdown
  is workload/layout dependent and appears when redirects collide with I-cache
  fill state.
- Recovering the 5-cycle/IF2-forwarding path more generally likely requires a
  more precise I-cache fill protocol, such as transaction/epoch tagging or
  delaying tag visibility until the corresponding line data is definitely
  coherent under redirects.
- The print corruption should be tracked separately from the context-switch
  hang. It does not currently block `BSG PASS`, but it means host I/O ordering
  around dense switches is still not cleanly explained.
- A scheduler-side hold after `issue_ctxtsw_v` was tried and reverted because it
  did not change the `mt_regfile_test` console corruption.

Important correction from Claude's later report:

- The known "gap1 through gap16 all pass" result was not this full stacked
  worktree.
- The valid fix for that result was only the scheduler rollback suppression:

```systemverilog
wire fe_queue_roll_li = commit_pkt_cast_i.npc_w_v & ~commit_pkt_cast_i.ctxtsw;
```

- In that clean scheduler-fix state, reported results were:
  - `mt_ctxtsw_smoke_test`: pass
  - `mt_ctxtsw_microbench`: pass
  - `mt_ctxtsw_microbench_gap1` through `gap16`: pass
  - `mt_ctxtsw_partial_unroll_benchmark`: pass
  - `mt_csr_isolation_test`, `mt_regfile_test`, `mt_frf_isolation_test`: pass
  - `mt_ctxtsw_live_regs_test`: hang, believed pre-existing
- A clean scheduler-only reconstruction now contains only that scheduler line in
  the BP submodule, plus the pre-existing unrelated `bp_be_regfile_mt.sv`
  remote-write forwarding change. The stacked `bp_be_top.sv`,
  `bp_be_calculator_top.sv`, and `bp_fe_controller.sv` changes were saved to
  `/tmp/ctxtsw_stacked_current.patch` and removed from the active RTL for this
  baseline.

Default debug rule going forward:

- Any unexpected hang, pass/fail discrepancy, or unexpected cycle count should
  get a focused TRACE waveform before another RTL guess.
- The first comparison should be between the same test on:
  1. clean scheduler-only baseline
  2. current stacked ISD/sideband worktree
- Keep the waveform signal set narrow: token create/accept/finalize, FE
  redirect metadata, FE queue roll/read/clear, and commit PC/instruction/thread.

## Known Architecture Facts

### Commit Authority

- `commit_pkt.ctxtsw` is the architectural signal that the context-switch
  instruction retired.
- It is generated at retirement, not at FE detection:
  - `bp_be_pipe_sys.sv` tracks `retire_ctxtsw_r`.
  - `bp_be_csr.sv` assigns `commit_pkt.ctxtsw = retire_pkt.instret &
    retire_ctxtsw_v`.
- Any early FE or BE behavior must eventually be reconciled with
  `commit_pkt.ctxtsw`.

Implication:

- Early forwarding can be speculative or preparatory.
- Context save/restore, old-thread retirement accounting, and final ownership
  changes must be carefully tied back to commit unless a stronger early-safety
  proof is added.

### Current Ctxtsw Decode Point

- Immediate ctxtsw is identified in the BE scheduler/issue path.
- The scheduler detects CSR immediate writes to CSR `0x081`.
- For immediate form, the target thread id is in the instruction immediate field
  and does not require reading a register value.

Implication:

- Immediate-form ctxtsw is the right first fast path.
- Register-form ctxtsw should fall back to the BE/ISD path until a clean operand
  forwarding scheme exists.

### FE Queue Hold vs Poison

- `poison_isd_i` suppresses dispatch validity; it is not a reliable hold
  mechanism.
- If an entry is read while poisoned, the design can effectively drop work.
- A safer hold point is the scheduler enable path, for example around
  `fe_queue_en_li = ~suppress_iss_i & ~ptw_busy_lo & ~hazard_v_i`.

Implication:

- For speculative target-context packets, prefer hold/backpressure over poison.
- Any IF2 implementation that allows target packets to reach BE before commit
  probably needs an explicit hold/release rule.

### Memory Side Effects Are Not Commit-Only

- Code analysis of the memory pipe showed dcache request generation can happen
  from reservation-stage valid requests.
- Therefore arbitrary target-context BE execution before ctxtsw commit is not
  globally safe.

Implication:

- Early FE redirect alone is safer than early BE ownership/execution.
- If target instructions can reach memory execution before the old ctxtsw
  commits, they must be blocked or proven side-effect-free.

### CSR Side Effects

- Normal CSR writes are retirement-side.
- Ctxtsw itself should not be treated as an ordinary CSR write to `0x081` at
  retirement; it has special commit behavior.

Implication:

- CSR state updates are less likely than memory to be the first unsafe side
  effect, but commit-time ctxtsw handling must remain special.

### FE Packetization Requirement for IF2

If a fetch packet contains older instructions before ctxtsw, those older
instructions must still be delivered before redirecting the younger stream.

Example:

```text
instr0, instr1, ctxtsw, younger0
```

Correct IF2 behavior:

```text
enqueue instr0, instr1, ctxtsw
redirect younger stream to target context
do not enqueue younger0 from the old stream
```

Branch priority must be explicit:

- branch before ctxtsw: branch wins
- ctxtsw before branch: ctxtsw wins

Implication:

- IF2 forwarding is not just "detect ctxtsw in the packet and redirect."
- It needs branch-like packet boundary handling.

## Known Test Results

These are accumulated observations from prior experiments and may not all refer
to the exact same commit. Treat them as evidence, not as a single verified
baseline.

### Known-Good Commit-Time Baseline

- `mt_ctxtsw_microbench`: passed.
- Warm round trip: `0x0e`.
- Warm single-switch estimate: `0x07`.

Interpretation:

- The original commit-time path is correct and reasonably stable.
- It is the fallback correctness reference.

### Sideband / FE-Overlap Experiments

Observed results included:

- `mt_ctxtsw_partial_unroll_benchmark`: reported `0x5` cycles/switch in one
  sideband-only style experiment.
- `mt_ctxtsw_microbench`: still reported around `0x10` round trip / `0x8`
  estimate in a related experiment.
- Some versions improved FE overlap but did not improve or even regressed dense
  benchmark behavior.

Interpretation:

- The useful `0x5` result likely measured FE prefetch/overlap, not a fully
  generalized safe 5-cycle context switch.
- The difference between partial-unroll and dense microbench means benchmark
  spacing matters.

### Dense Microbench and Trace Variants

Observed:

- `mt_ctxtsw_microbench_trace`: passed in at least one experiment.
- `mt_ctxtsw_microbench_barrier`: hung in at least one experiment.
- Original `mt_ctxtsw_microbench`: has hung in some fast-path experiments, even
  when trace-like versions passed.

Interpretation:

- The trace markers/calls change spacing and scheduling enough to hide the bug.
- The barrier/no-marker shape is closer to the real dense failure.

### 2026-05-13 Scheduler-Only Recheck

Active BP RTL at this point:

- `bp_be_scheduler.sv`: only the ctxtsw rollback suppression line is active:
  `fe_queue_roll_li = commit_pkt_cast_i.npc_w_v & ~commit_pkt_cast_i.ctxtsw`.
- `bp_be_top.sv` and `bp_be_director.sv`: no active diff.
- `bp_be_regfile_mt.sv`: pre-existing remote-write forwarding cleanup/fix is
  still present and was not touched during this recheck.

New observations:

- A trace-enabled `mt_ctxtsw_microbench_gap8` run with the temporary waveform
  gate passed:
  - `0xe / 0xe / 0xe`
  - estimate `0x7`
  - `BSG PASS`
- The captured trace window `275k..295k` was too early; it only showed
  startup/runtime branch traffic, including the `_start` BSS clear loop around
  `0x8000012e/0x80000132/0x80000134`, not the benchmark ctxtsw sequence.
- Clean non-trace rebuilds then hung after NBF load with no benchmark UART
  output for:
  - `mt_ctxtsw_microbench_gap8`
  - `mt_ctxtsw_microbench_gap12`
- Removing the temporary waveform gate from
  `cosim/v/bsg_nonsynth_zynq_testbench.sv` and rebuilding clean did not fix the
  non-trace hang.

Interpretation:

- The current local state is not yet a trustworthy scheduler-only checkpoint,
  because `gap12` no longer reproduces the earlier known pass.
- The immediate next step should be to compare against the exact clean
  scheduler-only state reported by Claude, or to add a very small non-waveform
  debug monitor around first benchmark entry/first ctxtsw so we can tell whether
  the non-trace run reaches the test body before hanging.

### Gap Tests

Observed in one experiment:

- `gap13`: hung.
- `gap14`: passed with roughly `0xf` cold/warm round trips and `0x7` estimate.
- `gap16`: passed with similar behavior.

Current `ctxtsw-isd-repair` observation:

- `mt_ctxtsw_smoke_test`: `BSG PASS`, `minstret delta 0xdbb`.
- After reconstructing the scheduler-only baseline, a stale build made `gap14`
  appear to hang. A clean trace rebuild passed, which showed the prior
  non-trace run was not trustworthy evidence.
- Code/objdump analysis then found a real test-shape issue: at `-O2`, `gap14`
  emitted an out-of-line `controlled_gap()` call (`jal` + 14 nops + `ret`),
  while `gap1` emitted inline nops. That made `gap14` a call/return test, not a
  pure straight-line gap test.
- Fix: force `controlled_gap()` to `always_inline` in
  `testing/mt_ctxtsw_microbench_gap_common.h`.
- With the fixed straight-line `gap14` binary and clean non-trace scheduler-only
  RTL, `mt_ctxtsw_microbench_gap14` passes:
  - cold: `0xe`
  - warm0: `0xe`
  - warm1: `0xe`
  - warm min estimate: `0x7`
  - `BSG PASS`
- Additional scheduler-only non-trace results from the same repaired baseline:
  - `mt_ctxtsw_microbench_gap13`: cold `0xe`, warm0 `0xf`, warm1 `0xe`,
    estimate `0x7`, `BSG PASS`.
  - `mt_ctxtsw_microbench_gap16`: cold `0xe`, warm0 `0xe`, warm1 `0xe`,
    estimate `0x7`, `BSG PASS`.
  - After stopping unrelated concurrent make/Verilator jobs, running
    `make clean`, and rebuilding non-trace via `mt_ctxtsw_smoke_test`,
    `mt_ctxtsw_microbench_gap12` passes: cold `0xe`, warm0 `0xe`, warm1
    `0xe`, estimate `0x7`, `BSG PASS`.
  - In that same clean non-trace baseline, `mt_ctxtsw_microbench_gap8` hangs
    before printing benchmark output.
  - `mt_ctxtsw_microbench_gap4` also hangs before printing benchmark output.
  - `mt_ctxtsw_microbench`: cold `0xe`, warm0 `0xe`, warm1 `0xe`,
    estimate `0x7`, `BSG PASS`, minstret delta `32974`.
  - `mt_ctxtsw_partial_unroll_benchmark`: `0x4` cycles per switch,
    `BSG PASS`.
  - `mt_csr_isolation_test`: final `[BSG-PASS]` and `BSG PASS`.
  - `mt_regfile_test`: final `ALL TESTS PASSED` and `BSG PASS`.
  - `mt_frf_isolation_test`: final `[BSG-PASS]` and `BSG PASS`.

Interpretation:

- The old `gap14` hang was not a clean ISD-forwarding failure. It was caused by
  the benchmark shape changing into a call/return sequence, stale/unclean
  Verilator/test rebuilds obscuring the result, and comparison against stacked
  sideband experiments rather than the scheduler-only baseline.
- Gap tests must be checked with objdump when the gap body changes; the intended
  shape is straight-line nops after each measured ctxtsw.
- The scheduler-only line remains the valid minimal RTL fix for the stale
  FE-queue rollback bug.
- Scheduler-only is not fully verified for all dense/tight controlled-gap
  shapes. The current confirmed boundary is `gap12` passing and `gap8`/`gap4`
  hanging in a clean non-trace build.

### Claude-Reported Passing Batch

Claude task output in `/tmp` includes concise summaries where:

- `mt_ctxtsw_smoke_test`: `BSG PASS`
- `mt_ctxtsw_microbench`: `BSG PASS`
- `mt_ctxtsw_partial_unroll_benchmark`: `BSG PASS`
- `mt_ctxtsw_live_regs_test`: output line was present but did not include a
  visible pass string in the captured summary.

Caution:

- These outputs do not by themselves identify the exact RTL commit or dirty
  state.
- They should be used to find the promising patch/state, not as proof that the
  current worktree is good.

## Attempted Fixes and Outcomes

### Early BE Ownership Handoff

Attempt:

- Change BE ownership/current thread earlier than commit.

Observed:

- Some versions hung or corrupted dense tests.
- Old-thread retirement and context save became difficult to reason about.

Lesson:

- Early BE ownership is high risk unless old-thread retirement identity and
  target-thread dispatch are fully separated.
- For now, prefer early FE redirect with commit-time BE architectural ownership.

### Suppressing Duplicate Commit-Time FE Command

Attempt:

- Use a `pending_ctxtsw_sent_r`-style token to avoid sending the commit-time
  `e_op_context_switch` FE command after FE already accepted sideband redirect.

Observed:

- Avoiding duplicate FE command is necessary, but suppressing too much director
  cleanup caused stalls or fall-through in some versions.

Lesson:

- Split "architectural/backend finalization" from "FE/control cleanup."
- Do not blindly replace all uses of `commit_pkt.ctxtsw`.
- Waveform must show:
  - early FE accept happens once,
  - commit still finalizes,
  - duplicate FE command is suppressed,
  - director does not drop required cleanup.

### Removing Commit-Time FE Queue Roll on Ctxtsw

Attempt:

- Change scheduler roll from `commit_pkt.npc_w_v` to
  `commit_pkt.npc_w_v & ~commit_pkt.ctxtsw`.

Observed:

- This was intended to avoid rolling/dropping queue state on a ctxtsw commit.

Open status:

- Needs verification against the smallest failing gap test.
- Check with waveform that the FE queue entry is held or advanced correctly and
  not duplicated.

### Dropping Same-Cycle FE Queue Packet on Sideband Accept

Attempt:

- In `bp_fe_controller.sv`, suppress `fetch_instr_v` and `fetch_exception_v` on
  `ctxtsw_accept_v`, while still allowing the fetch/realigner handshake.
- A stricter version that also suppressed `fetch_yumi_o` was tried first.

Observed:

- Suppressing `fetch_yumi_o` created a bad handshake/combinational dependency
  and hung the smoke test.
- Suppressing only FE queue valid preserved `mt_ctxtsw_smoke_test`.
- `mt_ctxtsw_microbench_gap14` still timed out with the same wrong-instruction
  pattern.

Lesson:

- The bad gap14 behavior is not fixed by dropping only the same-cycle old IF2
  packet at sideband accept.
- Do not gate `fetch_yumi_o` with `ctxtsw_accept_v`; accept itself depends on
  the FE/icache handshake.

### BE Issue Fence During Sideband/Commit Window

Attempt:

- Add `pending_ctxtsw_sent_i & ~switch_commit_v` to director `issue_fence_v`.

Observed:

- `mt_ctxtsw_smoke_test` still passed.
- `mt_ctxtsw_microbench_gap14` still timed out with the same
  wrong-instruction pattern.

Lesson:

- The corruption is not explained by target-context BE issue during only the
  one-cycle `pending_ctxtsw_sent_i` window.
- The bad instruction appears after the switch has committed and execution has
  returned to main-thread code.

### Re-enabling Duplicate Commit-Time Ctxtsw FE Command

Attempt:

- Force the commit-time `e_op_context_switch` FE command valid even when
  `pending_ctxtsw_sent_i` says sideband was already accepted.

Observed:

- `mt_ctxtsw_smoke_test` timed out/hung.

Lesson:

- The duplicate commit-time FE command is not a safe cleanup fix in the current
  sideband design.
- Keep duplicate FE command suppression while looking for the real FE
  realign/metadata/queue corruption.

### Disabling Sideband Output

Observed current/intermediate state:

- Some worktree states had `fe_ctxtsw_v_o = 1'b0` while token/director
  scaffolding remained.

Lesson:

- That state is not exercising ISD forwarding.
- Before debugging ISD forwarding, confirm sideband output is actually enabled.

### Director Port Drift

Observed:

- Intermediate edits added director ports such as
  `pending_ctxtsw_fast_finalized_i` and `ctxtsw_fast_finalize_i`.
- At least one Claude build failed with a `PINNOTFOUND` error for
  `ctxtsw_fast_finalize_i`.

Lesson:

- Before any runtime debugging, run a static build.
- Keep port additions and hookups in the same commit.

### Regfile Remote-Write Forwarding Fix

Attempt:

- In `bp_be_regfile_mt.sv`, delayed replacement used `w_data_mux` instead of
  `rd_data_i`.

Interpretation:

- This looks like a real remote-write forwarding fix, but it is separate from
  ctxtsw control flow.

Lesson:

- Keep this in a separate checkpoint from forwarding experiments if possible.

## Waveform Insights Collected So Far

### Sideband Accept / Commit Relationship

Observed in user waveform notes:

- `fe_ctxtsw_v_o` and `fe_ctxtsw_yumi_i` can be high together at the launch
  cycle.
- `pending_ctxtsw_sent_r` goes high one cycle after `yumi`.
- `commit_pkt.ctxtsw` can occur one cycle after sideband accept.

Guarantee/interpretation:

- FE accept is not the same as architectural commit.
- A one-cycle FE-accept-to-commit relationship is possible in the current path,
  but the RTL must still handle cancellation and cleanup.

### Director Cleanup Can Still Fire After Suppressed FE Command

Observed:

- `switch_commit_fe_control_v` was always low in one experiment, but
  `state_n` still entered `e_cmd_fence` and `poison_isd_o` asserted because raw
  `switch_commit_v` was still used in other director paths.

Lesson:

- When splitting commit control, audit every use:
  - `poison_isd_o`
  - `state_n`
  - `fe_cmd_v_li`
  - expected NPC update
  - queue clear/fence behavior

### PC Looping / Wrong Progress Symptoms

Observed:

- One failing waveform showed PC cycling through a small sequence long after a
  context switch.
- `ctxtsw_npc_r` and `resume_npc_r` stayed constant.

Interpretation:

- This points toward wrong control-flow recovery or ownership/context mismatch,
  not merely a slow benchmark.

Open question:

- Need a focused analyzer window around the first divergence, not hundreds of
  cycles later.

## Tool Inventory

This is the current known set of ctxtsw-relevant helper tools. Some are in
`/tmp`, so treat them as useful working artifacts rather than durable repo
infrastructure until copied or rewritten into the repo.

### `/tmp/analyze_postfix.py`

Best current base script.

Behavior:

- Parses the VCD header.
- Matches signals by name fragments.
- Tracks transitions around interesting ctxtsw events.
- Uses `CLKPERIOD = 50000`, matching 50 ns cycle timing.
- Looks for token state, FE accept, current thread id, commit fields, director
  signals, and queue roll/clear signals.

Use this for regenerated VCDs. Extend it by adding name-fragment matches.

### `/tmp/parse_ctxtsw.py`

Behavior:

- More detailed for one old VCD.
- Uses hardcoded VCD identifiers.

Use only for the exact matching old VCD/header.

### `/tmp/parse_thread_ids.py`

Behavior:

- Focuses on a narrow cycle window and thread-id signals.
- Uses hardcoded IDs.

Use only after updating the cycle window and verifying signal identifiers.

### `/tmp/analyze2.py`

Behavior:

- Targeted analysis for `/tmp/gap13_postfix.vcd`.
- Tracks many BE top, calculator, director, scheduler, and CSR signals.
- Fragile across regenerated waveforms.

Use as a reference for what to inspect, not as a permanent tool.

### `/tmp/parse_vcd.py`

Behavior:

- Generic-ish VCD scanner.
- Parses the VCD header and tracks scope-qualified signal names.
- Filters signals with ctxtsw-related name fragments.
- Groups transitions by time and prints compact cycle windows.

Caution:

- The default clock period in this script may not match the current 50 ns
  waveform flow. Confirm `CLKPERIOD` before trusting cycle numbers.

Use:

- Good starting point for broad discovery when we do not yet know exact signal
  names in a regenerated VCD.
- Less ctxtsw-specific than `/tmp/analyze_postfix.py`.

### `/tmp/run_tests.sh`

Behavior:

- Runs a fixed ctxtsw test sweep from `testing`.
- Uses a 120 second timeout per test.
- Reports `BSG PASS`, `BSG FAIL`, or `TIMEOUT/HANG`.
- Current test list:
  - `mt_ctxtsw_smoke_test`
  - `mt_ctxtsw_microbench`
  - `mt_ctxtsw_live_regs_test`
  - `mt_ctxtsw_partial_unroll_benchmark`
  - `mt_ctxtsw_microbench_gap1`
  - `mt_ctxtsw_microbench_gap8`
  - `mt_ctxtsw_microbench_gap12`
  - `mt_ctxtsw_microbench_gap13`
  - `mt_ctxtsw_microbench_gap14`
  - `mt_ctxtsw_microbench_gap16`

Caution:

- This is useful for a quick health sweep after a candidate fix.
- It is not a replacement for focused reproduction because it hides detailed
  logs and uses a hard timeout.

Use:

- After a surgical fix passes the smallest failing test.
- Before declaring an ISD-forwarding state broadly healthy.

### Repo Skills

There are local project skills under `codex-skills/`.

Relevant existing skills:

- `bp-waveform-debug`
  - Use when generating or analyzing BlackParrot waveforms.
  - Should reference the ctxtsw VCD analyzers above.
- `bp-targeted-verification`
  - Use when choosing the smallest credible test set.
  - Should be kept aligned with the current ctxtsw smoke/gap/microbench ladder.
- `bp-branch-experimentation`
  - Use for branch/checkpoint discipline during risky RTL experiments.
- `bp-checkpoint-commit`
  - Use when creating known-good rollback points.

Skill policy:

- Do not create a new skill for every temporary script.
- Extend `bp-waveform-debug` if the workflow is waveform-specific.
- Extend `bp-targeted-verification` if the workflow is test-selection-specific.
- Promote a `/tmp` script into the repo only after it has been useful on at
  least two regenerated waveforms or two separate failing tests.

### Possible Repo Tool to Add Later

If `/tmp/analyze_postfix.py` remains useful, create a durable repo tool such as:

```text
tools/ctxtsw_wave_analyze.py
```

Desired properties:

- accepts VCD path,
- accepts clock period,
- accepts cycle window or auto-detect mode,
- matches by full signal path or regex,
- emits a compact table of token/launch/commit/thread/queue state,
- can compare two VCDs around the first divergent ctxtsw event.

Do not do this until the ISD root-cause workflow is clear enough to avoid
building the wrong abstraction.

## Recommended Next Investigation

1. Restore or identify the best ISD-forwarding branch/state.
2. Confirm it builds and that `fe_ctxtsw_v_o` is enabled.
3. Run:
   - `mt_ctxtsw_smoke_test`
   - `mt_ctxtsw_live_regs_test`
4. Run gap tests from wide to narrow:
   - `gap16`
   - `gap14`
   - `gap13`
   - `gap8`
   - `gap1`
5. Generate waveforms for the nearest pass/fail pair:
   - passing: `mt_ctxtsw_microbench_gap12`
   - failing: `mt_ctxtsw_microbench_gap8`
6. Use `/tmp/analyze_postfix.py` as the first pass.
7. Compare token creation, FE accept, commit cleanup, and current-thread update
   against the expected ISD-forwarding sequence.
8. If a new failure appears, make one RTL change and re-run the smallest
   failing test.
9. Update this document with the exact result.

## Signals to Compare First in a Failing Waveform

Keep the first pass small:

- Token:
  - `pending_ctxtsw_v_r`
  - `pending_ctxtsw_sent_r`
  - `ctxtsw_launch_pending_r`
- Launch/accept:
  - `ctxtsw_launch_lo`
  - `fe_ctxtsw_v_o`
  - `fe_ctxtsw_yumi_i`
- Commit:
  - `commit_pkt.ctxtsw`
  - `commit_pkt.npc_w_v`
  - `commit_pkt.instret`
- Ownership/context:
  - `current_thread_id_lo`
  - `pending_ctxtsw_prev_thread_id_r`
  - `pending_ctxtsw_thread_id_r`
  - `context_npc_r`
- Director/queue:
  - `state_r`
  - `poison_isd_o`
  - `suppress_iss_o`
  - `clear_iss_o`
  - `fe_queue_roll_li`
  - `npc_mismatch_v`

Only add more signals after identifying which of these first diverges.

## Open Items

- Produce a waveform-backed explanation of `gap12` pass versus `gap8` hang.
- Confirm `gap1` and `gap2` after the `gap8`/`gap4` root cause is understood.
- Determine whether `live_regs` is still pre-existing broken in this branch.
- Confirm whether the intended ISD count is 4 or 5 cycles for the benchmark
  endpoint we care about.
- Decide whether the regfile remote-write fix is required for current tests or
  should remain a separate correctness patch.

## 2026-05-13 Claude Version Recheck

Question: what exactly was "Claude's version"?

Findings:

- The top-level branch records `import/black-parrot` at `55037827`
  (`fix ctxtsw retire gating and clean waveform flow`).
- The active BP branch before this recheck was not that recorded commit. It was
  `f574c642` on `ctxtsw-isd-repair`, a later sideband/ISD stack ending at
  `prepare ctxtsw early ownership handoff`.
- The saved local BP diff before the recheck had two files:
  - `bp_be/src/v/bp_be_checker/bp_be_scheduler.sv`
    - `fe_queue_roll_li = commit_pkt_cast_i.npc_w_v & ~commit_pkt_cast_i.ctxtsw`
  - `bp_be/src/v/bp_be_regfile_mt.sv`
    - mostly remote-write comment cleanup,
    - plus a real forwarding/data fix:
      `rs_data_n = replace_rs ? w_data_mux : fwd_data_lo`.

Reproduction attempts:

- Tested `631a5ed8 + scheduler one-liner`.
  - `mt_ctxtsw_microbench_gap8` hung after NBF load.
- Tested top-level recorded `55037827 + scheduler one-liner`.
  - `mt_ctxtsw_smoke_test` aborted with Verilator
    `Active region did not converge`.
- Tested plain recorded `55037827` with no scheduler one-liner.
  - `mt_ctxtsw_smoke_test` aborted the same way.
- Restored the previous active BP state:
  - branch `ctxtsw-isd-repair`,
  - commit `f574c642`,
  - local scheduler/regfile diff restored.
  - `mt_ctxtsw_smoke_test` passed:
    - `[BSG-PASS] ctxtsw smoke test completed`
    - `BSG PASS`
    - `minstret delta: 3515 (0xdbb)`.

Conclusion:

- In this checkout, `55037827` is not a usable base for Claude's passing gap
  report. It fails before the gap benchmark is meaningful.
- The only state currently verified smoke-clean is the later `f574c642`
  sideband/ISD stack plus the saved local scheduler/regfile edits.
- Interpret Claude's report as "scheduler-roll suppression was the important
  one-line behavioral fix on top of a later ISD/sideband stack", not as
  "`55037827 + one line`".

Next pinpoint step:

- Use the restored smoke-clean state as the baseline.
- Re-run a small ordered set:
  - `mt_ctxtsw_smoke_test` already passed.
  - `mt_ctxtsw_microbench_gap14` should be the first expected pass.
  - `mt_ctxtsw_microbench_gap8` is the first high-value expected fail/hang in
    the current reports.
- Generate/inspect waveforms for the nearest pass/fail pair only after the
  non-trace pass/fail pair is reproduced on the restored state.

### Build-Flow Trap

`make run PROG=...` in
`cosim/black-parrot-minimal-example/verilator` can silently reuse the previous
program image.

Reason:

- `prog.riscv` has no dependency on `$(PROG)`.
- `run` uses `prog.nbf` through an order-only prerequisite.
- If `prog.riscv`/`prog.nbf` already exist, changing `PROG=` may still run the
  old binary.

Observed:

- Ran `make ... run PROG=mt_ctxtsw_microbench_gap14` after a smoke run.
- Simulator printed the smoke banner:
  `=== ctxtsw smoke test ===`.
- `objdump -s -j .rodata prog.riscv` confirmed `prog.riscv` still contained
  the smoke-test strings.

For now, clean before every different `PROG`:

```text
make -C cosim/black-parrot-minimal-example/verilator clean
make -C cosim/black-parrot-minimal-example/verilator run PROG=<test>
```

### Restored-State Gap Results

State:

- BP branch: `ctxtsw-isd-repair`.
- BP commit: `f574c642`.
- Local BP diff:
  - scheduler ctxtsw roll suppression,
  - regfile remote-write forwarding fix.
- Verilator build cleaned before switching programs.

Results:

- `mt_ctxtsw_smoke_test`
  - PASS.
  - `minstret delta: 3515 (0xdbb)`.
- `mt_ctxtsw_microbench_gap14`
  - PASS.
  - banner confirmed: `=== Context Switch Gap Microbenchmark ===`.
  - `Gap instructions: 0xe`.
  - `Cold round-trip: 0xe`.
  - `Warm round-trip 0: 0xe`.
  - `Warm round-trip 1: 0xe`.
  - `Warm min single-switch estimate: 0x7`.
  - `minstret delta: 26280 (0x66a8)`.
- `mt_ctxtsw_microbench_gap8`
  - HANG.
  - Cleaned before run.
  - Reached NBF load and then produced no benchmark output for more than two
    minutes.
  - Simulation was stopped manually.

Current confirmed boundary:

- `gap14` passes.
- `gap8` hangs.
- Need test `gap13`/`gap12` only if the exact minimum passing gap matters; for
  root-cause waveform work, `gap14` versus `gap8` is enough.

Additional recheck:

- The current restored RTL has the FE ctxtsw sideband disabled:
  `bp_be_top.sv` ties `fe_ctxtsw_v_o` to `1'b0`.
- `ctxtsw_launch_lo` still pulses in the BE, but it is not consumed by the FE
  sideband in this state.
- A clean non-trace `mt_ctxtsw_microbench_gap8` run was left running after NBF
  for roughly three minutes with no benchmark banner/output, then stopped.
- A trace-enabled `gap8` capture (`gap8_repro.fst`) reached the benchmark setup
  region and showed repeated normal frontend redirects/replays before output;
  it did not yet capture the final hang point.
- At ctxtsw commits visible in that trace, `fe_queue_roll_li` remained low when
  `commit_pkt.ctxtsw` was high, so the scheduler roll-suppression line is active
  in the tested build.
