# `ctxtsw` Failure / Regression Log

This log records the context-switch optimization attempts that failed, stalled,
or regressed relative to the verified commit-time baseline.

## Known-Good Baseline

The stable baseline is the commit-time `ctxtsw` implementation:

- `import/black-parrot` known checkpoint: `631a5ed8 restore commit-time ctxtsw baseline`
- later verified checkpoint on current sideband branch: `f3b8325b tag issue queue entries with thread id`
- target test:
  `make -C cosim/black-parrot-minimal-example/verilator run PROG=mt_ctxtsw_microbench`
- clean verified result:
  - cold round-trip: `0xe`
  - warm round-trip: `0xe`
  - warm min single-switch estimate: `0x7`
  - `BSG PASS`

Baseline architectural property:

- `commit_pkt.ctxtsw` is the single authority for the switch.
- BE architectural ownership update, old-thread context save, FE redirect,
  poison/fence sequencing, and pending-state cleanup are all coupled to the
  normal commit-time path.

Baseline observed timing:

```text
cycle -3   dispatch_pkt.ctxtsw_v
cycle -2   pending_ctxtsw_v_r
cycle -1   pending_ctxtsw_v_r
cycle  0   fe_cmd_v_li / fe_cmd_yumi_i
cycle  1   current_thread_id_lo / thread_id_r
cycle  2   if2_pc_o under new thread
cycle  4   next thread's dispatch_pkt.ctxtsw_v
```

Working breakdown:

- `dispatch_pkt.ctxtsw_v -> fe_cmd_v_li`: about 3 cycles
- `fe_cmd_v_li -> thread-id rebind`: about 1 cycle
- `thread-id rebind -> visible fetch`: about 1 cycle

The main optimization target remains the first segment:
`dispatch_pkt.ctxtsw_v -> fe_cmd_v_li`.

## Repeated Failure Signature

The most common failed early-launch signature is:

```text
BSG-INFO:    ps.cpp: beginning nbf load
```

followed by no benchmark banner or pass/fail output.

This is important because the failure appears during host/NBF startup, before
the microbenchmark reaches its normal printing path. It means the fast-path
change is disturbing startup/control sequencing, not merely changing the
steady-state measured cycle count.

## Root Lesson So Far

The durable conclusion is:

```text
target ready is not enough
```

Moving FE earlier than commit needs an explicit ownership contract. The
successful commit-time baseline has one authority: `commit_pkt.ctxtsw`.
Most failed experiments split that authority so that some subset of FE, BE,
thread-id state, saved context, issue queue state, poison/clear/suppress, and
pending bookkeeping could move independently.

That creates ambiguous states such as:

- FE has redirected to the target thread but BE still considers the old thread
  architectural.
- BE `current_thread_id_lo` has changed early but old-thread instructions or
  queue entries still exist under baseline assumptions.
- `pending_ctxtsw_sent_r` suppresses the later FE command but commit-time BE
  finalization still partially fires.
- startup freeze/unfreeze or NBF-load control boundaries clear one side of the
  speculative switch state but not the other.
- a target-thread redirect lands without the normal director poison/fence
  sequencing that the shared FE/BE pipeline expects.

The next working design likely needs a real three-phase protocol:

1. detect one specific `ctxtsw`
2. launch exactly once if FE/BE are eligible
3. finalize or cancel explicitly

## Failure / Regression Records

### 0. Commit-Accept Target Packet Repair

Intent:

- Keep early FE sideband forwarding from wasting the target FE packet at
  `commit_pkt.ctxtsw`.
- Preserve backend architectural finalization at commit.
- Avoid reusing the broader packet-thread-tag experiment until FE metadata is
  made target-thread accurate.

Working fix:

- `bp_be_scheduler.sv` accepts a target FE packet on the ctxtsw commit cleanup
  cycle when `pending_ctxtsw_sent_i` is already high.
- `bp_be_issue_queue.sv` supports same-cycle clear plus enqueue for that target
  packet.
- `bp_be_top.sv` presents the pending target thread ID to the scheduler only on
  that commit-accept cycle, so the same-cycle preissue reads the target
  regfile.

Important failed intermediate:

- Accepting the packet without the effective scheduler thread ID made
  `mt_ctxtsw_partial_unroll_benchmark` run into the terminal loop instead of
  completing all switches.
- A broad attempt to use FE packet thread tags for regfile reads/dispatch also
  failed because sideband target FE packets still carried old-thread metadata.

Verified result:

- `mt_ctxtsw_microbench_gap8`: PASS, warm min estimate `0x5`
- `mt_ctxtsw_partial_unroll_benchmark`: PASS, `0x5` cycles/switch
- `mt_regfile_test`: PASS
- `mt_ctxtsw_smoke_test`: PASS
- `mt_ctxtsw_microbench`: PASS, but still slow: `0x6b` warm round-trip,
  `0x35` estimate
- `mt_csr_isolation_test`: PASS
- `mt_frf_isolation_test`: PASS

Remaining issue:

- The original dense microbench is still much slower than the favorable
  gap/unrolled cases. That should be treated as a performance diagnosis item,
  not as the same correctness failure as the earlier hangs.

### 1. Dispatch-Time Prepared Bundle Experiments

Relevant commits in `import/black-parrot` history:

- `35053354 classify ctxtsw in BE dispatch path`
- `67255916 add explicit ctxtsw target context read bundle`
- `bd2a9268 thread ctxtsw target bundle into director`
- `9164329a latch pending ctxtsw target bundle`
- `04f1b954 use prepared ctxtsw bundle for FE handoff`
- `7f6682ae plumb pending ctxtsw valid into director`
- `9a7c3368 launch ctxtsw FE handoff from pending bundle`
- `467a6ef8 speculatively rebind BE thread on ctxtsw launch`

Intent:

- Recognize `ctxtsw` before commit.
- Read/latch target restart state early.
- Launch FE from the pending/prepared target bundle rather than waiting for
  commit.
- In some variants, rebind BE thread ownership speculatively.

Observed result:

- Startup regressed and/or stalled around `ps.cpp: beginning nbf load`.
- The line of investigation was reverted back to the commit-time baseline at
  `631a5ed8 restore commit-time ctxtsw baseline`.

Likely failure class:

- `pending_ctxtsw_v_r` or prepared target state was treated as launch authority,
  but it was not a one-shot token tied to one specific surviving `ctxtsw`.
- FE launch and BE architectural finalization were not governed by a single
  explicit finalization/cancel contract.
- Startup boundaries such as reset/freeze/resume/NBF-load could leave stale or
  partially valid speculative switch state.

### 2. Sticky Pending / `pending_ctxtsw_sent_r` Variants

Intent:

- Use `pending_ctxtsw_sent_r` to avoid double-sending the normal commit-time FE
  command after an early launch.
- Preserve the normal commit path while trying to mark the early launch as
  already sent.

Observed result:

- Stalls or startup regressions.

Likely failure class:

- On the stable baseline, `pending_ctxtsw_sent_r` is not a full safety protocol.
  It is not enough to say "FE command was sent"; the design also needs to know:
  - which `ctxtsw` token was sent
  - whether BE ownership is speculative or architectural
  - whether commit should still save old-thread context
  - whether a later redirect cancels the early launch
- Suppressing the later FE command can remove the visible redirect while still
  leaving commit-time BE side effects or poison/fence behavior ambiguous.

### 3. FE Sideband Receive Path, Inactive

Relevant commits:

- `ea83faa8 add inactive ctxtsw sideband scaffolding`
- `12997887 add fe ctxtsw sideband receive path`

Intent:

- Add a dedicated FE sideband path carrying:
  - target NPC
  - target thread id
  - privilege
  - translation enable
  - ASID
- Keep the path inactive initially.

Observed result:

- With sideband inactive, baseline remained good.

Conclusion:

- The sideband receive plumbing itself is not the immediate bug.
- The instability appears when the sideband is allowed to redirect FE earlier
  than the normal commit-time ownership transition.

### 4. Sideband-Only / Hint-Only Launch

Intent:

- Send an early FE sideband redirect as a hint.
- Keep the normal commit-time switch authoritative.

Observed result:

- Stalled.

Likely failure class:

- Even if BE commit remains authoritative, FE has already moved to target-thread
  fetch state.
- The shared pipeline then observes a mixed world: FE is target-thread oriented,
  while BE/current-thread/issue/commit machinery can still be old-thread
  oriented.
- The baseline has no explicit rollback/cancel path for an FE-only speculative
  thread redirect.

### 5. Sideband Interlock Variant

Intent:

- Send sideband once.
- Mark the pending switch as sent.
- Suppress issue while the switch is sent-but-uncommitted.

Observed result:

- Got further than simpler sideband-only forms but still stalled.

Likely failure class:

- Suppressing issue was not sufficient to model all in-flight state.
- The design still lacked an explicit token lifecycle and a precise definition
  of when BE thread ownership became speculative versus architectural.

### 6. Fast Event Exposure

Relevant commits:

- `9826a3dd tag writebacks with issuing thread`
- `f06556b3 expose fast ctxtsw event`
- `300543db fix fast ctxtsw resume npc`
- `f3b8325b tag issue queue entries with thread id`

Intent:

- Expose a calculator-level fast `ctxtsw` event:
  - old thread id
  - target thread id
  - resume NPC
- Correct the old-thread resume NPC to use the post-`ctxtsw` PC.
- Tag issue queue entries with thread id so in-flight work can retain its
  issuing-thread identity.

Observed result:

- These changes are currently retained and baseline still passes at `0xe`
  round trip.

Conclusion:

- Fast event detection and metadata exposure are not enough by themselves, but
  they are useful scaffolding.
- The missing piece remains the ownership/finalization protocol around using the
  event to redirect FE and/or rebind BE early.

### 7. Latched Fast Mini-Commit Through Sideband

Date/session:

- 2026-05-04 session
- not committed
- reverted immediately after test

Intent:

- Latch the calculator fast event into a pending sideband request.
- Drive FE sideband redirect from the latched request.
- Update BE state only when FE acknowledges the sideband via `fe_ctxtsw_yumi_i`.
- Save old-thread resume context at that same accepted mini-commit point.
- Set `pending_ctxtsw_sent_r` to suppress later double-sending.

Observed result:

- Build/elaboration succeeded.
- Microbenchmark completed with `BSG PASS`, but timing regressed:
  - cold round-trip: `0x10`
  - warm round-trip 0: `0x10`
  - warm round-trip 1: bogus huge value `0x6cac29c9c92de658`
  - warm min round-trip: `0x10`
  - warm min single-switch estimate: `0x8`

Reason for revert:

- It was not a known-good optimization.
- It slowed the switch by about one cycle each direction.
- The bogus warm sample suggested state/timing corruption even though the test
  eventually passed.

Likely failure class:

- Latching the sideband request added a cycle, eliminating the hoped-for timing
  benefit.
- The same ambiguous finalization problem remained: the accepted mini-commit
  had to coexist with later commit-time cleanup and poison/fence assumptions.

### 8. Pulsed Same-Cycle Fast Mini-Commit Through Sideband

Date/session:

- 2026-05-04 session
- not committed
- reverted immediately after stall

Intent:

- Avoid the extra latch cycle from the previous attempt.
- Drive FE sideband directly from the calculator fast event when FE was ready.
- Update BE state only if FE accepted in the same cycle.
- Fall back to the normal commit-time path if FE did not accept.

Observed result:

- Build/elaboration succeeded.
- Runtime reached:

```text
BSG-INFO:    ps.cpp: beginning nbf load
```

- Then made no progress for multiple wait intervals.
- The Verilator process was killed.
- The change was reverted.
- Baseline rerun after revert restored:
  - cold round-trip: `0xe`
  - warm round-trip: `0xe`
  - warm min single-switch estimate: `0x7`
  - `BSG PASS`

Likely failure class:

- Direct same-cycle FE sideband launch still bypassed or conflicted with the
  normal director-controlled redirect/poison/fence path.
- FE/BE ownership could still split because the calculator fast event is not a
  complete architectural token lifecycle.
- `fe_ctxtsw_ready_i`/`fe_ctxtsw_yumi_i` only prove FE-side acceptance of that
  sideband transaction; they do not prove the BE and shared pipeline are in a
  globally safe ownership state.

### 9. Clean-Build / Waveform Infrastructure Failures

These were not `ctxtsw` microarchitectural failures, but they affected
debugging quality.

Observed issues:

- `make view` expected `dump.fst`, while the working traced flow used
  `trace.fst`.
- Running `make clean run` exposed missing/stale build assumptions:
  - `No rule to make target 'obj_dir/Vbsg_nonsynth_zynq_testbench'`
  - `No rule to make target '%/Vbsg_nonsynth_zynq_testbench'`
- One clean-build sanity check hit:

```text
%Error: .../cosim/v/bsg_nonsynth_zynq_testbench.sv:4: Active region did not converge.
```

Resolution status:

- Clean run flow was restored and verified later.
- Useful traced flow:
  - set `TRACE=1`
  - clean/rebuild before waveform-dependent sessions
  - run the benchmark
  - then open the generated trace through the appropriate viewer target/file

Lesson:

- Do not trust stale Verilator objects when validating `ctxtsw` behavior.
- Incremental tests are fine during local iteration, but clean rebuilds are
  required at key checkpoints and before waveform analysis.

### 10. Early BE Handoff + Retire-Thread Commit Mux

Date/session:

- 2026-05-06 session
- not committed
- current working-tree experiment at time of this note

Intent:

- Keep the FE sideband path active:
  - `fe_ctxtsw_v_o = ctxtsw_launch_lo`
  - `pending_ctxtsw_sent_r` set on `fe_ctxtsw_yumi_i`
- Move BE ownership to the target thread as soon as FE accepts the sideband.
- Keep old-thread retirement visible after early BE ownership changes by muxing
  `commit_pkt_o` from `retire_thread_id_i` instead of `current_thread_id_i`.
- Save old-thread context at the early handoff point and avoid double-saving it
  again at commit.
- Suppress only the duplicate commit-time FE context-switch command when the
  sideband was already accepted.
- Preserve commit-time director poison/fence cleanup.

Observed result:

- Static/elaboration/build checks passed:
  - `git diff --check`
  - `make -j24 prep_lite`
  - Verilator model rebuild
- Functional tests passed:
  - `mt_ctxtsw_microbench`: `0x10` round-trip / `0x8` estimate
  - `mt_ctxtsw_unrolled_ring_stress`: `BSG PASS`, `9909` minstret delta
  - `mt_ctxtsw_partial_unroll_benchmark`: `0x9` cycles/switch
- This is correct enough to run the benchmarks, but it is a performance
  regression relative to the known `0x7` partial-unroll baseline and the earlier
  `0x5` sideband-only measurement.

Related failed sub-variant:

- Suppressing commit-time director poison/fence cleanup when
  `pending_ctxtsw_sent_i` was already set caused `mt_ctxtsw_microbench` to stall
  after NBF load.
- Restoring commit-side poison/fence fixed that smoke failure but left the
  measured switch cost at `0x9` cycles/switch on partial-unroll.

Likely failure class:

- Early FE launch by itself can hide some FE redirect latency behind the old
  thread's final retirement.
- Early BE ownership handoff does not appear to buy the same overlap in this
  pipeline. Instead, it forces extra bookkeeping on the retire/commit side:
  - active-thread issue state and retire-thread commit state must be separated
  - old-thread context save must be guarded against a second commit-time save
  - `commit_pkt.ctxtsw` must still drive director poison/fence cleanup for
    correctness
- The result is a mixed early/commit-time design:
  - FE has already accepted the target redirect
  - BE ownership has already moved
  - but the director still has to run the commit-time cleanup/fence boundary
- That combination likely loses the overlap advantage from the simpler
  sideband-only approach while adding one or more cycles of disruption around
  commit/fence/issue restart.

Current conclusion:

- This experiment shows that "early BE handoff" is not automatically the next
  step after early FE sideband.
- The useful `0x5` result should be treated as an FE-prefetch/FE-overlap result,
  not proof that BE architectural ownership can safely move early with the same
  machinery.
- To get below the current baseline without regressions, the design probably
  needs an explicit speculative ownership/drain contract rather than moving
  `current_thread_id_lo` early and then repairing commit visibility afterward.

Follow-up:

- Reverted the dirty experiment back to the early-FE-only shape:
  - sideband active
  - duplicate commit-time FE command suppressed
  - BE ownership remains commit-time
  - old-thread context save remains commit-time
- Fresh rebuilt results in that state:
  - `mt_ctxtsw_partial_unroll_benchmark`: `0x5` cycles/switch
  - `mt_ctxtsw_microbench`: `0x10` round-trip / `0x8` estimate
- This confirms the current question for waveform debug: why does the dense
  steady-state switch stream benefit from early FE sideband while the isolated
  round-trip benchmark does not?

## Invariants A Future Attempt Must Satisfy

A successful early/first-class `ctxtsw` path needs all of the following.

### One Token Per Switch

Each early launch must correspond to one specific classified `ctxtsw` instance.

Not sufficient:

- sticky `pending_ctxtsw_v_r`
- raw calculator fast pulse without lifecycle bookkeeping
- raw commit-time pulse reused as launch authority

### FE Launch Eligibility

FE must be in a state that can honor a redirect-like `ctxtsw` operation.

Minimum:

- FE is in `e_run`
- FE is not draining reset traffic
- FE is not in wait/resume transition
- FE can accept the redirect this cycle or the request is held by a safe token

### Singular Ownership Authority

The design must decide whether early launch changes BE ownership:

- If yes, speculative BE ownership must be explicit and cancellable.
- If no, FE speculation must be explicit and rollbackable.

`current_thread_id_lo` should not silently serve as both speculative and
architectural ownership without separate state.

### Old-Thread Save Point

The old-thread resume PC/state must be saved from exactly one authority.

Open choices:

- keep old-thread save at normal commit until finalization
- introduce an explicit speculative save with cancellation/restore semantics

Do not mix both implicitly.

### Cancel Beats Finalize

Early `ctxtsw` must be canceled by older/control-winning events, including:

- freeze/reset/resume
- older exception/interrupt
- non-`ctxtsw` `npc_w_v`
- squash/flush of the classified switch

### Director / Poison / Fence Semantics

The normal director path does more than emit a PC redirect. It also coordinates:

- `npc_w_v`
- FE command/fence sequencing
- poison/suppress/clear behavior
- shared pipeline recovery

A sideband redirect that bypasses this sequencing must provide equivalent
semantics or prove they are unnecessary for the early path.

## Current Practical Recommendation

Do not continue with free-form "send FE earlier" patches.

The next implementation attempt should be contract-driven:

1. Add explicit switch-token lifecycle state.
2. Add or strengthen FE eligibility feedback.
3. Separate speculative thread identity from architectural `current_thread_id_lo`.
4. Define finalization and cancellation first.
5. Only then let FE redirect before commit.

Success criteria:

- startup/NBF load completes
- `mt_ctxtsw_microbench` passes
- warm round-trip improves below `0xe`
- no bogus samples
- waveform shows the improvement is from shrinking
  `dispatch_pkt.ctxtsw_v -> fe_cmd/ctxtsw_redirect`, not from measurement noise
- clean rebuild verifies the same result

## 2026-05-06 Minimal Smoke Test And Director Split

Added `mt_ctxtsw_smoke_test` as a non-benchmark hang/correctness sentinel:

- thread 0 seeds thread 1 NPC/GP/SP
- thread 0 executes `csrwi 0x081, 1`
- thread 1 stores a flag and executes `csrwi 0x081, 0`
- thread 0 checks the flag and exits

This test caught an important correctness boundary. Suppressing all commit-time
director cleanup when `pending_ctxtsw_sent_i` is set lets thread 0 fall through
past the context-switch CSR, so the old stream is not killed even though FE
accepted the sideband redirect.

Verified safe split:

- keep raw `commit_pkt.ctxtsw` for local director NPC update and `poison_isd_o`
- suppress only duplicate FE/control behavior when sideband already sent:
  - duplicate FE context-switch command
  - `e_run -> e_cmd_fence` caused solely by the already-sent switch
- keep BE ownership and context save at commit
- keep the experimental early-BE fast path scaffold disabled

Results:

- `mt_ctxtsw_smoke_test`: PASS, minstret delta `0xdbb`
- `mt_ctxtsw_partial_unroll_benchmark`: PASS, `0x8` cycles/switch, minstret
  delta `0x4537`

Interpretation:

- The earlier fully suppressed cleanup behavior was not generally correct; it
  can only look good in very constrained benchmark shapes.
- The local poison/NPC cleanup is required to stop old-context fall-through.
- With the correctness cleanup restored, this version improves over the old
  `0x9` cleanup/fence result but does not recover the previous `0x5` result.
- Getting to `0x5` or below for general code likely needs an explicit
  speculative/rollback contract rather than merely suppressing commit cleanup.

## 2026-05-06 FE Metadata Fix And Early-BE Identity Isolation

Found a metadata hole in the sideband FE redirect path:

- `bp_fe_controller.sv` correctly selected `redirect_thread_id_o` from
  `ctxtsw_thread_id_i` on sideband accept.
- The same sideband accept path set `redirect_br_metadata_fwd_o` to zero.
- The BE issue queue derives `preissue_pkt.thread_id` from the high bits of
  `branch_metadata_fwd`, so target-context fetch packets could still look like
  thread 0 to BE-side per-instruction metadata consumers.

Implemented the safe prerequisite fix:

- build sideband redirect branch metadata with `ctxtsw_thread_id_i` in the
  thread-id field and zero in the remaining branch metadata bits.
- keep BE architectural ownership at commit.
- keep scheduler regfile reads and normal dispatch stamped from
  `current_thread_id_i` for now.

Isolation result:

- Changing scheduler regfile reads and normal dispatch to use
  `preissue_pkt.thread_id` compiled, but `mt_ctxtsw_smoke_test` hung after the
  banner.
- Reverting only that scheduler early-BE identity change while keeping the FE
  metadata fix restored the smoke test.

Verified current working state:

- `git -C import/black-parrot diff --check -- ...`: PASS
- `make -C /home/coyang/zynq-parrot-copy/zynq-parrot -j24 prep_lite`: PASS
- `make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_smoke_test`:
  PASS, minstret delta `0xdbb`
- `make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_partial_unroll_benchmark`:
  PASS, `0x8` cycles/switch, minstret delta `0x4537`
- `make -C /home/coyang/zynq-parrot-copy/zynq-parrot/testing run-mt_ctxtsw_microbench`:
  no program output after NBF load during an extended run; stopped manually
  rather than treating it as passing

Interpretation:

- FE sideband metadata must be fixed before any instruction-carried thread-id
  BE work can be trusted.
- Instruction-carried thread id in scheduler is not sufficient by itself and is
  not currently safe. The backend still has global state tied to
  `expected_npc_i`, `current_thread_id_i`, and commit-time finalization.
- The next real early-BE attempt needs explicit speculative BE state and
  side-effect gating rather than simply replacing `current_thread_id_i` with
  FE queue metadata in scheduler.

## 2026-05-06 Microbench Shape Diagnostics

Added diagnostic tests to explain why `mt_ctxtsw_microbench` is harder than the
partial-unroll benchmark:

- `mt_ctxtsw_microbench_trace`
  - same high-level seed/switch sequence as the microbench
  - prints markers before and after every seed/switch phase
  - adds compiler memory barriers on context CSR writes
- `mt_ctxtsw_microbench_barrier`
  - same no-marker shape as the original microbench
  - adds compiler memory barriers on context CSR writes
- `mt_ctxtsw_live_regs_test`
  - directly checks whether selected live GPRs survive a T0->T1->T0 switch
  - covers `a4`, `a5`, and `s0`-`s3`

Observed results:

- `mt_ctxtsw_microbench_trace`: PASS
  - markers show all three seed/switch phases complete
  - measured: cold `0x10`, warm0 `0x10`, warm1 `0x48`
  - minstret delta `0x43a8`
- `mt_ctxtsw_microbench_barrier`: no output after NBF load for several minutes;
  stopped manually
- `mt_ctxtsw_live_regs_test`: PASS
  - selected live GPRs are preserved across one isolated round trip
  - minstret delta `0x18f2`

Disassembly notes:

- The optimized no-marker microbench keeps values live across multiple switches:
  - `a4` holds the `t_ping` target address
  - `a5` holds the virtual-address mask
  - `s0`-`s3` hold measured deltas/minimums for later printing
- The trace version inserts calls between phases. Those calls change scheduling
  and give the machine many extra committed instructions between each
  seed/switch step.

Current interpretation:

- The original microbench difficulty is not explained by a simple compiler
  memory-barrier issue; the barrier-only variant still parks.
- It is also not explained by a simple "live GPRs are not preserved" issue; the
  narrow live-register test passes.
- The likely stressor is the dense, no-call sequence of:
  seed target context -> switch out -> return -> immediately seed next target
  context -> switch again.
- That shape may be exposing an RTL timing/ordering issue in the context CSR
  write path or pending ctxtsw cleanup: the next target context is written very
  soon after returning from the previous switch, while the trace version waits
  long enough for cleanup to settle.

Next useful checks:

- Controlled spacing sweep results:
  - `gap1`: no output after NBF load; stopped manually
  - `gap8`: no output after NBF load; stopped manually
  - `gap12`: no output after NBF load; stopped manually
  - `gap13`: no output after NBF load; stopped manually
  - `gap14`: PASS, cold/warm round trips `0xf`, estimate `0x7`
  - `gap16`: PASS, cold/warm round trips `0xf`, estimate `0x7`
- The pass/fail boundary is therefore between 13 and 14 inserted independent
  `addi x0, x0, 0` instructions for this exact generated code shape.
- Inspect waveform around the first failing no-gap or `gap13` transition and
  compare against passing `gap14`:
  - `commit_pkt.ctxtsw`
  - context CSR write valid/target thread for `0x082` and `0x083`
  - `pending_ctxtsw_v_r` / `pending_ctxtsw_sent_r`
  - `current_thread_id_lo`
  - FE sideband accept

## 2026-05-14 Gap8 Print/Reentry Waveform Diagnosis

Context:

- Current local RTL has early FE sideband disabled in `bp_be_top.sv`.
- Current local scheduler has:
  `fe_queue_roll_li = commit_pkt_cast_i.npc_w_v & ~commit_pkt_cast_i.ctxtsw`.
- `mt_ctxtsw_microbench_gap14` passes with clean `TRACE=1` waveform.
- `mt_ctxtsw_microbench_gap8` reaches the final post-switch print path in the
  waveform but does not produce normal program output.

Source placement:

- The first `bp_print_string` in `mt_ctxtsw_microbench_gap_common.h` happens
  after all three measured switch round trips:
  - seed/switch thread 1
  - gap, seed/switch thread 2
  - gap, seed/switch thread 3
  - compute `warm_min`
  - `restore_gp()`
  - print benchmark banner/results
- Therefore the print is not supposed to happen during the logical context
  switch window. If the first print hangs, it is a symptom of earlier
  architectural/queue state corruption or of a later replay/order bug exposed
  by the post-switch code.

Gap8 waveform signature:

- The final context switches complete and return to thread 0.
- Execution reaches:
  - `0x8000031e`: restore `gp`
  - `0x8000032e`: `jal ra, bp_print_string`
  - `0x80005594`: `bp_print_string`
- Inside `bp_print_string`, the stack spill `sd a0,-24(s0)` reaches the memory
  pipe and an accepted d-cache miss is observed:
  - `dc_req_v=1`
  - `dc_req_yumi=1`
  - `dc_miss=1`
  - `commit_dmiss0=1`
  - `commit_npc_w0=1`
  - `fe_queue_roll_li=1`
- The redirect/recovery then re-presents code around the print loop. Shortly
  after, the reload from `-24(s0)` / dereference path is visible with bad or
  zeroed operands in the trace.

Relevant RTL facts:

- Accepted d-cache miss and replay are different:
  - `cache_miss_v_o = early_v_r & ... & cache_req_yumi_i`
  - `cache_replay_v_o = early_v_r & ... & ~cache_req_yumi_i`
- Store misses are blocking in the writeback configuration; they are not
  nonblocking store-buffer style operations.
- `dcache_miss` is carried as a BP special, `dcache_replay` as a BP exception.
  Both contribute to `commit_pkt.npc_w_v` through raw special/exception bits.
- Issue queue roll semantics:
  - for replay, `instret=0`, so roll returns to the faulting instruction
  - for accepted miss, `instret=1`, so roll advances past the committed miss
    instruction and replays younger work

Current interpretation:

- The print should not be considered part of the context-switch operation.
- The first print is the first code region that forces stack stores/loads after
  the dense gap8 switch sequence, so it is a good place for stale queue state or
  incomplete context-switch cleanup to become observable.
- The current `~commit_pkt_cast_i.ctxtsw` roll suppression is a design fork, not
  a complete correctness protocol. It avoids one stale-old-stream replay mode,
  but it is only safe if old FE/issue queue state is otherwise cleared, drained,
  or tagged so it cannot issue after a context-switch boundary.

Design decision needed:

- Decide what `ctxtsw` should do to the old FE/issue queue:
  - roll old queue to resume-after-ctxtsw, matching ordinary redirect/replay
    semantics
  - hard clear/drain old queue at the context-switch boundary
  - tag queue entries with thread/epoch and suppress mismatches
- Also decide whether `ctxtsw` may commit while memory/long-latency scoreboard
  state is outstanding:
  - if yes, detector/scoreboard state needs thread ownership
  - if no, `ctxtsw` issue/commit needs an ordered/no-outstanding interlock

Immediate recommendation:

- Treat the current one-line scheduler roll suppression as an incomplete
  experiment until the queue-boundary decision is made.
- The next surgical fix should implement an explicit clear/drain or
  thread/epoch-valid rule for entries across `ctxtsw`, then clean-run
  `gap8`, `gap14`, `mt_ctxtsw_microbench`, and the register/isolation tests
  with `TRACE=1`.

## 2026-05-14 Partial-Unroll Throughput Verification

Context:

- Clean traced run:
  `make -C cosim/black-parrot-minimal-example/verilator clean run PROG=mt_ctxtsw_partial_unroll_benchmark TRACE=1 DUMP_FILE=partial_verify.fst`
- Result:
  - `Cycles per switch: 0x0000000000000004`
  - `BSG PASS`
- The generated benchmark has four consecutive immediate context switches per
  ring body, for example:
  - `0x800004aa: csrwi 0x081,2`
  - `0x800004ae: csrwi 0x081,2`
  - `0x800004b2: csrwi 0x081,2`
  - `0x800004b6: csrwi 0x081,2`

Waveform signature:

- A representative first switch around cycle `295047` shows:
  - cycle `295047`: `dispatch_ctxtsw=1`, `issue_ctxtsw=1`
  - cycle `295048`: `fast_ctxtsw=1`
  - cycle `295049`: `pending_v=1`, `launch=1`
  - cycle `295050`: `commit_ctxtsw=1`, `switch_commit=1`,
    `fe_cmd_v=1`, `redirect_npc=0x800004a6`
  - cycle `295051`: `current_thread_id_lo` changes to `1`
  - cycle `295052`: target PC is visible in IF2 / FE queue path
  - cycle `295055`: next target-thread ctxtsw reaches ISD
- Later steady-state windows show the same overlap pattern and the measured
  average remains `0x4`.

Interpretation:

- The `0x4` partial-unroll result is real for this benchmark and this RTL; it is
  not a stale-build or print/reporting artifact.
- It is a steady-state throughput measurement across back-to-back `ctxtsw`
  instructions, not a proof of isolated arbitrary-instruction latency.
- It also does not prove the queue boundary is safe. The current gap8 print
  failure still points at stale/ambiguous queue state or replay recovery after
  dense switches.

Design direction recorded:

- Prefer thread tagging for the queue/ownership boundary.
- Do not keep layering special cases onto the untagged `fe_queue_roll_li`
  suppression path as the final correctness mechanism.

## 2026-05-16 Gap8 Sideband / I-cache Abort Finding

Context:

- Re-enabled FE sideband handoff and kept BE ownership/finalization commit-time.
- Clean traced run after fixing NBF explicit zero preservation:
  `make -C cosim/black-parrot-minimal-example/verilator clean run PROG=mt_ctxtsw_microbench_gap8 TRACE=1 DUMP_FILE=gap8_fe_only_sideband.fst`
- The first two sideband context switches completed:
  - first `sideband_v/yumi` accepted target `0x8000048e`
  - commit-time `commit_pkt.ctxtsw` still fired and switched BE ownership
  - second sideband returned to T0 at `0x8000027c`
- The later failure was not a missing commit token. FE delivered corrupt
  instruction words for T0 resume PCs such as `0x80000288`, even though the
  program image contains nops there.

Root cause found:

- During the first switch, T0 had an I-cache miss for the resume-after-ctxtsw
  line. The critical word arrived, then sideband forced a redirect before the
  full line completed.
- The existing abort experiment tried to invalidate the aborted line, but the
  abort invalidation used the current forced target index instead of the
  partially-filled old line index. Waveform before the fix:
  - critical fill for old T0 line at tag index `0x0a`
  - sideband redirect/abort cycle drove `ic_tag_addr=0x12`
  - later T0 resume hit the old line and read mixed correct/stale data
- Fix direction:
  - latch miss paddr/way on `cache_req_yumi_i`
  - use the latched miss paddr/way for abort invalidation
  - give the abort tag write priority over the forced redirect tag read

Current result:

- Clean traced run:
  `make -C cosim/black-parrot-minimal-example/verilator clean run PROG=mt_ctxtsw_microbench_gap8 TRACE=1 DUMP_FILE=gap8_icache_abort_priority.fst`
- PASS:
  - cold round-trip `0x6b`
  - warm round-trip 0 `0x32`
  - warm round-trip 1 `0x0c`
  - warm min single-switch estimate `0x6`
  - `BSG PASS`
- Waveform check confirms the abort now targets the old line:
  - critical fill at tag index `0x0a`
  - abort cycle also drives `ic_tag_addr=0x0a`
  - returning to T0 at `0x8000027c` no longer reuses the stale partially-filled
    line; the next access misses/refills instead of consuming corrupt data.

Open items:

- This is a correctness improvement, not a final performance result. The cold
  and first warm gap8 numbers are still inflated by I-cache refill/abort tails.
- Need rerun a broader matrix before committing: `gap1/gap4/gap8/gap14`,
  `mt_ctxtsw_microbench`, partial-unroll, smoke, and register/isolation tests.
- The sideband/queue-boundary design is still experimental; thread/epoch tagging
  remains the preferred final direction.

## 2026-05-16 Broader Clean TRACE=1 Regression Matrix

Context:

- Current RTL keeps FE sideband active and BE ownership/finalization
  commit-time.
- Current I-cache abort fix is active:
  - latch the missed line paddr/way on accepted miss
  - invalidate the aborted old line using the latched paddr/way
  - give the abort tag write priority over the forced redirect tag read
- Current NBF flow preserves explicit zero writes while still skipping absent
  zeros.
- All runs below used `make clean run ... TRACE=1` with unique dump names.

Static checks:

- `git -C import/black-parrot diff --check -- bp_fe/src/v/bp_fe_icache.sv bp_be/src/v/bp_be_top.sv bp_be/src/v/bp_be_checker/bp_be_director.sv bp_be/src/v/bp_be_checker/bp_be_scheduler.sv bp_common/software/py/nbf.py`: PASS
- `git diff --check -- CTXTSW_FAILURE_LOG.md tools/ctxtsw_timeline.py cosim/black-parrot-minimal-example/Makefile.collateral`: PASS

Gap matrix:

- `mt_ctxtsw_microbench_gap1`: PASS
  - cold `0x6b`
  - warm0 `0x6c`
  - warm1 `0x6c`
  - warm min estimate `0x36`
  - minstret delta `0x3aaf`
- `mt_ctxtsw_microbench_gap4`: PASS
  - cold `0xa3`
  - warm0 `0x68`
  - warm1 `0x9f`
  - warm min estimate `0x34`
  - minstret delta `0x3ab5`
- `mt_ctxtsw_microbench_gap8`: PASS
  - cold `0x6b`
  - warm0 `0x32`
  - warm1 `0x0c`
  - warm min estimate `0x6`
  - minstret delta `0x3abe`
- `mt_ctxtsw_microbench_gap14`: PASS
  - cold `0x6b`
  - warm0 `0x0c`
  - warm1 `0x72`
  - warm min estimate `0x6`
  - minstret delta `0x3acc`

Core context-switch benchmarks:

- `mt_ctxtsw_microbench`: PASS
  - cold `0x6b`
  - warm0 `0x6c`
  - warm1 `0x6f`
  - warm min estimate `0x36`
  - minstret delta `0x4843`
- `mt_ctxtsw_partial_unroll_benchmark`: PASS
  - cycles/switch `0x6`
  - total cycles `0x19db`
  - contexts `4`
  - switches/context `0x100`
  - unroll factor `4`
  - minstret delta `0x3f22`

Smoke and isolation regressions:

- `mt_ctxtsw_smoke_test`: PASS, minstret delta `0xdbb`
- `mt_regfile_test`: PASS, minstret delta `0x4609`
- `mt_csr_isolation_test`: PASS, minstret delta `0x3751`
- `mt_frf_isolation_test`: PASS, minstret delta `0x34c1`

Interpretation:

- The I-cache abort fix appears to close the previous gap1/gap4/gap8 hang class:
  the small-gap programs now complete instead of stalling after NBF load or
  corrupting the post-switch print path.
- Performance remains strongly dependent on code shape and I-cache refill/abort
  tails:
  - gap1 and the original microbench still measure about `0x36` per one-way
    switch.
  - gap8/gap14 can still expose the better `0x6` one-way estimate once the
    refill/abort tail is avoided or amortized.
  - partial-unroll is now `0x6` cycles/switch in this state, slower than the
    earlier `0x4` observed before the current correctness hardening.
- Current state is therefore a correctness improvement with unresolved
  performance regression/shape sensitivity. The next useful waveform check is
  to compare the original microbench or gap1 against gap8 warm1 and identify
  how many cycles are caused by I-cache abort/refill versus FE/BE redirect
  sequencing after `commit_pkt.ctxtsw`.

## 2026-05-16 ISD Forwarding Timing Experiments

Added `tools/ctxtsw_delta_scan.py` to extract context-switch timing deltas from
VCD waveforms. It tracks, per ctxtsw dispatch:

- scheduler dispatch of the ctxtsw
- calculator `fast_ctxtsw_v_o`
- FE sideband accept
- target PC arrival in IF1/IF2
- first accepted FE queue packet / next ctxtsw dispatch
- commit-time ctxtsw cleanup

Baseline/current checkpoint before new experiments:

- `mt_ctxtsw_microbench_gap8`: PASS
  - cold `0x6b`, warm0 `0x32`, warm1 `0x0c`, estimate `0x6`
  - waveform: sideband accept at dispatch `+2`, target IF2 at `+4`
  - useful target FE queue / next dense ctxtsw generally appears at `+5/+6`
- `mt_ctxtsw_partial_unroll_benchmark`: PASS
  - cycles/switch `0x6`
  - same dense waveform shape: sideband `+2`, target IF2 `+4`, useful target
    queue/dispatch `+5/+6`

Experiment A: launch FE sideband directly from calculator `fast_ctxtsw_v_o`
instead of waiting for the pending token register.

- Change:
  - `fe_ctxtsw_v_o = fast_ctxtsw_launch_v_li | ctxtsw_launch_lo`
  - sideband payload muxes between the calculator fast ctxtsw bundle and the
    pending token bundle.
- Results:
  - `mt_ctxtsw_microbench_gap8`: PASS, estimate still `0x6`
  - `mt_ctxtsw_partial_unroll_benchmark`: PASS, cycles/switch still `0x6`
- Waveform effect:
  - sideband accept moved from dispatch `+2` to `+1`
  - target IF2 moved from `+4` to `+3`
  - useful FE queue/next ctxtsw did not improve because the earlier target IF2
    now collides with commit-time `commit_pkt.ctxtsw` cleanup:
    `fe_queue_clr_li`, `ctxtsw_queue_hold_li`, and calculator `pipe_flush_v`
    are high at the commit cycle.
- Interpretation:
  - The one-cycle FE redirect improvement is real internally.
  - Benchmark-visible improvement is absorbed by commit-time scheduler/queue
    cleanup.

Experiment B: create/capture/launch the pending ctxtsw token directly from
`dispatch_pkt.ctxtsw_v` in `bp_be_top.sv`, using the dispatch-stage target
bundle.

- Result:
  - `mt_ctxtsw_microbench_gap8`: PASS, but regressed:
    - cold `0x10`, warm0 `0x32`, warm1 `0x10`, estimate `0x8`
- Waveform effect:
  - sideband accept moved to dispatch `+0`
  - target IF2 can appear at `+2`
  - first redirect after the cold transition drove a bad transient target
    (`0x0`) before later recovery/cleanup corrected progress.
- Interpretation:
  - Dispatch-cycle sideband launch is not a safe surgical change in this
    structure. It creates a same-cycle combinational path through scheduler
    dispatch classification, top-level context target muxing, FE redirect, and
    frontend state.
  - This is likely why the measured estimate regressed despite earlier IF1/IF2
    timing.
- Action:
  - Reverted Experiment B.
  - Do not retry zero-cycle ISD launch without first breaking the target bundle
    out of the same-cycle redirect loop or adding a separate predecoded/latched
    target source.

Current bottleneck after Experiment A:

- `bp_be_scheduler.sv` holds FE queue ready low from ctxtsw dispatch until
  commit:
  - `ctxtsw_issue_hold_r`
  - `ctxtsw_queue_hold_li`
  - `fe_queue_ready_and_o = issue_queue_ready_and_lo & ~ctxtsw_queue_hold_li`
- At commit, the queue is also cleared:
  - `fe_queue_clr_li = clear_iss_i | commit_pkt_cast_i.ctxtsw`
- Therefore the next optimization target is not sideband accept timing alone.
  It is the safe treatment of target-context FE queue packets across
  commit-time ctxtsw cleanup.
