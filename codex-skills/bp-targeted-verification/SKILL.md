---
name: bp-targeted-verification
description: Use when choosing or running verification for BlackParrot or zynq-parrot changes, especially to match the test scope to RTL, cosim, benchmark, or build-system modifications.
---

# BlackParrot Targeted Verification

Use this skill to choose the smallest verification set that still gives credible evidence.

## Core Rule

Verification should match the changed surface.

## Default Mapping

- `bp_be` / `bp_fe` / `bp_common` RTL changes:
  - run the most relevant smoke test
  - rerun the benchmark or workload that exercises the modified path
- build-system or collateral changes:
  - do one clean rebuild of the affected flow
  - rerun one previously known-good test in that flow
- host-side cosim changes:
  - rerun the exact failing cosim command
  - distinguish load-time, unfreeze-time, and runtime behavior
- documentation-only changes:
  - no code test required unless docs claim a new verified result

## Recommended Verification Ladder

1. confirm current baseline if the area is unstable
2. make one change
3. run the narrowest relevant smoke test
4. if that passes, run the higher-value benchmark only if it exercises the same path

## BlackParrot-Specific Heuristics

- after major RTL churn, run `make -j24 prep_lite`
- before trusting waveform/debug conclusions, do a clean rebuild of the specific cosim flow
- for ctxtsw work, prefer:
  - `mt_ctxtsw_smoke_test`
  - `mt_ctxtsw_live_regs_test`
  - controlled gap tests around the known pass/fail boundary
  - `mt_ctxtsw_microbench`
  - `mt_ctxtsw_partial_unroll_benchmark`
  - `mt_ctxtsw_unrolled_ring_stress`

## Ctxtsw Verification Ladder

For ctxtsw forwarding repair:

1. run `mt_ctxtsw_smoke_test`
2. run `mt_ctxtsw_live_regs_test`
3. run wide-to-narrow gap tests such as `gap16`, `gap14`, `gap13`, `gap8`, `gap1`
4. run `mt_ctxtsw_partial_unroll_benchmark`
5. run `mt_ctxtsw_microbench_trace` and `mt_ctxtsw_microbench_barrier`
6. run dense `mt_ctxtsw_microbench`

Use `/tmp/run_tests.sh` only as a quick sweep after a focused failing case has
already been fixed. It uses a hard timeout and compresses logs, so it is not
enough for root-cause analysis by itself.

## Clean Rebuild Triggers

Do a clean rebuild when:

- stale source lists may matter
- switching to waveform work
- changing host/NBF/cosim infrastructure
- preparing a review-ready branch
- many incremental edits have accumulated without a from-scratch check

## Reporting

When done, report:

- command run
- pass/fail
- one-line meaning of the result
