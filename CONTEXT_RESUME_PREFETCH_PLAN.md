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

### First matched simulation checkpoint

The new `mt_context_resume_prefix_benchmark` selects its mode through the
same post-load runtime patch mechanism used by the other benchmark programs.
It places a 96-operation target prefix in an aligned text region, seeds the
same nonresident target, and times only the switch-to-completion interval.
Mode 0 leaves the target context cold. Mode 1 runs that exact entry and prefix
on the target context, switches back, reseeds it, and then measures the same
handoff; the oracle warmup is outside the timed interval.

With `NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1`, the matched runs measured:

| Mode | Resume cycles | Result |
| --- | ---: | --- |
| Cold target prefix | 490 | pass |
| Target-context oracle warm | 172 | pass |
| Source-context warm | 226 | pass |
| Switch-only control | 97 | pass |

This is a 2.85x oracle warm-start speedup (318 cycles, 64.9% fewer), not a
prefetcher result. It demonstrates that the selected target instruction state
is materially on the resume path and gives the future RTL a useful upper-bound
control. Warming only the source context is 2.17x (226 cycles), while removing
the prefix body leaves a 97-cycle switch-only floor. The next experiment must
replace the warmup with a real permission-checked instruction request while
keeping these mode boundaries and the same target code layout.

### RTL seam and minimum safe interface

The frontend currently has one I-cache request stream driven by
`bp_fe_controller`, and the MMU address input is always `next_pc` from the
active context. The backend already knows the pending target NPC, privilege,
translation-enable bit, and ASID, but the saved translation bundle does not
reach the frontend with the target request's base PPN or SUM/MXR permissions.
Consequently, simply reusing the existing data-prefetch path would either use
the wrong address space or turn a speculative target request into an
architectural fetch or fault.

The minimum safe implementation should therefore be staged as follows:

1. Add a one-entry target-request bundle from the backend context handoff to
   the frontend: virtual context ID, NPC, physical slot, privilege,
   translation state, ASID, base PPN, SUM/MXR, and a short-prefix count.
2. Let the FE controller hold that bundle when a switch is captured and issue
   one speculative I-cache request before accepting the redirect. Its hit or
   fill response must be consumed as advisory state, never entered into the
   active context's FE queue.
3. Preserve the existing redirect pending/flush rules and cancel the bundle
   on a younger redirect, trap, or context-switch cancellation.
4. Start with direct-mode simulation only, where the target physical address
   is unambiguous. Add translated permission checks only after the request,
   fill, and cancellation state machine is stable.

This should not mutate `bp_fe_icache_pkt_s` in place: that packet has no
address-space identity, and doing so would risk mixing a target fill with the
active context. The first RTL change should add an explicit sideband/arbiter
and a traced request marker so acceptance, response, and cancellation can be
measured independently.

### Rejected first slice and revised cache seam

The first direct-mode prototype reused the architectural I-cache request
stream, substituted the saved target NPC, and waited for that request to be
accepted before redirecting. It passed the directed correctness checks but
regressed every matched mode (cold 490 to 554 cycles, target-warm 172 to 184,
source-warm 226 to 227, and switch-only 97 to 99), so it was reverted. The
regression shows that a target request cannot be made advisory merely by
holding the normal frontend stream: it adds a pipeline/redirect dependency and
does not provide a useful overlap point.

The cache hierarchy already defines `e_cache_prefetch` and the UCE can service
that best-effort request without an architectural response. The next minimal
implementation should therefore add an explicit `prefetch` bit to the
frontend I-cache packet and carry it through the TL/TV stages to select
`e_cache_prefetch`; `spec` must remain reserved for the existing
permission/translation semantics. The target request still needs a separate
context/translation sideband and an acceptance/cancellation handshake, but it
can then reuse the existing UCE capacity and response-drain rules instead of
creating a second memory path.

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

Use the matched `mt_context_resume_prefix_benchmark` as the 2-resident/4-context
baseline, then extend its runtime-selected modes to:

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
