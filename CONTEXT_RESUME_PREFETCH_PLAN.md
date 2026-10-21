This document defines the context-resume instruction-prefetch experiment. It records the existing evidence, the speedup bounds, the staged implementation, and the simulator-first acceptance gates so that a new cache-resume result is not confused with the older data-prefetch results.

# Context-resume instruction prefetch

## Question

Can a hardware thread remember the first instruction lines used by its paired
software thread and fetch a high-confidence prefix before or during a context
switch, reducing the cold-start interval before useful target execution?

This is a context-switch warm-start optimization, not a general replacement
for ordinary software prefetching. The first implementation should use a
software-seeded or oracle footprint; automatic learning comes only after the
timing and correctness path is understood.

## Existing evidence and expected range

The retained Linux resume decomposition gives the following bounds:

| Condition | Median cycles | Interpretation |
| --- | ---: | --- |
| Hot same-mm resume | 5,551 | Scheduler and already-warm target baseline |
| 32 KiB instruction displacement | 12,160 | +6,609 cold-instruction penalty |
| 128 KiB clean-data displacement | 11,136.5 | +5,585.5 cold-data penalty |
| Both displacements | 17,335–17,421.5 | Ideal combined opportunity near 3.1× versus hot |

These are displacement controls, not a result for the proposed hardware.
They establish that instruction state can matter substantially in a long Linux
resume. They do not imply that a 5–11-cycle resident handoff can hide hundreds
of line refills.

The existing replay and retention analysis bounds the useful regimes:

- an oracle 128/160/192-line replay reduced post-resume application work by
  about 6×, but scheduler-inclusive speedups were only 1.39×/1.49×/1.56×;
- combining that replay with the measured hot-kernel floor projects 2.63×,
  2.78×, and 2.85×, but these are composed upper bounds;
- a realistic automatic data signature was projected at only 0.2–2.5% phase
  reduction, while exact physical hints saved roughly 74–80 cycles in the
  controlled same-mm experiment;
- full 128–192-line replay requires early background issue, retention, or both.

Therefore the first implementation should target a prioritized prefix of a
few instruction lines. The expected initial result is tens to a few hundred
saved cycles on a deliberately cold resume, potentially around 1.1–1.5× for a
long scheduler-inclusive phase. A near-3× result is an oracle ceiling, not the
expected first hardware result. For a five-to-eleven-cycle resident handoff,
the expected speedup is zero unless fetch begins before the switch and the
target is already known with high confidence.

## Existing benchmarks and controls

Use these in order:

1. `mt_ctxtsw_nonresident_overhead_benchmark`: matched resident/nonresident
   rings using global CSR `0xcc0`; this is the baseline timing gate.
2. `mt_umode_nonresident_sv39_data_handoff_test`: correctness for translated
   instruction/data handoff and target replay recovery.
3. `mt_cache_miss_trace_test`: verifies the I/D miss recorder and provides
   request-level evidence, but is not itself a speedup benchmark.
4. `mt_ctxtsw_pure_ring_stress_test`: dense-switch correctness only.
5. The retained Linux scheduler-resume and cold-displacement traces provide
   realistic target footprints after the directed path is working.

The existing `mt_prefetch_nonresident_interleave_benchmark` and dependent
stream tests remain useful memory-interleaving regressions, but their data
prefetch workload must not be used as an instruction-resume result.

## Staged experiment

### Stage A — baseline and directed oracle

Add a matched 2-resident/4-context benchmark with a runtime-selected mode:

- cold target, no resume prefetch;
- exact target instruction prefix requested before the switch;
- exact prefix requested at switch launch;
- warm target control.

Keep context setup, code layout, measured work, result checks, and global-cycle
bookkeeping identical. Report switch-to-first-use, first/last request and
response, useful-before-demand count, total cycles, and prefetch traffic.

### Stage B — target-context correctness

Run the prefix through the target context's page table/ASID and execute only
permission-checked instruction requests. A missing or non-executable page must
not become an architectural fault before the target context runs. Invalidate
or disable a footprint when the code mapping changes.

### Stage C — small footprint and confidence sweep

Sweep 1/2/4/8 instruction lines and correct versus stale target predictions.
Retain the existing data-hint rule that wrong predictions can cost more than
correct predictions save; use a short prefix unless confidence is high.

### Stage D — learned footprint and Linux replay

Only after the directed path is stable, learn the first unique instruction
lines after each resume and replay a high-confidence prefix while the target is
off CPU or at an early scheduler boundary. This stage is where the realistic
Linux results belong; it must not be inferred from the oracle controls.

## Acceptance

Simulation is the iteration path. Every RTL or benchmark change gets a clean
target rebuild and a traced directed run. The result is not promoted as an
application speedup until it has a matched no-prefetch control, exact target
topology, request-level evidence, and a final routed/physical checkpoint.

The first claim we should seek is modest:

> A high-confidence instruction prefix can overlap part of a cold context
> resume and reduce time to first useful target execution.

Only a later Linux experiment can support a stronger end-to-end speedup claim.
