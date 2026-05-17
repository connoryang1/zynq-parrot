# Early `ctxtsw` Handoff Contract

## Purpose

This note defines the minimum correctness contract for moving `ctxtsw` earlier
than commit in the restored baseline at submodule commit `8dddc514`.

The main lesson from the failed early-launch experiments is:

> `target ready` is not enough.

Early handoff must satisfy an explicit ownership contract across:

- BE detection and old-thread save/finalization
- director FE-command launch timing
- FE controller state
- BE/FE thread-id ownership
- rollback on later redirects or non-`ctxtsw` `npc_w_v`

## Baseline Timing

On the true baseline, one switch looks like:

```text
cycle -3   dispatch_pkt.ctxtsw_v
cycle -2   pending_ctxtsw_v_r
cycle -1   pending_ctxtsw_v_r
cycle  0   fe_cmd_v_li / fe_cmd_yumi_i
cycle  1   current_thread_id_lo / thread_id_r
cycle  2   if2_pc_o under new thread
cycle  4   next thread's dispatch_pkt.ctxtsw_v
```

This implies:

- about 3 cycles before FE handoff
- about 2 cycles from FE handoff to visible new-thread fetch
- about 2 more cycles before the resumed thread's own next `ctxtsw` is classified

The main optimization target is still:

- `dispatch_pkt.ctxtsw_v -> fe_cmd_v_li`

## What The Code Says Today

### 1. Commit-time FE launch is coupled to commit-time architectural finalization

In `bp_be_director.sv`, committed `ctxtsw` drives:

- `npc_w_v`
- FE `e_op_context_switch`
- poison / fence sequencing
- transition into `e_cmd_fence`

In `bp_be_top.sv`, committed `ctxtsw` drives:

- `current_thread_id_lo <= pending_ctxtsw_thread_id_r`
- old-thread resume-state save into `context_*_r`
- cleanup of `pending_ctxtsw_v_r`

So the current design has a single architectural authority:

- `commit_pkt.ctxtsw`

### 2. FE command acceptance is state-dependent

In `bp_fe_controller.sv`:

- `e_reset` drains non-reset commands
- `e_wait` only consumes attaboys
- `e_resume` consumes commands through the resume path
- `e_run` is the normal redirect/immediate command path

So an early `e_op_context_switch` is only meaningful if FE is in the right
state. A valid FE command packet is not, by itself, proof that FE can honor the
handoff as intended.

### 3. `pending_ctxtsw_sent_r` is not a safety mechanism on the baseline

At `8dddc514`, `pending_ctxtsw_sent_r` is:

- reset to `0`
- cleared on `commit_pkt.ctxtsw | commit_pkt.npc_w_v`
- cleared again on `dispatch_pkt.ctxtsw_v`

It is not set anywhere on the baseline path. So it is not currently enforcing
"launch exactly once" or "this early launch belongs to one specific switch".

## Contract For A Correct Early Handoff

An early handoff is allowed only when all of the following are true.

### A. Event identity is explicit

The launch must correspond to one specific classified switch event.

Required:

- a one-shot launch token created from the current `dispatch_pkt.ctxtsw_v`
- the token must be invalidated by:
  - flush / squash
  - a later architectural redirect that beats the switch
  - completion of the handoff

Not sufficient:

- sticky `pending_ctxtsw_v_r`
- raw `retire_ctxtsw_v`

### B. FE is launch-capable

The handoff may only issue when FE is in a state that can honor a ctxtsw
redirect as an immediate redirect-like operation.

Minimum required condition:

- FE is in `e_run`

This can be observed indirectly through an explicit readiness handshake or a
new FE-visible `ctxtsw_ready` signal. The BE should not guess from local state.

### C. Old-thread save point is defined

If FE/BE ownership moves before commit, the design must still know exactly:

- which thread is the old thread
- where old-thread resume state will be saved
- what later event cancels or finalizes that handoff

That implies:

- old-thread id must be latched in one place
- context save must remain tied to one authority
- later non-`ctxtsw` `npc_w_v` must not silently corrupt ownership bookkeeping

### D. BE thread-id authority is singular

`current_thread_id_lo` cannot have multiple ambiguous writers.

If BE ownership moves early, then:

- early handoff must become the one authority for the speculative thread id
- commit / rollback must finalize or restore from that one authority

If BE ownership stays at commit, then:

- FE must be explicitly allowed to speculate independently
- rollback path must be explicit

Mixing both without a contract is what made prior experiments unstable.

### E. Rollback is explicit

Early handoff must define what happens if a later event beats the switch.

Required rollback cases:

- older exception / interrupt wins
- later `commit_pkt.npc_w_v & ~commit_pkt.ctxtsw` wins
- classified switch is squashed before architectural finalization

The existing baseline already uses `commit_pkt.npc_w_v & ~commit_pkt.ctxtsw &
pending_ctxtsw_v_r` to restore `current_thread_id_lo` in one path. Any early
handoff must integrate with that path deliberately rather than incidentally.

## Recommended Next Implementation Shape

Do not try another free-form early-launch experiment.

Instead, add an explicit contract-driven path:

### Step 1. Define a launch token

In `bp_be_top.sv` or `bp_be_director.sv`, add:

- `ctxtsw_launch_pending_r`
- `ctxtsw_launch_cancel_r` or equivalent cancellation condition

Ownership:

- created only by the currently classified `dispatch_pkt.ctxtsw_v`
- consumed once on successful FE launch
- cleared on cancel/finalize

### Step 2. Add FE readiness feedback

Expose a minimal FE readiness signal back to BE, ideally something equivalent
to:

- `fe_ctxtsw_ready`

Definition:

- FE is in `e_run`
- FE can accept an immediate redirect-like command this cycle

Without this, BE is still guessing about FE state.

### Step 3. Separate speculative BE ownership from architectural finalization

Add explicit naming for:

- `ctxtsw_spec_thread_id_r`
- `ctxtsw_old_thread_id_r`
- `ctxtsw_finalized_r`

This prevents `current_thread_id_lo`, pending state, and context save from
implicitly serving multiple roles.

### Step 4. Launch only on:

```text
ctxtsw_launch_pending
& target_ready
& fe_ctxtsw_ready
& no_beating_redirect
& command_queue_can_accept
```

Not on:

- sticky pending state alone
- commit-adjacent pulse alone
- BE `is_run` alone

## File-by-File Plan

### `bp_fe/src/v/bp_fe_controller.sv`

Add a minimal exported readiness signal for ctxtsw early handoff:

- `ctxtsw_ready_o`

Initial definition:

- `state_r == e_run`

Keep it simple first.

### `bp_be/src/v/bp_be_top.sv`

Add explicit speculative handoff bookkeeping:

- launch token
- old-thread id
- speculative target-thread id if needed
- clear finalization / rollback paths

Keep existing `pending_ctxtsw_*` bundle for target state.

### `bp_be/src/v/bp_be_checker/bp_be_director.sv`

Use the explicit contract:

- `ctxtsw_detected_v`
- `ctxtsw_target_ready_v`
- `ctxtsw_fe_ready_v`
- `ctxtsw_launch_allowed_v`
- `ctxtsw_launch_v`
- `ctxtsw_finalize_v`
- `ctxtsw_cancel_v`

Launch FE only from `ctxtsw_launch_v`.

### Optional later: `bp_fe/src/v/bp_fe_pc_gen.sv`

Only touch this if FE state readiness is not enough and a more direct
thread-id/redirect ownership split is needed.

## Practical Success Criteria

The next attempt is successful only if all of these are true:

1. startup / NBF load still completes
2. `mt_ctxtsw_microbench` still passes
3. waveform shows `dispatch_pkt.ctxtsw_v -> fe_cmd_v_li` shrinks
4. FE handoff still lands in the same `1 cycle` thread-id rebind and `1 cycle`
   fetch behavior

If the next attempt cannot satisfy those conditions, revert it and keep
`8dddc514` as the checkpoint.
