---
name: bp-cosim-triage
description: Use when a BlackParrot cosim flow fails or hangs and the first task is to localize whether the problem is in rebuild infrastructure, host/NBF loading, unfreeze/startup, or runtime execution.
---

# BlackParrot Cosim Triage

Use this skill when a cosim run does not complete and you need localization before changing RTL.

## Triage Order

1. Decide whether the failure is:
   - build/rebuild failure
   - host bring-up failure
   - NBF generation/load failure
   - post-unfreeze startup failure
   - runtime execution hang/crash
2. Avoid changing RTL until the failing stage is known.

## Localizing Stages

- if `make clean` changes behavior, suspect source lists or stale build artifacts
- if reset/host CSRs fail, suspect host-shell or wrapper issues
- if NBF load stalls, instrument sparse progress through the NBF stream
- if NBF load completes but `minstret` stays zero after unfreeze, suspect startup-side RTL control
- if output begins but workload never completes, suspect runtime datapath/control issues

## Instrumentation Rules

- add temporary prints only at stage boundaries
- prefer sparse counters over per-event spam
- remove instrumentation once the failing stage is understood

Good examples:

- `beginning nbf load`
- every 256th NBF line
- final fence lines
- `finished nbf load`
- first forward packet after unfreeze

## Useful BlackParrot-Specific Checks

- compare clean baseline branch versus current branch in the same cosim flow
- separate host-side fixes from branch RTL fixes
- if a control signal can behave without a valid retiring instruction, inspect reset and valid gating first

## Exit Criteria

Triage is complete when you can state:

- the last confirmed good stage
- the first bad stage
- the smallest plausible code region to inspect next

