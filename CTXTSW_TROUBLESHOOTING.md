# Context-Switch Troubleshooting Notes

This file keeps the durable lessons from older context-switch experiments. It is
not a complete diary of every branch state.

## Default Debug Rule

For any unexpected hang, pass/fail discrepancy, wrong output, or surprising
cycle count:

1. Stop changing RTL.
2. Reproduce with the smallest relevant `make -C testing ... TRACE=1` run.
3. Use the waveform tools before making another guess.
4. Compare against a clean known-good baseline when possible.

Keep debug instrumentation separate from functional fixes and remove it once
the measurement is understood.

## Common Failure Signatures

### Board disappears during overlay reload

If artifact staging has verified the package and NBF hashes but SSH is refused
while `load-blackparrot-overlay` is still running, no guest result exists. Treat
the board as contaminated, power-cycle it, wait for the PYNQ-ready gate, and
reload before retrying; do not classify that interruption as an RTL failure.

### Stall after NBF load

Typical output:

```text
BSG-INFO:    ps.cpp: beginning nbf load
```

followed by no benchmark banner or pass/fail output.

This usually means the change disturbed startup/freeze/resume/control
sequencing, not only the measured context-switch loop.

### Wrong or illegal instruction after sideband/fast-path work

Older failed sideband experiments produced wrong instruction fetches around
known benchmark PCs. Treat this as FE fetch/realign/queue metadata or I-cache
state corruption until proven otherwise.

### Trace and non-trace disagree

Trace markers, waveform gating, stale Verilator objects, or host scheduling can
change timing enough to hide a bug. Do a clean rebuild before trusting
waveform-dependent conclusions.

### Gap tests disagree unexpectedly

Check the binary shape with objdump. A gap helper that becomes an out-of-line
call/return sequence is no longer testing the same straight-line gap. The
controlled-gap helper should remain forced inline.

### CSR isolation reports a stale written value

If `mt_csr_isolation_test` reports that T1 wrote the value produced by the first
instruction of a `li` sequence, such as `0x5a5a6000` instead of `0x5a5a5a5a`,
check the register-form CSR write RAW path. The CSR source operand must not
consume an early integer producer before the final value is available.

### Ring isolation is quiet after NBF load

`mt_ctxtsw_4ctx_ring_isolation` intentionally prints only after the ring
returns to T0. A pre-ring banner can leave host MMIO stores outstanding; combined
with the thread-body fences, that exercises host I/O ordering instead of just
CSR/thread isolation.

## Durable Lessons

- `commit_pkt.ctxtsw` is the baseline architectural authority.
- `target ready` is not enough to launch an early switch safely.
- `pending_ctxtsw_sent_r` is not a complete protocol by itself.
- Early FE redirect is safer than early BE ownership, but still needs explicit
  finalization/cancel rules.
- Moving BE ownership before commit is high risk unless old-thread retirement
  identity, target-thread dispatch, context save, and rollback are fully
  separated.
- Memory side effects are not commit-only; arbitrary target-context BE execution
  before old-thread context-switch commit is not globally safe.
- Poison is not the same as hold/backpressure. If an entry is read while
  poisoned, the design may drop work that should have been held.
- A duplicate commit-time FE command may need suppression after early FE accept,
  but commit-time cleanup/fence/finalization often still needs to run.
- I-cache redirect/force behavior must not expose partially completed stale
  old-thread fills as valid target-thread instruction data.
- Thread IDs must follow queue entries, hazards, replay, late writeback,
  regfile writes, and host/MMIO side effects.
- BE-to-FE redirect metadata must preserve the owning thread id. A nonzero
  thread that takes a CSR/translation redirect with zeroed branch metadata can
  restart FE under thread 0.
- UCE request credits are used as an ordering signal by fences. Count one
  outstanding request per complete forward command and verify `credits_empty`
  before trusting fence-related deadlock conclusions.

## Early-Handoff Contract

Any future early/speculative design needs:

- one explicit token per classified switch
- a launch condition tied to FE eligibility, not just target readiness
- a single authority for architectural thread ownership per phase
- a defined old-thread save point
- explicit cancel paths for reset, freeze, resume, flush, exceptions,
  non-ctxtsw redirects, and squashed switches
- exactly-once finalization

Without those properties, previous attempts have split FE and BE ownership into
ambiguous states.

## Useful Tests

Smoke and basic state:

```bash
make -C testing run-mt_ctxtsw_smoke_test TRACE=1
make -C testing run-mt_regfile_test TRACE=1
make -C testing run-mt_csr_isolation_test TRACE=1
make -C testing run-mt_frf_isolation_test TRACE=1
```

Hazards and side effects:

```bash
make -C testing run-mt_ctxtsw_late_wb_hazard_test TRACE=1
make -C testing run-mt_abi_preservation_test TRACE=1
make -C testing run-mt_ctxtsw_gpr_ring_stress TRACE=1
```

Performance and spacing:

```bash
make -C testing run-mt_ctxtsw_roundtrip_benchmark TRACE=1
make -C testing run-mt_ctxtsw_gap8_benchmark TRACE=1
make -C testing run-mt_ctxtsw_ring_throughput_benchmark TRACE=1
make -C testing run-mt_ctxtsw_pure_ring_stress_test TRACE=1
```

## Waveform Focus

When debugging a switch window, start with:

- ctxtsw detect/dispatch
- pending token create/accept/finalize
- FE sideband or FE command accept
- redirect PC/thread metadata
- FE queue clear/roll/enqueue/accept
- issue queue preissue/dispatch
- `commit_pkt.ctxtsw`
- `current_thread_id_lo`
- I-cache state, force, abort, request, critical/last response
- late writeback thread ID and destination register

Use `$zynq-parrot-waveform-debug` for the repo tool map and cycle-level analysis
workflow.
