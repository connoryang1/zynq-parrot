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

### Archived Linux runner reads an invalid reset CSR

The protocol-compatible runner identified by SHA-256 `76db…` is required for
the archived January bitstream, but it is not interchangeable with every
routed candidate. If its first base-register read reports a non-Boolean reset
value and does not reach NBF configuration, stop and power-cycle; restore the
candidate's reviewed runner before continuing. That is a host/bitstream
protocol mismatch, not guest or RTL evidence.

### Detached serial launch disappears before creating a transcript

On this PYNQ image, a `setsid`/`nohup` control-program wrapper can be reaped
when its originating SSH session closes, before it creates either its retained
log or status file. This is a launcher failure, not a board run: verify that
no `control-program` is alive, reload the intended overlay, and use the
serial helper with `PYNQ_CONTROL_PROGRAM_FOREGROUND=1` for the next bounded
or self-terminating control.

### Historical source checkpoint silently times out under a current runner

An old source revision that once booted Linux is not itself a sufficient FPGA
control. The rebuilt `2a1f8834` / `ce328a77` pair and the CSR-only candidate
both timed out silently with the same 0.133339 IPC signature under the current
reviewed runner, so do not attribute the candidate result to its RTL delta.
First establish a freshly bootable source/bitstream/host-runner control, then
perform an A/B comparison using identical NBF, runner hash, power-cycle, and
overlay-load procedure.

That control now exists for the pre-feature `4015d0f` / `08edfb` pair: its
freshly built bitstream reaches `/init` only with the source-matched legacy
threaded FIFO runner (`b774f7…`), while the newer pybind/PYNQ runner produces
the misleading silent 0.133-IPC loop. Treat the host runner as a versioned
component of every Linux classification, not incidental board tooling.

### Linux runner must explicitly zero DRAM, but zeroing is not a boot proof

The archived Linux runner includes `FREE_DRAM=1 ZERO_DRAM=1`; a normal runner
compiled with `ZERO_DRAM=0` is not an equivalent test even if the source and
NBF hashes match. Build a temporary hash-pinned zeroing runner and require its
`zero-d 0 MB` through `zero-d 63 MB` transcript before comparing Linux runs.
That condition is necessary but not sufficient: the exact historical baseline
still showed the same silent loop after a verified zeroing-runner control.

### Legacy Vivado flow supplies its own mode

The preserved pre-feature source invokes Vivado as `-mode batch`, whereas the
maintained 2024.2 wrapper historically added that option unconditionally.  Do
not treat Vivado's `mode can only be specified once` error as a source or RTL
failure: the wrapper now preserves a caller-supplied mode and only defaults to
batch when none is present.

### Historical source uses nested FPGA submodules

The 2015-style source graph contains a nested
`black-parrot-subsystems/zynq/import/riscv-dbg` gitlink.  A top-level
submodule initialization is insufficient: before legacy Vivado packaging, run
the exact submodule's recursive initialization and verify `src/dm_pkg.sv` is
present.  A missing file is a reproducible checkout failure, not a missing RTL
source or a synthesis result.

### Historical PLIC sources are generated collateral

The older `zynq/v/gen` PLIC directory is not committed with its source
snapshot.  Regenerate its patched OpenTitan PLIC first and stage the required
primitive and generated `rv_plic_*` files as one matched bundle; the pinned
historical configuration yields the same PLIC RTL hashes as the maintained
generator.  Do not substitute an arbitrary OpenTitan revision, because the
wrapper and register-package interfaces must match the historical PLIC glue.

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
