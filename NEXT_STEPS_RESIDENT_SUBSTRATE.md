# Current Plan: Resident Context-Switch Substrate

The current milestone is to finish validating the resident hardware-thread
substrate before taking on broader Linux-facing or cache-backed context work.

## Immediate Goal

Make the `ctxtsw-isd-repair` branch reviewable:

- keep commit-time architectural ownership coherent
- preserve the ISD/commit-accept repair where it is correct
- explain the remaining dense-microbench performance tail with waveform evidence
- avoid reintroducing broad speculative handoff experiments until the current
  path is measured and stable

## Phase 1: Lock Down Current Correctness

Use serialized `make -C testing ... TRACE=1` runs. Do not run testing flows
concurrently unless separate simulator/build outputs are deliberately configured.

Minimum correctness ladder:

```bash
make -C testing run-mt_ctxtsw_smoke_test TRACE=1
make -C testing run-mt_regfile_test TRACE=1
make -C testing run-mt_csr_isolation_test TRACE=1
make -C testing run-mt_frf_isolation_test TRACE=1
make -C testing run-mt_ctxtsw_late_wb_hazard_test TRACE=1
```

Add the ABI/GPR/ring tests when touching register ownership, writeback, hazard,
or multi-context behavior.

## Phase 2: Explain Current Performance

Primary tests:

```bash
make -C testing run-mt_ctxtsw_gap8_benchmark TRACE=1
make -C testing run-mt_ctxtsw_ring_throughput_benchmark TRACE=1
make -C testing run-mt_ctxtsw_roundtrip_benchmark TRACE=1
```

For each performance claim, collect:

- exact command
- pass/fail output
- waveform path
- measured endpoints
- cycle deltas
- whether I-cache miss/abort/refill tails are part of the measured number

The known open question is why favorable gap/unrolled shapes can reach the
`0x5` class while the dense original microbench has shown a much longer tail.

## Phase 3: Expand Resident-Context Validation

After the current branch is stable, expand coverage before refactoring:

- larger context counts
- repeated switching across privilege-mode combinations
- repeated switching across address-space / ASID combinations
- exception and trap behavior after a switch
- timer/interrupt behavior after a switch
- call/return predictor behavior, especially shared RAS behavior

## Phase 4: Define Control Semantics

Write the software-visible model clearly:

- how a context is created or seeded
- what dormant, resident, runnable, and live mean
- how one context may modify another context's architectural state
- what committed `ctxtsw` means architecturally
- what resume PC/state is expected after a switch

If this model cannot be explained cleanly, that is evidence that a
threading-first refactor may be justified.

## Refactor Decision Gate

Do not start a first-class/speculative redesign just because the current path is
not ideal. Revisit the design only after the current resident substrate has been
pushed far enough to show a real structural limit.

A larger refactor is justified if:

- scaling context count requires scattered, fragile plumbing
- software-visible semantics become awkward or inconsistent
- rollback/cancel behavior cannot be made explicit in the current structure
- Linux-facing control semantics would require ad hoc interfaces
- cache-backed contexts cannot layer cleanly on top of resident contexts
