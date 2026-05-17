# Context Switch Forwarding Plan

This document is the working plan for context-switch forwarding. The immediate
goal is not to add more speculative behavior or move logic earlier by default.
The first goal is to prove, with code analysis, tests, and waveforms, that the
existing ISD-forwarding version is healthy and behaves exactly as intended. Only
after the ISD path is correct and measured should we decide whether an IF2 fast
path is worth implementing.

## Current Starting Point

ISD forwarding is now reconstructed in a scheduler-only baseline and passes some
focused Stage 1 tests, but it is not yet proven correct across the dense/gap
suite. Stage 1 is still a verification and repair phase: finish waveform
confirmation, keep the change set clean, and fix the current queue/ownership
boundary before moving logic earlier into IF2.

Recommended workflow:

1. Create a dedicated branch for the ISD repair work.
2. Make one small change or measurement at a time.
3. Run the narrowest relevant test after each change.
4. Use waveform analysis as evidence for both failures and performance claims.
5. Commit only verified-good checkpoints.
6. Record every failed attempt in `CTXTSW_FORWARDING_INVESTIGATION.md`.

High-level order:

1. Make the current ISD-forwarding path pass the correctness suite.
2. Measure one-off or round-trip context-switch latency and explain the number
   with waveforms.
3. Compare the measured result against the theoretical 3-cycle target and list
   exactly which conditions are or are not true.
4. Evaluate dense steady-state throughput only after the one-off path is stable.
5. Treat IF2 forwarding as an optional optimization behind a decision gate, not
   as the default next step.
6. Use thread tagging as the preferred safety direction for mixed in-flight
   contexts, rather than relying on untagged queue rollback suppression.

Waveform policy:

- For hangs or unexpected performance regressions, run the smallest failing
  test with `TRACE=1` by default before making a new RTL change.
- For performance improvements, collect waveforms for at least one
  representative passing run before recording the cycle count as a fact.
- Do not compare a traced run from the stacked worktree against Claude's
  scheduler-only report as if they were the same RTL.
- At checkpoints, do a clean rebuild before collecting waveforms that will be
  used as evidence.
- Each claimed latency should name the measured endpoints, for example
  `ctxtsw ISD -> target fetch`, `ctxtsw ISD -> target ISD`, or
  `ctxtsw retirement -> target retirement`.

## What We Know

- The architectural commit point for a context switch is `commit_pkt.ctxtsw`.
- `commit_pkt.ctxtsw` comes from retirement:
  - `bp_be_pipe_sys.sv` latches `retire_ctxtsw_r`.
  - `bp_be_csr.sv` emits `commit_pkt.ctxtsw = retire_pkt.instret & retire_ctxtsw_v`.
- The existing BE decoder path identifies `ctxtsw` after the FE packet reaches
  the scheduler/issue path.
- Current immediate-form context switches are encoded as CSR immediate writes to
  CSR `0x081`.
- The target thread id for immediate-form ctxtsw can be read directly from the
  CSR immediate field, so this first fast path can be limited to immediates.
- Existing tests are enough to exercise the basic immediate path and regfile
  ownership cases, but they are not yet enough to prove every early-dispatch
  safety case:
  - `mt_ctxtsw_smoke_test`
  - `mt_ctxtsw_live_regs_test`
  - `mt_ctxtsw_microbench`
  - `mt_ctxtsw_microbench_trace`
  - `mt_ctxtsw_microbench_barrier`
  - gap tests: `gap1`, `gap2`, `gap4`, `gap8`, `gap12`, `gap13`, `gap14`,
    `gap16`
  - `mt_ctxtsw_partial_unroll_benchmark`
- Additional tests are still needed if target instructions can reach BE before
  the old ctxtsw commits, especially loads, stores, CSR operations, exceptions,
  and branch redirects close to the switch boundary.
- Current RTL facts from source review:
  - `ctxtsw` is classified in `bp_be_scheduler.sv` as a CSR write to `0x081`.
  - Immediate-form target TID comes from the CSR immediate field; register-form
    target TID comes from the integer source register value.
  - The FE sideband port exists, and FE can accept it, but this worktree has
    `fe_ctxtsw_v_o` tied to `1'b0` in `bp_be_top.sv`. No sideband-forwarding
    latency claim counts until this is intentionally enabled and waveforms show
    `fe_ctxtsw_v_o`/`fe_ctxtsw_yumi_i`.
  - The current fast token is not created in the same cycle as scheduler
    classification. `dispatch_pkt.ctxtsw_v` is latched through reservation, and
    `fast_ctxtsw_v_o` is driven from `reservation_r`.
  - The pending ctxtsw state is a single slot in the current stacked worktree.
    Dense back-to-back switches can overwrite pending state unless token
    creation is explicitly guarded or made multi-entry.
- Current design decision:
  - Use thread tagging to make queue entries, register reads, writebacks, and
    replay/roll decisions explicitly belong to the thread that produced them.
  - Treat `fe_queue_roll_li = commit_pkt_cast_i.npc_w_v &
    ~commit_pkt_cast_i.ctxtsw` as an incomplete experiment until the queue has a
    clear thread/epoch-valid rule across ctxtsw boundaries.
  - The intended safe model is not "the active thread changed, therefore all
    queued work changed meaning." It is "each queued instruction carries its
    issuing thread, and commit/finalization decides which tagged stream may
    advance or be replayed."
- Prior results showed spacing matters, but the gap tests themselves also need
  assembly-shape validation. `gap14` originally compiled into a `jal
  controlled_gap` call/return sequence while smaller gaps were straight-line
  nops, so it was not testing the same thing. The shared gap helper is now forced
  inline so the gap variants are intended to remain straight-line.
- Claude's later report clarified the earlier gap result: the state where
  `gap1` through `gap16` all passed was the clean scheduler-only fix:
  `fe_queue_roll_li = commit_pkt_cast_i.npc_w_v & ~commit_pkt_cast_i.ctxtsw`.
  Earlier `gap14` failures came from stacked sideband experiments, stale
  rebuilds, and the gap helper compiling into an out-of-line call/return
  sequence.
- Current `ctxtsw-isd-repair` scheduler-only reconstruction:
  - active BP submodule RTL diff is the scheduler rollback mask plus the
    pre-existing `bp_be_regfile_mt.sv` remote-write forwarding change.
  - stale stacked sideband changes were saved to
    `/tmp/ctxtsw_stacked_current.patch` and removed from the active RTL.
  - fixed straight-line `gap14` passes non-trace with `0xe/0xe/0xe`, estimate
    `0x7`.
  - `gap12`, `gap13`, and `gap16` also pass non-trace with warm estimate
    `0x7`.
  - after a clean non-trace rebuild and smoke pass, `gap8` and `gap4` hang
    before benchmark output; this is now the controlled-gap boundary to debug.
  - dense `mt_ctxtsw_microbench` passes with `0xe` round-trip and `0x7`
    estimate.
  - `mt_ctxtsw_partial_unroll_benchmark` passes and reports `0x4` cycles per
    switch for its endpoint. A clean traced run on 2026-05-14 confirmed this is
    a real steady-state throughput result: consecutive switch detections and
    commit redirects appear at the expected cadence. It is not proof of
    arbitrary single-switch latency or correctness with nearby memory/replay
    events.
  - `mt_csr_isolation_test`, `mt_regfile_test`, and
    `mt_frf_isolation_test` all end in `BSG PASS`.
  - next Stage 1 work is waveform confirmation and checkpoint cleanup before
    reintroducing any sideband/fast-path changes.
- Claude created waveform-analysis scripts in `/tmp`:
  - `/tmp/analyze_postfix.py` is the best starting point because it parses VCD
    headers and matches signals by name fragments.
  - `/tmp/parse_ctxtsw.py`, `/tmp/parse_thread_ids.py`, and `/tmp/analyze2.py`
    are useful for specific old VCDs but rely more heavily on hardcoded signal
    identifiers.

## What We Are Not Yet Sure About

- Whether the current dirty worktree is actually the verified 5-cycle
  ISD-forwarding state. Source review shows sideband launch is disabled in this
  worktree, so any prior sideband-forwarding number must be reproduced on the
  exact RTL that produced it.
- Whether the 5-cycle result was measuring true general ctxtsw latency, or only
  FE overlap in a benchmark where switches are spaced favorably.
- Whether dense back-to-back ctxtsw cases fail because of:
  - BE thread ownership changing too early,
  - FE queue roll/poison dropping an instruction,
  - duplicate commit-time cleanup,
  - stale pending token state or single-slot pending-token overwrite,
  - context save/restore ordering,
  - wrong thread metadata on FE redirect,
  - or some interaction between these.
- Whether all target-context side effects are naturally blocked until the old
  ctxtsw commits. Code analysis suggests memory requests can be issued before
  commit, so arbitrary target BE dispatch before commit is not globally safe.
- Whether IF2 forwarding can safely redirect from any packet position, or only
  when ctxtsw is the first valid instruction in the packet. The intended design
  is packet-position aware, like branches.

## Latency Definitions

Do not use a bare "3-cycle context switch" claim without naming the endpoint.
The relevant endpoints are:

- `ctxtsw detect`: cycle where the switch is first classified, ideally ISD/C0.
- `target fetch launch`: cycle where FE launches the target thread PC into I$.
- `target FE queue`: cycle where the target instruction is available to the
  FE->BE queue.
- `target ISD`: cycle where the target instruction dispatches from BE ISD/C0.
- `ctxtsw commit`: cycle where `commit_pkt.ctxtsw` retires architecturally.
- `target retirement`: cycle where the first target instruction retires.

For the current pipeline, a best-case target instruction after redirect still
has to pass through:

```text
target F0 -> target F1/TL -> target F2/TV+FE queue -> target ISD/C0
```

Because FE queue output can be accepted and predecoded by the BE issue queue in
the same cycle, the minimum from target fetch launch to target ISD is about three
cycle intervals in the normal I$ hit path:

```text
T0: target F0 launch
T1: target F1/TL
T2: target F2/TV, FE queue output, BE enqueue/preissue
T3: target ISD/C0
```

Therefore, a true 3-cycle `ctxtsw detect -> target ISD` result requires the
target fetch launch to occur in the same cycle as ctxtsw detection. If target
fetch launch is one cycle later, the best target-ISD result becomes about four
cycles. This is an architectural timing distinction, not measurement noise.

In the current inspected RTL, the tokenized ISD path does not satisfy that
same-cycle launch requirement: scheduler classification feeds reservation, and
`fast_ctxtsw_v_o` is produced from `reservation_r`. Treat a same-cycle ISD
launch as a new implementation requirement, not as a property of the present
worktree.

## Three-Cycle Best-Case Conditions

The theoretical 3-cycle goal is achievable only under a narrow best-case
definition:

```text
ctxtsw ISD/C0 detects switch and launches target fetch in the same cycle
target I$ and ITLB hit
target FE queue entry is accepted in F2
target instruction reaches ISD/C0 three cycle intervals after ctxtsw detection
```

Conditions that must all hold for this best case:

- Immediate-form ctxtsw target thread ID is available without waiting for a
  register-file operand.
- Target restart bundle is available in the detection cycle: target PC,
  privilege mode, translation enable, ASID, and target thread ID.
- FE restart path is direct and is not queued behind normal commit-time
  `fe_cmd`.
- FE thread identity and shadow privilege/translation/ASID are updated before
  target fetch observes them.
- The FE shadow privilege/translation/ASID caveat is real: the sideband accept
  path can drive a new PC combinationally, but shadow context updates are
  registered. Same-cycle fetch is valid only if the translation context is
  unchanged/irrelevant, the shadow context is bypassed, or launch is delayed
  until the registered shadow context is visible.
- Target I$ access hits.
- Target ITLB/PMA lookup hits or is otherwise immediately usable.
- FE queue and BE issue queue are ready.
- No old-thread younger instruction is emitted past the ctxtsw boundary.
- Commit-time ctxtsw finalization still occurs exactly once.
- A commit-time FE redirect is suppressed only if the early redirect was
  accepted.
- Older redirects, traps, exceptions, and failed/squashed ctxtsw instances cancel
  the early target stream cleanly.
- Target BE dispatch is either naturally delayed until safe or explicitly held
  before any unsafe side effect can issue.

If any of these are false, the measured result may still be correct, but the
plan must document which condition moved the best case from 3 cycles to 4, 5, or
more.

## Stage 1: Repair and Verify ISD Forwarding

Goal: make the existing ISD-level forwarding correct, stable, and explainable
before moving the detection point earlier. This includes fixing current failures,
not just measuring the passing cases.

### 1. Establish the Exact ISD State

Tasks:

- Create or switch to a dedicated branch from the best available ISD-forwarding
  commit or patch set.
- Record the top-level commit, nested `import/black-parrot` commit, and dirty
  files.
- Reconstruct and test the scheduler-only baseline before debugging the stacked
  sideband version:
  - `bp_be_scheduler.sv`: suppress FE queue rollback when the retiring redirect
    is a ctxtsw.
  - Keep `bp_be_top.sv`, `bp_be_calculator_top.sv`, `bp_fe_controller.sv`, and
    `bp_be_director.sv` otherwise at their baseline state for this measurement.
- Keep the controlled-gap tests straight-line:
  - `controlled_gap()` must remain forced inline.
  - verify at least `gap14` with objdump after changing compiler flags or the
    gap helper.
- Confirm `fe_ctxtsw_v_o` is actually enabled for the ISD sideband path.
- Confirm the director port list and instantiation compile cleanly.
- Confirm fast BE handoff is either intentionally disabled or intentionally
  enabled; do not leave it half-connected.

Expected result:

- Static build succeeds.
- The starting state is identified as partially passing: scheduler-only passes
  dense microbench, smoke, isolation, partial-unroll, and gap12+ tests, but
  tighter controlled gaps still hang.
- No unrelated dirty RTL is mixed into the measurement.
- Scheduler-only baseline reproduces the Claude-reported result before further
  ISD/sideband repair continues.

Verification:

```sh
git status --short --branch
git -C import/black-parrot status --short --branch
git -C import/black-parrot diff --check -- \
  bp_be/src/v/bp_be_top.sv \
  bp_be/src/v/bp_be_checker/bp_be_director.sv \
  bp_be/src/v/bp_be_checker/bp_be_scheduler.sv \
  bp_be/src/v/bp_be_calculator/bp_be_calculator_top.sv \
  bp_fe/src/v/bp_fe_controller.sv
make -C /home/coyang/zynq-parrot-copy/zynq-parrot -j24 prep_lite
```

### 2. Code-Audit the ISD Protocol

Tasks:

- Identify the exact cycle where ctxtsw is first classified.
- Identify the exact signal that creates the pending token.
- Identify the exact signal that launches FE redirect.
- Identify the exact signal that changes `current_thread_id_lo`.
- Identify the exact signal that saves the old resume PC.
- Identify all cancel paths.
- Confirm commit-time duplicate FE command suppression.
- Confirm commit-time cleanup still preserves architectural state.

Signals/modules to inspect:

- `bp_be_scheduler.sv`
  - `issue_ctxtsw_v`
  - `dispatch_pkt_cast_o.ctxtsw_v`
  - `dispatch_pkt_cast_o.ctxtsw_target_tid`
  - `fe_queue_en_li`
  - `fe_queue_roll_li`
- `bp_be_calculator_top.sv`
  - `fast_ctxtsw_v_o`
  - `fast_ctxtsw_pipe_safe_o`
  - `fast_ctxtsw_resume_npc_o`
- `bp_be_top.sv`
  - `pending_ctxtsw_v_r`
  - `pending_ctxtsw_sent_r`
  - `ctxtsw_launch_pending_r`
  - `current_thread_id_lo`
  - `context_npc_r`
  - `retire_thread_id_lo`
- `bp_be_director.sv`
  - `ctxtsw_launch_o`
  - `switch_commit_v`
  - any `switch_commit_fe_control_v`-style split
  - `poison_isd_o`
  - `state_r/state_n`
  - `fe_cmd_v_o`
- `bp_fe_controller.sv`
  - `ctxtsw_accept_v`
  - `redirect_v_o`
  - `redirect_pc_o`
  - `redirect_br_metadata_fwd_o`

Questions to answer before changing RTL:

- Does `commit_pkt.ctxtsw` still perform all architectural finalization?
- Does early FE redirect happen exactly once per ctxtsw?
- Is the later commit-time FE command suppressed only when the early command was
  accepted?
- Does the director still enter `e_cmd_fence` on a commit that has already been
  handled by the sideband?
- Does `poison_isd_o` kill any instruction that should instead be held?
- On cancel, do we restore the previous thread id and clear the pending token?

### 3. Run Focused Correctness Tests

Run these before performance tuning:

```sh
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_smoke_test
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_live_regs_test
```

Expected result:

- Both pass.
- `smoke_test` is valuable as a minimal hang sentinel even though it is not a
  performance benchmark. Keep it in the suite.

If either fails:

- Stop performance work.
- Generate a waveform for the failing test.
- Verify token create, FE accept, commit, current-thread update, and resume PC
  save around the first ctxtsw.

### 4. Measure One-Off / Round-Trip Latency First

Before optimizing dense switch streams, measure a simple case such as:

```text
n normal instructions
1 ctxtsw
n normal instructions on target thread
```

If a one-way test is inconvenient, use the smallest round-trip test that is easy
to reason about. The important requirement is that the benchmark shape is simple
enough to identify the switch event, target fetch, target ISD, switch commit,
and target retirement in a waveform.

Tasks:

- Run the narrowest available one-off or round-trip microbench.
- Record the raw reported cycle count.
- Generate a waveform for a representative passing run.
- Mark the following events in the waveform:
  - ctxtsw FE packet / instruction PC
  - `dispatch_pkt.ctxtsw_v` or the chosen detection signal
  - pending token creation
  - FE sideband or FE command acceptance
  - target thread fetch launch
  - target FE queue output
  - target ISD dispatch
  - `commit_pkt.ctxtsw`
  - first target `instret`
- Explain the measured latency in terms of the named endpoints from
  "Latency Definitions".

Expected result:

- The one-off or round-trip number is stable across repeated runs.
- The measured number is explained by waveform evidence, not only by benchmark
  printout.
- A 5-7 cycle result is acceptable at this phase if the waveform explains which
  cycles are structural, architectural, or implementation artifacts.

Questions to answer from the waveform:

- Does target fetch launch in the same cycle as detection, one cycle later, or
  only at commit?
- Does target FE queue output arrive at the expected I$ hit latency?
- Does target ISD dispatch naturally wait until `commit_pkt.ctxtsw`, or does it
  arrive earlier?
- If target ISD arrives earlier, is it held before unsafe side effects?
- Is the later commit-time FE command correctly suppressed after early accept?

Do not proceed to dense throughput tuning until this measurement is stable and
explained.

### 5. Compare Against the Three-Cycle Goal

After the one-off measurement is stable, compare it against the best-case
conditions above.

Tasks:

- Fill out a table for each required 3-cycle condition:
  - observed true,
  - observed false,
  - unknown, needs waveform or code audit.
- For every false condition, write whether it is:
  - a real architectural constraint,
  - a fixable implementation delay,
  - a correctness safety requirement,
  - or a measurement endpoint mismatch.
- Decide whether the current ISD path can plausibly reach the desired target
  without IF2 forwarding.

Expected result:

- If the ISD path can reach the target, stop pursuing IF2 for now and focus on
  correctness/density.
- If the ISD path is stable but stuck at 4, 5, or more cycles for a documented
  reason, decide whether that remaining gap justifies IF2 complexity.
- If the number cannot be explained, keep debugging the ISD path before changing
  the forwarding point.

### 6. Run Density/Gaps Before Full Microbench

Run controlled gap tests to localize the minimum safe spacing:

```sh
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_gap16
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_gap14
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_gap13
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_gap8
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_gap1
```

Expected result for a robust ISD version:

- All gap tests pass.
- The measured cycle count is stable and explainable.

If `gap14` passes but `gap13` fails:

- Do not guess. Compare gap13 and gap14 waveforms around the first failing
  transition.
- The key question is what state is still busy one cycle later in gap13.

Current state note:

- `gap14` does not currently pass, so the immediate next waveform should be
  `gap14` around the first wrong instruction, not a gap13/gap14 pass/fail pair.
- Focus on FE redirect, realigner, and FE queue metadata after the `0->2->0`
  switch and before the corrupt main-thread instruction at `0x800002da`.

### 7. Run Performance Tests

Run:

```sh
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_partial_unroll_benchmark
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_trace
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench_barrier
make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench
```

Expected result:

- `partial_unroll` should report the intended ISD-forwarding cycle count.
- The dense `microbench` should pass. If it does not, the implementation is not
  robust enough to treat as a verified base.
- `trace` passing while `barrier` or original `microbench` hangs means spacing or
  live-value scheduling is hiding the bug.

Expected ISD count:

- Best case should be documented by endpoint. It may be 3, 4, or 5 cycles
  depending on whether the measured endpoint is target fetch, target ISD arrival,
  first target retirement, or added steady-state dispatch slots.
- Any 7-, 8-, or 9-cycle result needs a waveform-backed explanation.

### 8. Waveform Acceptance Checklist for ISD

For each representative passing and failing case, check only these relationships
first:

1. `ctxtsw` detection -> pending token create
   - Compare `fast_ctxtsw_v_lo` or `dispatch_pkt.ctxtsw_v` with
     `pending_ctxtsw_v_r`.
   - Expected for the current tokenized path: token appears after scheduler
     detection, not in the same cycle. If the goal is true 3-cycle
     `detect -> target ISD`, this checkpoint must prove a new same-cycle launch
     path instead.

2. Pending token -> FE sideband accept
   - Compare `pending_ctxtsw_v_r`, `ctxtsw_launch_lo`, `fe_ctxtsw_v_o`,
     `fe_ctxtsw_yumi_i`.
   - Hard precondition: `fe_ctxtsw_v_o` must not be tied off. In the current
     inspected worktree it is tied to zero, so this checklist item should fail
     until the sideband is intentionally enabled.
   - Expected after enablement: launch happens once; `yumi` marks acceptance.

3. FE accept -> commit cleanup
   - Compare `fe_ctxtsw_yumi_i`, `pending_ctxtsw_sent_r`,
     `commit_pkt.ctxtsw`, `fe_cmd_v_o`.
   - Expected: commit still happens; duplicate FE ctxtsw command is suppressed
     if FE already accepted the sideband.

4. Commit cleanup -> next target retirement
   - Compare `commit_pkt.ctxtsw`, `current_thread_id_lo`, FE queue PC, ISD PC,
     and target `instret`.
   - Expected: the next target instruction is from the target thread and target
     PC, with no dropped old-thread instruction.

5. Cancel path
   - Compare `commit_pkt.npc_w_v & ~commit_pkt.ctxtsw`,
     `pending_ctxtsw_v_r`, `current_thread_id_lo`, and `context_npc_r`.
   - Expected: pending target stream is canceled and ownership returns to the
     previous thread.

Use `/tmp/analyze_postfix.py` as the starting script for VCD analysis. Extend it
by signal name, not hardcoded VCD identifiers, so regenerated waveforms remain
usable.

### 9. Stage 1 Done Criteria

Stage 1 is complete only when:

- Static build passes.
- Smoke and live-reg tests pass.
- One-off or round-trip latency is stable and waveform-explained.
- The measured one-off number has been compared against the 3-cycle best-case
  conditions.
- All named gap tests pass. A waveform-explained failing boundary is useful
  debug information, but it is not a Stage 1 completion condition.
- Dense `mt_ctxtsw_microbench` passes.
- `partial_unroll` reports a cycle count that is endpoint-defined and
  waveform-explained.
- Waveforms confirm the intended one-launch, one-commit, no-duplicate-FE-command
  protocol. If sideband remains disabled, the plan must explicitly record that
  Stage 1 measured scheduler/commit behavior only, not sideband forwarding.
- A checkpoint commit records the known-good ISD state and measured results.

If any existing test still fails, Stage 1 is not complete. In that case, the next
action is waveform/code root-cause analysis on the smallest failing case, not IF2
implementation.

## Stage 2: Evaluate Steady-State Throughput

Goal: after one-off latency is stable, decide whether dense streams of context
switches can approach constant 3-cycle throughput, and whether that work is
worth doing now.

Do not assume that single-switch latency implies dense throughput. A back-to-back
stream adds pressure on token cleanup, commit finalization, FE/BE thread
identity, issue queue state, and side-effect safety.

For a stream like:

```text
ctxtsw, ctxtsw, ctxtsw, ...
```

or:

```text
n instructions, ctxtsw, n instructions, ctxtsw, ...
```

the following must hold before expecting 3-cycle steady-state behavior:

- A new ctxtsw token can be created before or while the previous one finalizes,
  without overwriting or reusing stale pending state.
- The implementation either prevents `fast_ctxtsw_v` from overwriting an
  occupied pending slot, or replaces the single pending slot with a structure
  that can represent all in-flight switches allowed by the scheduler.
- Every early launch is tied to exactly one surviving ctxtsw instance.
- Commit cleanup for switch N does not block, duplicate, or cancel switch N+1.
- FE thread identity is correct before each target fetch.
- BE active-thread identity is correct before each target ISD, or target ISD is
  explicitly held.
- Retire-thread identity and active-thread identity are separated when early FE
  restart overlaps old-thread retirement.
- Register-file reads use the correct issuing thread, either through active
  thread update, per-entry thread tagging, or an explicit hold until safe.
- Writebacks and late writebacks carry the issuing thread and cannot be
  misattributed after a switch.
- Old-thread resume PC/context is saved exactly once per switch.
- FE queue roll/read/clear does not drop a ctxtsw packet or a target packet.
- Target memory or CSR side effects cannot issue before the prior switch is
  architecturally safe.
- Duplicate commit-time FE commands are suppressed only for switches whose early
  redirect was accepted.
- Cancel paths clear pending state and restore the previous FE/BE view.

Verification:

- Run gap tests from wide to dense and compare the smallest failing gap against
  the nearest passing gap with waveforms.
- Treat `gap1`/`gap2` and dense `mt_ctxtsw_microbench` as the real steady-state
  evidence; spaced partial-unroll results are not enough.
- Waveforms must show token create, FE accept, commit cleanup, current-thread
  update, issue queue read/roll, and first target ISD for at least one dense
  passing case.

Decision:

- The selected safety direction is thread tagging. If steady-state 3-cycle
  throughput only requires completing thread/epoch-valid queue semantics and
  small token cleanup, keep it in scope after one-off latency is stable.
- If tagging exposes broader BE ownership refactoring, document the required
  work and split it into checkpointed steps rather than adding more special
  cases to the untagged rollback path.
- Do not start IF2 forwarding as a workaround for unexplained dense ISD bugs.

### Thread-Tagged Queue Direction

Thread tagging should make the fast path safe by removing ambiguity from mixed
old-thread and target-thread work in the FE/BE queues.

Initial tagging scope:

- FE-to-BE / issue queue entries carry an issuing thread id.
- Scheduler dispatch, hazard detection, and register-file read selection use the
  entry thread id, not only `current_thread_id_lo`.
- Writeback and late writeback already need issuing-thread metadata; verify
  that all integer, FP, memory, CSR, replay, and exception paths preserve it.
- Queue roll/replay logic must only re-present entries that are valid for the
  architectural recovery thread/epoch.
- A retiring `commit_pkt.ctxtsw` finalizes ownership and marks which target
  stream is architectural; it should not reinterpret already queued old-thread
  entries as target-thread entries.

Verification focus:

- Pick the smallest failing controlled-gap case and compare it to the nearest
  passing case.
- In waveforms, compare each queued/dispatching instruction's PC with its tagged
  thread id, `current_thread_id_lo`, `commit_pkt.ctxtsw`, `commit_pkt.npc_w_v`,
  `fe_queue_roll_li`, and the first memory/replay event after the final switch.
- The first target instruction may be fetched early, but it must either carry
  the correct target tag or be held until the tag is architectural.

## Stage 3: Optional Move Earlier to IF2

Goal: detect immediate-form ctxtsw in the FE after realign/scan and redirect the
FE target stream earlier. Target expected behavior must be stated by endpoint:
same-cycle IF2 redirect could make target fetch start immediately and target
queue availability appear after the normal hit pipeline, while a registered IF2
redirect is closer to detection+3 cycles for target queue availability on an
I$ hit. Correctness remains anchored at `commit_pkt.ctxtsw`.

This stage should run only after the ISD path is correct, measured, and compared
against the 3-cycle best-case conditions. If verified ISD forwarding already
meets the target endpoint and dense tests are stable, skip IF2 forwarding.

### IF2 Design Shape

The IF2 fast path should behave like branch packetization:

- If a fetch packet contains older instructions before ctxtsw, those older
  instructions must still be delivered first.
- If the packet contains `instr0, instr1, ctxtsw, younger0`, enqueue through
  `ctxtsw` and redirect only the younger stream after ctxtsw.
- If a branch appears before ctxtsw in the same packet, the branch wins.
- If ctxtsw appears before a branch in the same packet, ctxtsw wins and the
  packet ends at ctxtsw.
- First version may support only immediate-form ctxtsw.
- IF2 parsing is a design goal, not current RTL. The existing FE scan logic is a
  plausible place to add it because it already handles instruction boundaries
  and branch cut counts.
- IF2 can parse the immediate target TID, but it does not by itself know the
  target PC, privilege mode, translation-enable state, or ASID. Those live in BE
  context state today. IF2 redirect therefore requires either a new FE-visible
  context lookup/bundle, or a BE-provided context bundle that arrives early
  enough for the chosen timing target.

### Step 3.1: Add Pure IF2/Scan Parsing

Implement detection only; no redirect yet.

Tasks:

- In FE realign/scan area, identify immediate-form CSR writes to CSR `0x081`.
- Compute:
  - `ctxtsw_found_v`
  - `ctxtsw_count`
  - `ctxtsw_pc`
  - `ctxtsw_resume_npc`
  - `ctxtsw_target_tid`
- Respect compressed-instruction boundaries and packet count.
- Ensure branch-before-ctxtsw priority is explicit.

Verification:

- Build only.
- Run smoke test to ensure no behavior changed.
- Add or run parser tests/waveforms for:
  - compressed instruction boundaries,
  - full-width instruction boundaries,
  - branch before ctxtsw in the same packet,
  - ctxtsw before branch in the same packet,
  - ctxtsw not first in the packet,
  - multiple CSR writes or ctxtsw-like encodings in one packet.
- Generate a waveform or add temporary trace only if needed to confirm detection
  in existing tests.

Commit:

- Commit this as a no-functional-change IF2 parser checkpoint.

### Step 3.2: Packetize Through Ctxtsw

Tasks:

- When IF2 scan finds ctxtsw before any branch, set FE queue packet count to end
  at ctxtsw.
- Do not redirect yet.
- Ensure older same-packet instructions are preserved.

Verification:

- Run smoke, live-reg, gap14, gap13.
- Re-run the parser/packetization cases from Step 3.1, especially branch
  priority and ctxtsw-not-first packet cuts.
- Waveform check:
  - packet PC/count includes older instructions and ctxtsw,
  - younger instructions after ctxtsw are not included in the same packet.

Commit:

- Commit only if behavior is unchanged or intentionally explained.

### Step 3.3: Launch FE Redirect from IF2 Ctxtsw

Tasks:

- Provide target PC/thread/privilege/translation/ASID metadata to FE redirect
  logic. The parser alone can provide immediate target TID; target context must
  come from a new FE-visible context lookup or from BE.
- Mark the target stream as pending/speculative.
- Keep architectural BE ownership unchanged until `commit_pkt.ctxtsw`.
- Suppress duplicate commit-time FE command if IF2 redirect was accepted.
- Decide explicitly whether shadow context is bypassed for same-cycle launch or
  whether target fetch is delayed until the registered FE shadow context is
  visible.

Verification:

- Smoke and live-reg first.
- Then gap16, gap14, gap13, gap8, gap1.
- Then partial-unroll and dense microbench.
- Waveform check:
  - IF2 ctxtsw detection,
  - FE redirect accept,
  - target fetch starts before BE commit,
  - BE dispatch of target-context instructions is held until safe if needed.

Commit:

- Commit only if all correctness tests pass and the performance shift is
  waveform-confirmed.

### Step 3.4: Gate Target BE Dispatch if Needed

This is the main safety valve.

Tasks:

- If IF2 redirect allows target instructions to reach BE before ctxtsw commit,
  prevent target-context instructions from issuing side effects before the old
  ctxtsw commits.
- Prefer holding FE queue/ISD dispatch over poisoning and dropping entries.
- Reuse existing scheduler hold paths where possible:
  - `fe_queue_en_li`
  - `suppress_iss_i`
  - hazard-style blocking
- Avoid relying on `poison_isd_i` as a hold mechanism; it suppresses dispatch and
  can drop queue entries.

Verification:

- Waveform must show target packets are held, not discarded.
- Dense microbench must pass.
- Memory-side tests should be added later if target code can include loads or
  stores close to ctxtsw.

### Step 3.5: Extend Beyond Immediate Forms

This is out of scope for the first IF2 implementation.

Register-form ctxtsw is possible, but it cannot be fully resolved in IF2 without
knowing the source register value. Supporting it cleanly likely requires either:

- falling back to ISD/BE resolution for register-form ctxtsw, or
- adding a new operand-forwarding/prediction protocol that is not justified for
  the first version.

Immediate-form ctxtsw should remain the first fast path because existing tests
exercise it and the target thread id is available directly from the instruction.

## Root-Cause Workflow for Hangs

When a test hangs:

1. Reproduce with the smallest failing test, preferably a gap test.
2. Generate VCD/FST for the first failing transition.
3. Run `/tmp/analyze_postfix.py` or a derived script.
4. Compare against the nearest passing gap test.
5. Identify the first divergent sequential state:
   - pending token state,
   - FE accept state,
   - director state,
   - current thread id,
   - FE queue roll/read pointer,
   - context NPC save/restore,
   - commit packet fields.
6. Make one surgical RTL change.
7. Re-run the same failing focused test.
8. Only then broaden to the full benchmark suite.

## Branch/Commit Plan

Suggested checkpoints:

1. `ctxtsw-isd-repair`
   - current ISD forwarding repaired and characterized.
2. `ctxtsw-isd-verified`
   - known-good ISD forwarding,
   - all current tests passing or documented,
   - one-off or round-trip latency waveform-explained.
3. `ctxtsw-isd-latency-explained`
   - measured endpoint explicitly named,
   - 3-cycle best-case checklist filled out,
   - decision recorded: stop at ISD, tune dense throughput, or consider IF2.
4. `ctxtsw-isd-dense-eval`
   - gap tests and dense microbench characterized,
   - steady-state throughput requirements documented,
   - dense 3-cycle feasibility accepted or deferred.
5. `ctxtsw-if2-parser`
   - IF2 immediate parser only,
   - no functional redirect.
6. `ctxtsw-if2-packet-boundary`
   - FE packet ends at ctxtsw like a branch,
   - no redirect yet.
7. `ctxtsw-if2-redirect`
   - FE target redirect from IF2,
   - commit remains authoritative.
8. `ctxtsw-if2-safe-dispatch`
   - target BE dispatch held/released safely if needed.

Do not combine parser, redirect, BE ownership, and cleanup changes in one
commit.

## Open Design Questions

- What is the exact measured endpoint for the one-off/round-trip result:
  target fetch, target FE queue, target ISD, target retirement, or added dispatch
  slots?
- Can ISD forwarding launch target fetch in the same cycle as ctxtsw detection,
  or is there an unavoidable one-cycle prepare step?
- If ISD forwarding measures 4 or 5 cycles, which 3-cycle best-case condition is
  false?
- In the healthy ISD branch, is sideband FE redirect launched from dispatch,
  reservation, or another named point?
- Does the director still need commit-time `poison_isd_o` for correctness after
  early FE accept, or can that be split into architectural finalization and FE
  control cleanup?
- Can target BE dispatch naturally arrive only after ctxtsw commit in the ISD
  and IF2 immediate paths, or do we definitely need a hold?
- Does the scheduler regfile read path use the correct thread for dense early
  target dispatch, or must it be changed to use per-entry thread identity?
- Can steady-state back-to-back ctxtsw throughput approach 3 cycles without broad
  BE ownership refactoring?
- What is the exact gap13/gap14 sequential difference in the current healthy
  branch?
- Which tests should become mandatory pre-commit gates versus occasional
  waveform/debug checks?
