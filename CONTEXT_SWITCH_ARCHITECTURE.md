# Context Switch Architecture And Current Status

This repo is currently focused on fast resident hardware-thread context
switching for BlackParrot.

Current working branches:

- `zynq-parrot`: `ctxtsw-isd-repair`
- `import/black-parrot`: `ctxtsw-isd-repair`

Use `git rev-parse --short HEAD` in each repository for the exact local
checkpoint. These docs describe the branch state after the ring-deadlock,
thread-metadata, UCE-credit, and CSR RAW-hazard fixes.

The top-level repo carries test programs, harness changes, waveform tools, and
writeups. The actual RTL implementation lives in `import/black-parrot`.

## Current Model

The machine is still one shared BlackParrot pipeline. It now holds multiple
resident architectural contexts and switches which context is live.

Software controls contexts through CSRs:

- `0x081`: switch to a target resident context
- `0x082`: seed a dormant context's entry/resume PC
- `0x083`: remotely seed architectural register state, including branch-specific
  FP register support where present

Per-context state includes:

- integer register state
- floating-point register state
- CSR/control state
- saved next PC / resume PC
- privilege mode
- translation-enable state
- ASID
- frontend thread identity and predictor state where implemented

The baseline architectural rule is:

> `commit_pkt.ctxtsw` is the authority for architectural context-switch
> finalization.

Early or speculative work must reconcile back to that authority unless the RTL
introduces an explicit replacement protocol with event identity, launch,
finalize, and cancel semantics.

## Baseline End-To-End Switch Path

In the committed-switch model:

1. Software writes the target thread id to CSR `0x081`.
2. The instruction flows through the normal backend pipeline.
3. On commit, BE recognizes `commit_pkt.ctxtsw`.
4. Old-thread resume state is saved.
5. Target-thread state is selected and live ownership changes.
6. BE emits an FE context-switch/restart command.
7. FE restarts fetch under the target thread's PC, privilege, translation, ASID,
   and frontend thread identity.

This is a BE-driven architectural switch followed by FE restart. It is not a
frontend-only redirect.

## Current Branch Path

The checked-out `ctxtsw-isd-repair` RTL adds an early sideband/token path on top
of the committed-switch model.

Current source-level facts:

- `bp_be_scheduler.sv` classifies immediate context switches in the issue path
  as CSR writes to `12'h081`.
- `bp_be_detector.sv` treats register-form CSR writes as dependent on a
  preceding early integer producer when they use the same `rs1`; this avoids
  writing stale source data into CSRs such as `mscratch`.
- `bp_be_top.sv` captures a pending target bundle from the fast context-switch
  event when the core is not frozen or resuming.
- `bp_be_top.sv` can drive the FE sideband outputs:
  `fe_ctxtsw_v_o`, `fe_ctxtsw_npc_o`, `fe_ctxtsw_thread_id_o`,
  `fe_ctxtsw_priv_o`, `fe_ctxtsw_translation_en_o`, and `fe_ctxtsw_asid_o`.
- `bp_fe_controller.sv` accepts that sideband only when FE is in run state and
  the I-cache path accepts the redirect (`ctxtsw_v_i & is_run & icache_yumi_i`).
- `pending_ctxtsw_sent_r` records that FE accepted the early sideband, so the
  later commit-time FE command can be suppressed without suppressing
  architectural finalization.
- `current_thread_id_lo` still updates on `commit_pkt.ctxtsw`; a non-ctxtsw
  redirect while a pending switch exists restores the previous thread id.
- BE-to-FE redirects that resume the current thread must preserve branch
  metadata carrying the current frontend thread id; otherwise a nonzero-thread
  CSR redirect can silently retag FE fetch as thread 0.
- The scheduler has a commit-accept path so a target FE packet already available
  during context-switch commit cleanup can be accepted under the pending target
  thread id.

So the current branch should be understood as:

> early FE preparation/redirect plus commit-time BE architectural finalization.

It is not a fully speculative BE ownership handoff. Any future change that moves
BE ownership earlier must add a stronger finalize/cancel protocol.

## Verified Baseline Claim

The older stable committed path established the useful reference point:

- `mt_ctxtsw_roundtrip_benchmark`: warm round-trip `0x0e`, implying `0x07` cycles/switch
- `mt_ctxtsw_ring_throughput_benchmark`: `0x07` cycles/switch
- `mt_ctxtsw_pure_ring_stress_test`: dense pure-ring stress passed

That `7 cycles/switch` result means a warm, minimal resident-context handoff
where the target context is pre-seeded, target instructions are hot, and the
benchmark excludes setup, printing, loop bookkeeping, and miss/refill tails.

It does not mean every context switch in an arbitrary workload is always seven
cycles.

## Current ISD Repair Status

The current `ctxtsw-isd-repair` work is no longer just the old 7-cycle committed
path. It explores an ISD/commit-accept repair that can preserve an already
fetched target packet during context-switch commit cleanup.

Current local documentation, branch history, and RTL shape indicate the important
result:

- favorable gap/unrolled cases can reach the `0x5` class
- correctness tests such as regfile/CSR/FRF isolation and smoke tests have
  passed in the repaired state
- the dense `mt_ctxtsw_roundtrip_benchmark` can still report a much longer tail
  (`0x6b` round-trip / `0x35` estimate in recorded runs)

Treat that dense microbench behavior as the active performance investigation,
not as proof that the basic state-isolation repairs are broken.

## Main RTL Areas

Backend:

- `bp_be_top.sv`: live thread selection, pending context-switch state, saved
  context state, target context selection
- `bp_be_director.sv`: FE command/restart sequencing and commit-time cleanup
- scheduler / issue queue / detector files: ISD classification, FE queue
  accept/clear/roll behavior, hazard and thread-id ownership
- calculator / pipe memory files: commit packet generation, replay, side
  effects, late writeback
- CSR/regfile files: CSR `0x081`/`0x082`/`0x083`, per-thread register/CSR state

Frontend:

- `bp_fe_controller.sv`: context-switch restart acceptance and redirect control
- `bp_fe_pc_gen.sv`: active FE thread identity and predictor context selection
- `bp_fe_icache.sv`: stale old-thread miss/recover escape, abort/fill behavior,
  and target fetch availability
- TLB/MMU files: ASID and translation state across switches

## Measurement Rule

For performance claims, name the endpoints.

Useful endpoints include:

- `ctxtsw detect`
- FE sideband/command accept
- redirect / target fetch launch
- first target FE queue entry
- first target BE dispatch
- `commit_pkt.ctxtsw`
- first target `instret`

The primary context-switch overhead metric is the number of dead or discarded
cycles from architectural `commit_pkt.ctxtsw` / redirect to the first useful
target-context FE queue or BE dispatch. I-cache miss, abort, and refill tails
should be reported separately.
