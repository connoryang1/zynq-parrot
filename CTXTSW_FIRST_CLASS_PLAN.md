# First-Class `ctxtsw` Implementation Plan

## Goal

Redesign `ctxtsw` from a committed CSR-managed switch event into a first-class hardware primitive with a dedicated fast path, while preserving precise architectural ownership and without slowing normal non-`ctxtsw` execution.

The current branch is a correct baseline:

- per-thread architectural state exists
- FE and MMU state restore correctly
- the committed switch path measures 7 cycles/switch on the warm path

The plan below is about reducing latency beyond that point.

## Design Target

The immediate target should be a clean 3-cycle switch path that can later be compressed toward 2 cycles if the timing and control path allow it.

That target should be interpreted as:

1. detect `ctxtsw` early
2. prepare target-thread restart state through a dedicated ctxtsw path
3. restart FE on the target thread

Commit should remain the authority for final architectural ownership, even if FE restart work begins earlier.

## Core Design Principles

- keep the normal BE/FE path unchanged for non-`ctxtsw` instructions
- give `ctxtsw` its own fast path rather than stretching the generic CSR path
- separate "prepare target-thread restart" from "architecturally finalize the switch"
- make target-thread restart state cheap to read and explicit to route
- add rollback rules for speculative or early restart work

## Required Architectural Changes

### 1. Dedicated `ctxtsw` op classification

Today, software exposes switching through `CSR 0x081`, and the BE ultimately recognizes the switch at commit through the system/CSR path. A first-class design should still preserve the software-visible interface initially, but internally the machine should classify `ctxtsw` as its own operation as early as possible.

The natural first place to do that is in the scheduler / decode path. Once identified, the operation should carry:

- `is_ctxtsw`
- `target_tid`
- enough metadata to suppress younger issue behind it

This is the first step toward reducing latency, because it removes the dependency on treating the switch as "just another CSR write" all the way through the backend.

### 2. Dedicated target-context read path

The current branch stores the per-thread restart state in `bp_be_top`:

- saved next PC
- privilege mode
- translation enable
- ASID

That state should be reorganized conceptually as a fast target-context read bundle:

- `target_npc`
- `target_priv`
- `target_translation_en`
- `target_asid`
- target thread identity

The actual storage can remain where it is, but the read path should become explicit and low-latency. The goal is that once `target_tid` is known, the machine can fetch the entire restart bundle immediately rather than reconstructing it later through the committed handoff path.

### 3. Dedicated FE ctxtsw restart interface

The current branch reuses existing FE control plumbing and currently carries target thread identity through `branch_metadata_fwd`. That was a practical integration choice for the current implementation, but it is not the right long-term structure for a fast ctxtsw path.

A first-class design should give FE an explicit ctxtsw restart interface carrying:

- valid bit
- target thread id
- target PC
- target privilege mode
- target translation enable
- target ASID

That interface should be consumed directly by FE restart logic instead of being packed into generic redirect metadata.

### 4. Explicit rollback / recovery rules

The current committed switch path is simple because FE does not begin acting as the target thread until commit. A lower-latency path becomes more speculative, so it needs explicit rules for when early-prepared target-thread work must be canceled.

That means defining what happens if:

- an older instruction faults
- an older redirect wins
- the `ctxtsw` itself is squashed before architectural completion

The clean version is:

- FE may begin preparing or even restarting the target-thread path early
- BE architectural ownership does not become final until commit
- recovery restores the old-thread FE view if commit never validates the switch

## Proposed 3-Cycle Target Path

### Cycle 0: detect

At ISD or the earliest practical backend classification point:

- detect `ctxtsw`
- extract `target_tid`
- block or suppress younger issue behind it
- read target-thread restart state

Outputs needed by the end of this cycle:

- target PC
- target privilege mode
- target translation enable
- target ASID
- target FE thread identity

### Cycle 1: prepare FE restart

Drive the dedicated FE ctxtsw path:

- FE thread id := target thread
- FE restart PC := target PC
- FE shadow privilege / translation / ASID := target values
- icache restart / escape logic asserted if needed

At the same time, BE tracks that a ctxtsw handoff is in flight but not yet architecturally final.

### Cycle 2: target fetch begins

FE starts fetching as the target thread.

Meanwhile:

- older instructions still retain priority if they fault or redirect
- architectural ownership only becomes final once the BE validates the switch

This is the right 3-cycle structure because it already contains the ingredients needed for a later 2-cycle design:

- dedicated ctxtsw classification
- dedicated target-context read path
- dedicated FE restart path

## Path to 2 Cycles

A later 2-cycle design would most likely come from collapsing one stage of the 3-cycle design rather than inventing a new mechanism.

The most plausible path is:

1. detect `ctxtsw` and read target restart state in the same cycle
2. restart FE on the target thread in the next cycle

That only becomes possible if:

- target restart state is available with very low latency
- FE restart input is direct and not queued behind generic control machinery
- the rollback model is already explicit

That is why the 3-cycle design should be built around explicit ctxtsw-specific structures instead of generic CSR reuse.

## Why Not Optimize the Existing Path Incrementally

There are incremental opportunities in the current design, such as earlier detection and earlier context selection, but those will eventually run into the limits of the current structure:

- ctxtsw is still shaped like a system/CSR operation
- target-thread identity still rides through reused redirect metadata
- FE restart is still integrated through generic command paths

Those are acceptable choices for the committed 7-cycle design, but they are not the cleanest starting point for a true low-latency primitive. If the goal is to pursue branch-like restart behavior, a dedicated path is the cleaner long-term direction.

## Recommended Implementation Order

1. Add early `ctxtsw` classification in the scheduler / decode path.
2. Refactor target-thread restart state into an explicit fast-read bundle.
3. Add a dedicated FE ctxtsw restart interface.
4. Move target thread identity off the reused `branch_metadata_fwd` path.
5. Define rollback and recovery rules for early restart work.
6. Implement and measure a 3-cycle path.
7. Only then evaluate whether the remaining latency is small enough to justify a 2-cycle compression pass.

## Success Criteria

The redesign should be considered successful if it achieves all of the following:

- non-`ctxtsw` execution paths are not slowed down
- FE restart under the target thread remains correct across privilege / translation / ASID changes
- rollback from an uncommitted or eclipsed `ctxtsw` is well-defined
- the new path materially reduces warm switch latency below the current 7-cycle baseline

If those hold, the resulting design would be a better substrate for pushing toward truly low-latency hardware-thread handoff than continued optimization of the current committed CSR-based path.
