---
name: bp-benchmark-validation
description: Use when validating or interpreting BlackParrot benchmark results, especially to separate true hardware latency from benchmark-shape overhead and to choose the right benchmark for the claim being made.
---

This skill distinguishes measured context-switch throughput from architectural
handoff latency. It defines the counter, topology, and evidence needed to compare
results without mistaking a different benchmark shape for a hardware improvement.

# BlackParrot Benchmark Validation

## Core Principle

A benchmark result is only meaningful relative to what the benchmark shape actually charges for.

## For Ctxtsw Work

For nonresident measurements on branches that provide it, use the core-wide
physical-cycle CSR `0xCC0`. Do not use `rdcycle`/`mcycle`: virtual context
restore can roll those counters backward. Compile FPGA nonresident images for
the RTL's two physical threads and four logical contexts; otherwise context 2
is accidentally measured as resident.

If a simulator benchmark cannot use `0xCC0`, bracket both the matched resident
and nonresident timed loops with host signal writes and verify that
`CTXTSW_GLOBAL_MARKER` timestamps appear in `run.log`. A comment saying to use
global markers is not evidence that the program actually emitted them. For
dirty-state benchmarks, subtract the matched resident loop first, then compare
that increment with the clean nonresident increment; instruction-heavy state
checks belong to both loops and are not context-switch overhead.

Use the benchmarks for different questions:

- `mt_ctxtsw_nonresident_overhead_benchmark`
  - current matched resident/nonresident rings using physical CSR `0xCC0`
  - primary performance regression gate for the accepted SRAM-backed topology
- `mt_ctxtsw_roundtrip_benchmark`
  - focused resident round-trip workload; confirm its counter and topology
    before comparison with the physical-cycle nonresident benchmark
- `mt_ctxtsw_pure_ring_stress_test`
  - correctness under dense switching, not itself a measured speedup

See [the maintained test guide](../../testing/README.md) for current commands.
Use a prior simulator run with the same benchmark and configuration for simulator
regression comparisons; FPGA and simulator baseline values are not interchangeable.

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
