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

The pre-trace plan therefore targeted only a few prioritized instruction
lines, expecting tens to a few hundred saved cycles. The ordered trace model
below supersedes that sizing choice by showing a stable shared privileged
prefix can be much larger and still timely. It does not turn the near-3×
oracle ceiling into an implemented result. For a five-to-eleven-cycle resident
handoff, replay still has zero expected benefit unless it begins before the
switch; retained state remains the appropriate mechanism there.

### Trace-driven architecture selection

The exact physical Linux demand traces now replace the earlier aggregate
capacity estimate. `logs/cache-resume-trace-model-20261029/` trains an
eight-MRU-lines-per-set privileged prefix on the preceding complete handoff and
schedules every predicted line against the next two measured demand windows.
With four slots, a conditional 41-cycle first response beat, and the measured
19-cycle installer median, 175 unique predicted lines are ready before first
demand, two are late, and 34 predictions are unused. The trained prefix is
83.9% useful and covers 177/266 demand records in time. Proportional scaling
of the separately measured 6,609-cycle cold-instruction penalty gives a
4,397.7-cycle upper bound, not an implemented speedup.

The conclusion is insensitive to the optimistic 41-cycle proxy: with a
200-cycle first beat and four slots, 164 unique lines remain timely. In
contrast, trace-trained one/two/four-line retention covers only one/three/six
unique lines. Adding four oracle-immediate retained lines to shared replay
raises timely coverage only from 175 to 179. The selected first RTL is
therefore an early shared privileged-prefix replay lane with four full-line
slots; retention becomes a later first-line and very-short-handoff complement.

### First matched simulation checkpoint

The new `mt_context_resume_prefix_benchmark` selects its mode through the
same post-load runtime patch mechanism used by the other benchmark programs.
It places a 96-operation target prefix in an aligned text region, seeds the
same nonresident target, and times only the switch-to-completion interval.
Mode 0 leaves the target context cold. Mode 1 runs that exact entry and prefix
on the target context, switches back, reseeds it, and then measures the same
handoff; the oracle warmup is outside the timed interval.

The original `NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1` checkpoint measured:

| Mode | Resume cycles | Result |
| --- | ---: | --- |
| Cold target prefix | 490 | pass |
| Target-context oracle warm | 172 | pass |
| Source-context warm | 226 | pass |
| Switch-only control | 97 | pass |

This historical result is a 2.85x oracle warm-start speedup (318 cycles, 64.9%
fewer), not a prefetcher result. A later clean build on 2026-10-23 reproduced
mode 0 twice at 552 cycles, mode 1 at 183, mode 2 at 226, and mode 3 at 97.
All four passed the guest and host checks. The cold and target-warm values
therefore do not currently reproduce the 490/172 checkpoint, while source-warm
and switch-only do. Until the compiler/linker inputs or generated program from
the original run are recovered, use 552/183/226/97 as the current control
matrix and treat 490/172/226/97 as historical evidence only. The selective
shift suggests a target-code placement or I-cache state difference, but its
cause is not established.

The mode-1 name means “target warmup,” not a verified L1-I hit at timed resume.
On the enlarged same-ELF probe, the I-cache request trace shows the first three
target prefix lines requested once during warmup and again during the timed
resume. A temporary nine-line same-set eviction mode measured 180 cycles,
versus 181 for mode 1 on that same ELF, and also re-requested the target line.
The ordinary warmup/return/setup sequence already leaves these lines missing,
so the synthetic eviction added no distinct condition and was removed. This
trace supports measuring retained-line hits directly before estimating their
speedup; the cycle comparison alone does not establish one.

### RTL seam and required independent lanes

The FE has one architectural I-cache stream, and its MMU read port and cache
arrays serve that stream. Reusing that stream for the target request showed
higher counts than the historical controls, although the later no-target-wiring
rerun means that regression is not yet isolated. The backend does have an
earlier launch opportunity: it
recognizes a nonresident target at dispatch, before switch commit and register
restore, while it does not launch the normal FE redirect until restore finishes.
Each virtual context also retains a CSR snapshot containing SATP. The root is
available in backend state, but is not part of the existing FE redirect
sideband.

A viable design therefore needs a separately queued advisory request from
dispatch, with no dependency in either direction between its acceptance and
the architectural redirect. The target translation lookup must not consume an
architectural I-TLB request slot. A bounded first slice can issue only on a
target-context TLB hit and drop TLB misses; the target's ordinary fetch then
performs its usual page walk and fault handling. The target's execute
permission must be checked before any detached memory read is issued.

The current I-cache UCE does not provide the needed fill path. Its prefetch
setting is disabled in the active I-cache configuration; its enabled narrow
mode issues 16-byte requests and returns data through `e_cache_data_mem_prefetch`,
which the I-cache does not install. The full-line installer is tied off in
this checkout. A historical D-cache full-line mode buffers complete lines,
but takes exclusive cache access while installing and can hold a same-line
demand behind the advisory request. It is a protocol reference, not an
I-cache implementation to enable directly.

The selected shared-prefix dataflow is:

1. At syscall or scheduler entry, enqueue an M-configured ordered prefix of
   shared kernel/OpenSBI physical instruction lines plus a cancellation epoch.
   User mode cannot supply or modify these physical addresses.
2. Keep this first slice target-independent. The ordinary architectural MMU
   still performs translation and execute-permission checks before any demand
   can consume an installed line. A later private-prefix extension requires a
   separate target translation path and is not part of this prototype.
3. Send a detached full 64-byte read into a small response buffer. It must not
   consume or rewrite the architectural I-cache TL/TV request stages.
4. Install from the completed buffer through a demand-priority I-cache
   arbiter. Publish the tag only after all four 16-byte fill beats are
   written. If demand reaches that line first, let demand proceed and merge
   the buffered response or cancel/drop it; never hold demand waiting for an
   advisory completion.
5. Cancel queued requests on an older redirect, trap, context-switch cancel,
   translation rebind, or `fence.i`. Drain already issued responses, but do
   not publish a cancelled or stale-epoch line.

The measured dispatch opportunity is only five cycles to FE redirect capture
and six cycles to the first target I-cache request. That is shorter than even
the historical 16–25-cycle D-cache installer range, and the physical full-line
latency is not measured. A detached line fetch launched at dispatch therefore
cannot have a line ready for the first target demand; it could only help if
issued earlier from a reliable predictor or merged with an in-flight demand.

A lower-risk candidate is a small resume-line buffer populated from actual
architectural fetches. It could retain a recently used instruction line while
another context displaces the main I-cache, then satisfy a later resume after
the normal MMU has translated and permission-checked the request. This avoids
speculative translation and detached memory traffic, but does not help a
context's first-ever resume. The FE I-cache already has a TV-stage data mux
after SRAM read and tag comparison, which is a possible data insertion point;
however, correct capture needs a full line (the SRAM exposes only the selected
bank/word on a fetch), and hits must preserve the MMU fault, uncached, abort,
and refill semantics. In the noncoherent I-cache configuration, `fence.i`
issues `e_cache_inval`, which sweeps every set under a UCE request lock; the
retained valid bits can be cleared on that same invalidate event. No RTL
feasibility or timing claim is made yet.

The first useful prototype should instead replay the fixed shared privileged
prefix through a four-slot detached full-line queue and a demand-priority
I-cache installer. The prefix table may initially be software/M-mode seeded so
the experiment tests scheduling and installation rather than conflating them
with online learning. Count issued, response-complete, installed-before-demand,
late, consumed, unused, dropped, and demand-delayed lines. Ordinary demand must
always win, and a replay-disabled mode must preserve the exact architectural
path.

The fill path can use existing handshakes: the I-cache has one MSHR, and its
UCE returns four 128-bit data writes for each 512-bit line. At the accepted
architectural miss, latch the translated physical line address and logical
context ID. Assemble the four writes by `fill_index` in a staging register and
publish a shadow entry only when all four beats arrived and the miss was not
aborted. The current miss packet does not carry the logical ID, so add it to
the FE context-switch sideband and retain it with the miss. Clear shadow valid
bits when `e_cache_inval` is accepted. A small per-context quota of the first
few unique lines after resume is a better retention policy than ordinary LRU:
the timed-resume trace shows that the first three target lines are requested
again after warmup, while a temporary conflict stream added no further timing
cost because the first line was already missing.

The retained store remains a follow-on for immediate private lines and
five-to-eleven-cycle handoffs. Its complete-line assembly, logical-context
identity, lookup mux, and `fence.i` invalidation requirements remain valid, but
RL-049 shows that it is not the highest-value first Linux mechanism. Do not add
that storage until the shared-prefix lane is measured. The 97-cycle switch-only
floor and unchanged architectural fetch result remain gates for both designs.

### Rejected first slice and revised cache seam

The first direct-mode prototype reused the architectural I-cache request
stream, substituted the saved target NPC, and waited for that request to be
accepted before redirecting. It passed the directed correctness checks and
measured cold 554, target-warm 184, source-warm 227, and switch-only 99 cycles
against the then-recorded 490/172/226/97 controls, so it was reverted. A later
no-target-wiring run measured 552/183/226/97; therefore the prototype's
performance cost is not yet isolated against a contemporaneous baseline. The
six-cycle dispatch-to-demand trace still rules out serving the first target
fetch through a line installer launched at dispatch.

The packet `prefetch` bit is only a request-type seam. It builds and remains
inert while the controller drives it low; it does not provide independent
translation, response storage, or an I-cache line installer. Do not wire the
target to that bit through the normal FE slot. The existing I-cache UCE
configuration and response path cannot install its detached replies, so the
next checkpoint is architecture and interface validation for an independently
scheduled full-line lane, not target wiring to the packet seam.

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

### Stage A — establish the overlap window and arbitration contract

Completed by RL-049. The hash-verified physical demand sequence was scheduled
through trigger, translation, queue, response, and installer sensitivity. It
selects an early shared privileged prefix, at least four full-line slots, and
an independent demand-priority installer. Do not use an architectural FE
request as the replay request.

Keep the exact context setup, code layout, measured work, checks, and global
cycle bookkeeping. Report switch-to-first-use, target-request accept,
translation result, first/last response beat, tag publication, useful-before-
demand count, demand wait cycles, total cycles, and prefetch traffic.

### Stage B — independent shared-prefix correctness

Run the M-configured physical shared prefix through the detached full-line
lane. It must not delay demand, alter architectural translation/fault behavior,
or make a line executable without the ordinary MMU's permission check.
Invalidate queued and retained replay state on `fence.i`; drain already-issued
responses without publishing cancelled entries.

### Stage C — prefix and confidence sweep

Sweep prefix depth, queue depth, and correct versus stale shared histories.
Retain the existing data-hint rule that wrong predictions can cost more than
correct predictions save. Compare the trace-selected per-set-recency prefix
against shorter high-confidence prefixes and a replay-disabled control.

### Stage D — learned footprint and Linux replay

Only after the directed path is stable, learn the first unique instruction
lines after each resume and replay a high-confidence prefix while the target is
off CPU or at an early scheduler boundary. This stage is where the realistic
Linux results belong; it must not be inferred from the oracle controls.

## Acceptance

Simulation is the iteration path. Every RTL or benchmark change gets a clean
target rebuild and a traced directed run. A result is rejected if target
prefetch changes architectural redirect acceptance, delays any demand fetch,
or changes the 97-cycle switch-only control. Promote no application-speedup
claim until a matched no-prefetch control, exact target topology,
request/response/install evidence, and a routed/physical checkpoint exist.

The first claim we should seek is modest:

> A high-confidence instruction prefix can overlap part of a cold context
> resume and reduce time to first useful target execution.

Only a later Linux experiment can support a stronger end-to-end speedup claim.
