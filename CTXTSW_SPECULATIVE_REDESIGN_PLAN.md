# CTXTSW Speculative Redesign Plan

Starting point:
- `import/black-parrot` commit `7bc1076b`
- verified baseline:
  - `make -j24 prep_lite`
  - `make -C cosim/black-parrot-minimal-example/verilator run PROG=mt_ctxtsw_microbench`
  - warm round-trip `14`
  - single-switch estimate `7`

## Problem Statement

The measured baseline still breaks down as:

- `ctxtsw_v -> fe_cmd_v_li`: about 3 cycles
- `fe_cmd_v_li -> thread-id rebind`: about 1 cycle
- `thread-id rebind -> visible fetch`: about 1 cycle

Earlier attempts to move FE launch earlier than commit all regressed startup and stalled around:

- `ps.cpp: beginning nbf load`

So the missing piece is not target-state preparation and not FE readiness alone. The missing piece is an explicit speculative ctxtsw ownership contract across:

- BE ctxtsw detection
- FE launch eligibility
- startup freeze/unfreeze
- old-thread save/finalization
- rollback/cancel on later redirects

## Design Goal

Turn ctxtsw into a first-class speculative handoff primitive with three explicit phases:

1. `detect`
2. `launch`
3. `finalize` or `cancel`

The key change is that `launch` must become an explicit speculative protocol, not an inferred side effect of sticky prepared-state bits.

## Proposed State Model

Introduce one speculative ctxtsw FSM in BE:

- `e_ctxtsw_idle`
- `e_ctxtsw_prepared`
- `e_ctxtsw_launched`
- `e_ctxtsw_finalized`
- `e_ctxtsw_canceled`

Only `idle`, `prepared`, and `launched` need to persist as real state. `finalized` and `canceled` can collapse back to `idle` if preferred.

### Meaning of each state

- `idle`
  - no speculative ctxtsw in flight

- `prepared`
  - one specific ctxtsw has been detected
  - target bundle is captured
  - launch has not happened yet

- `launched`
  - FE has been launched speculatively for this ctxtsw
  - BE may or may not also have speculative ownership depending on the step

- `finalized`
  - the same ctxtsw committed and architectural ownership is now official

- `canceled`
  - the ctxtsw was invalidated by freeze/reset/resume/redirect/older winner

## Ownership Model

Do not treat one thread-id signal as both speculative and architectural without explicit bookkeeping.

Define these concepts explicitly:

- `arch_thread_id`
  - the officially committed BE thread id

- `spec_ctxtsw_active`
  - whether a speculative handoff is active

- `spec_thread_id`
  - the target thread id of the launched speculative switch

Near-term implementation can keep `current_thread_id_lo` as the architectural thread id and add separate speculative state first. That lets FE launch happen without immediately reusing BE architectural ownership as the same concept.

## Required Invariants

### Invariant 1: one token per switch

Each early launch token must correspond to exactly one ctxtsw instance.

Allowed creator:
- the specific `dispatch_pkt.ctxtsw_v` event for that switch

Not allowed:
- sticky `pending_ctxtsw_v_r` by itself
- raw commit-time pulse reused as launch authority

### Invariant 2: launch is invalid across startup boundaries

Speculative ctxtsw state must be invalidated on:

- `reset_i`
- `cfg_bus.freeze`
- `commit_pkt.resume`
- FE `state_reset/resume` envelope if exposed

The host flow in `ps.cpp` freezes the core, writes NPC, loads NBF, then unfreezes. A speculative ctxtsw must not survive across those transitions.

### Invariant 3: launch requires explicit FE eligibility

FE readiness must mean more than “state is run-like.”

Early launch must not happen if FE is in:

- `e_reset`
- `e_wait`
- `e_resume`

and must also avoid overlap with state-reset/resume/fence command traffic.

### Invariant 4: cancel beats finalize if older control wins

Any older redirect/trap/interrupt/freeze winner must cancel a speculative ctxtsw before it can finalize.

### Invariant 5: old-thread save point is explicit

The old-thread resume context must be saved from one clear authority.

If FE launches early but BE architectural finalization remains commit-time, then the old-thread save still belongs to the commit-time path unless and until a new explicit speculative save protocol exists.

## File-by-File Plan

### 1. `bp_be/src/v/bp_be_top.sv`

Add speculative ctxtsw state registers:

- `spec_ctxtsw_state_r`
- `spec_ctxtsw_valid_r`
- `spec_ctxtsw_launched_r`
- `spec_ctxtsw_thread_id_r`
- `spec_ctxtsw_prev_thread_id_r`
- `spec_ctxtsw_npc_r`
- `spec_ctxtsw_priv_mode_r`
- `spec_ctxtsw_translation_en_r`
- `spec_ctxtsw_asid_r`

Responsibilities:

- capture target bundle on detect
- clear speculative state on reset/freeze/resume/cancel/finalize
- keep architectural `current_thread_id_lo` behavior unchanged at first
- continue feeding the old commit-time ctxtsw path until launch is explicitly enabled

Phase 1 behavior:
- scaffolding only
- no launch behavior change

### 2. `bp_be/src/v/bp_be_checker/bp_be_director.sv`

Add explicit named conditions:

- `ctxtsw_detected_v`
- `ctxtsw_prepared_v`
- `ctxtsw_launch_allowed_v`
- `ctxtsw_cancel_v`
- `ctxtsw_finalize_v`
- `ctxtsw_launch_v`

Responsibilities:

- own launch authorization
- own FE speculative ctxtsw command issuance
- own cancel/finalize transitions
- keep startup-sensitive transitions explicit

Launch should eventually require:

- prepared token valid
- FE eligible
- not frozen
- no resume/state-reset path active
- no overriding redirect/fence conflict
- no prior launch for the same token

Phase 1 behavior:
- compute these conditions
- do not yet use them to change outputs

### 3. `bp_fe/src/v/bp_fe_controller.sv`

Current output:
- `ctxtsw_ready_o = is_run`

Potential stronger export if needed:

- `ctxtsw_eligible_o`

Meaning:
- FE is in `e_run`
- not in resume transition
- not draining reset traffic
- not in wait

Phase 1 behavior:
- no functional FE change required if `ctxtsw_ready_o` stays scaffolding-only

### 4. `bp_top/src/v/bp_core_minimal.sv`

Responsibilities:

- thread any new FE eligibility or debug visibility signals between FE and BE

Phase 1 behavior:
- pure plumbing only

## Phased Implementation

### Phase A: speculative FSM scaffolding only

Files:
- `bp_be_top.sv`
- `bp_be_director.sv`
- maybe `bp_core_minimal.sv`

Behavior:
- none changed

Verification:
- `prep_lite`
- `mt_ctxtsw_microbench`

Exit criteria:
- baseline still `14/7`
- state machine signals visible in waveform/debug

### Phase B: explicit cancel/invalidate policy

Behavior:
- speculative ctxtsw state is cleared on:
  - reset
  - freeze
  - resume
  - commit-time redirect winner
  - commit-time ctxtsw finalize

Still:
- no early FE launch yet

Verification:
- `prep_lite`
- `mt_ctxtsw_microbench`
- optional waveform spot-check during startup path

Exit criteria:
- no baseline change
- startup path still clean

### Phase C: speculative FE launch only

Behavior:
- FE ctxtsw command may launch from `prepared -> launched`
- BE architectural thread id remains commit-time for this step

Purpose:
- isolate whether FE-only speculation can be made startup-safe under the new contract

Verification:
- `prep_lite`
- `mt_ctxtsw_microbench`
- waveform:
  - `ctxtsw_v`
  - speculative FSM state
  - `fe_cmd_v_li`
  - `thread_id_r`
  - `if2_pc_o`

Exit criteria:
- no startup/NBF hang
- if successful, measure `ctxtsw_v -> fe_cmd_v_li`

### Phase D: speculative BE ownership if necessary

Behavior:
- if FE-only speculation is not enough, add speculative BE ownership state
- keep architectural finalize at commit

This should be attempted only if Phase C is stable.

### Phase E: timing optimization

Only after the protocol is stable:

- try to shrink launch latency
- reevaluate whether `7 -> 6` or `7 -> 5` is reachable

## Verification Checklist

After every phase:

1. `make -j24 prep_lite`
2. `make -C cosim/black-parrot-minimal-example/verilator run PROG=mt_ctxtsw_microbench`

At key checkpoints:

1. clean rebuild before waveform/debug
2. waveform on:
   - `dispatch_pkt.ctxtsw_v`
   - speculative ctxtsw state
   - `fe_cmd_v_li`
   - `fe_cmd_yumi_i`
   - `current_thread_id_lo`
   - `thread_id_r`
   - `if2_pc_o`

Success criteria by stage:

- Phase A/B:
  - no behavior change

- Phase C:
  - no startup hang
  - same or better microbench result

- Later phases:
  - `ctxtsw_v -> fe_cmd_v_li` shrinks
  - benchmark improves

## Immediate Next Step

Implement Phase A only:

- add explicit speculative ctxtsw FSM scaffolding in `bp_be_top.sv`
- add explicit named launch/cancel/finalize conditions in `bp_be_director.sv`
- keep all outputs behaviorally identical

No early launch attempt should be retried before that scaffolding is in place and verified.
