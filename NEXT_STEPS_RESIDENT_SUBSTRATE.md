# Next Steps: Resident Substrate

## Goal

Establish whether the current implementation is strong enough to keep scaling
toward Banyan-style threading before committing to a threading-first refactor.

The immediate objective is not Linux bring-up or cache-backed contexts. The
immediate objective is to finish and validate the resident-context substrate so
that later design decisions are driven by evidence rather than style
preferences.

## Current Baseline

The current repo has already established:

- fast resident context handoff
- verified `7 cycles/switch` on the warm fast path
- restore-path correctness fixes for:
  - target-thread `translation_en`
  - per-thread ASID save/restore wiring
- dense pure-switch robustness via:
  - `mt_ctxtsw_unrolled_ring_stress`

What is not yet established:

- larger context counts at Banyan-like scale
- multicontext trap/exception behavior
- Linux-facing thread/control semantics
- cache-backed context residency

## Phase 1: Lock Down The Current Model

Write down the current resident-thread model clearly and keep it stable while
the next validation steps are executed.

The model should explicitly define:

- what per-context state exists today
  - integer register file
  - floating-point register file
  - CSR state
  - FE thread identity / predictor state
  - saved NPC / privilege / translation / ASID state
- what software-visible operations exist today
  - `ctxtsw` via CSR `0x081`
  - thread NPC seeding via CSR `0x082`
  - remote register seeding via CSR `0x083`
- what the current guarantees are
  - fast resident handoff
  - isolation at the current tested scope
- what remains intentionally undefined or unimplemented

This step is complete when the current design can be explained as a coherent
resident-thread model rather than as a collection of benchmark mechanisms.

## Phase 2: Expand Resident-Context Validation

The next tests should stress the current design, not a refactored one.

Priority coverage gaps:

- more contexts than the smallest proof-point cases
- repeated switching across more privilege-mode combinations
- repeated switching across more address-space combinations
- exception and trap behavior after a context switch
- timer/interrupt behavior after a context switch

The main question is:

> does the current design remain correct and understandable as the exercised
> multicontext cases become richer?

## Phase 3: Make The Control Model Explicit

Even if the RTL remains unchanged for a while, the software-visible thread model
should be described explicitly.

Define:

- how a context is created or seeded
- when it is considered dormant, runnable, or currently executing
- how another context may modify its architectural state
- what a committed `ctxtsw` means architecturally
- what the expected resume point is after a switch

If this model is awkward to explain cleanly, that is evidence that a later
threading-first refactor may be worthwhile.

## Phase 4: Push Context Scale Modestly

Before discussing cache-backed contexts, test how far the resident design can go
without changing the architecture qualitatively.

Questions to answer:

- can the current design stand up a noticeably larger number of contexts?
- do the current parameterization and tests scale cleanly?
- does debug and reasoning complexity remain manageable?

This phase does not need to jump immediately to the final Banyan target. The
goal is to determine whether the current implementation still scales naturally
once it is pushed beyond the smallest validated cases.

## Phase 5: Revisit The Refactor Question

After the steps above, decide between:

- extending the current design further
- or doing a focused threading-first refactor

That decision should be made only after the resident substrate has been pushed
far enough to reveal where the current structure does or does not hold up.

## Validation Checklist

### Correctness

- context isolation across larger context counts
- translation/ASID correctness under repeated switching
- privilege-mode switching correctness
- FP/int/CSR integrity after long switch sequences

### Control Semantics

- clear meaning of dormant/resident/running
- exact architectural meaning of `ctxtsw`
- exact semantics of remote seeding/manipulation

### Robustness

- repeated ring switching
- dense back-to-back switching
- larger multicontext switching patterns
- fault/trap behavior after resume

### Scalability

- parameterized context-count experiments
- resource-growth awareness
- assessment of debug complexity as scale increases

## Criteria For A Refactor

A threading-first refactor becomes justified if one or more of the following is
true:

- new thread-control features feel bolted on rather than natural
- scaling the context count requires too much scattered plumbing
- software-visible semantics become hard to explain coherently
- Linux integration would require ad hoc interfaces rather than a clear model
- cache-backed contexts cannot be layered cleanly on top of the resident design

If these conditions do not appear yet, the current design should continue to be
extended incrementally.

## Recommendation

The next milestone should be:

> prove whether the current resident design is a solid Banyan substrate by
> expanding validation and making the control model explicit.

Linux bring-up and cache-backed context storage should be treated as subsequent
phases, not as substitutes for finishing the resident substrate first.
