---
name: bp-benchmark-validation
description: Use when validating or interpreting BlackParrot benchmark results, especially to separate true hardware latency from benchmark-shape overhead and to choose the right benchmark for the claim being made.
---

# BlackParrot Benchmark Validation

Use this skill when a result needs interpretation, not just execution.

## Core Principle

A benchmark result is only meaningful relative to what the benchmark shape actually charges for.

## For Ctxtsw Work

For nonresident measurements on branches that provide it, use the core-wide
physical-cycle CSR `0xCC0`. Do not use `rdcycle`/`mcycle`: virtual context
restore can roll those counters backward. Compile FPGA nonresident images for
the RTL's two physical threads and four logical contexts; otherwise context 2
is accidentally measured as resident.

Use the benchmarks for different questions:

- `mt_ctxtsw_microbench`
  - fast sanity check
  - warm round-trip estimate
- `mt_ctxtsw_partial_unroll_benchmark`
  - better steady-state estimate with reduced loop-overhead distortion
- `mt_ctxtsw_unrolled_ring_stress`
  - correctness and robustness under dense switching

## Interpretation Rules

- do not claim a hardware speedup if only the measurement shape changed
- distinguish:
  - warm round-trip
  - inferred single-switch cost
  - steady-state amortized measurement
- if two benchmarks differ, explain the structural reason
- keep physical-cycle ring spacing distinct from the waveform-derived interval
  from architectural context-switch redirect to first useful target work
- for matched resident/nonresident rings, report raw resident spacing, raw
  nonresident spacing, and nonresident-minus-resident incremental cost

## Serializing Test Policy

Serialize runs when they share:

- the same collateral
- the same simulator working directory
- the same output files

Do not trust benchmark conclusions from overlapping runs in the same workspace.

## Reporting

Always report:

- benchmark name
- exact observed result
- what it actually validates
