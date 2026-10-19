---
name: bp-memory-interleaving-app
description: Design, implement, validate, and document application-level BlackParrot memory-interleaving benchmarks with matched demand, software, hardware-context, and ideal-batch controls. Use for Nano-coroutine-style lookup, dependent graph, or database/index workloads; do not use for protected-RPC isolation benchmarks.
---

# BlackParrot memory-interleaving applications

Use this workflow to determine whether hardware contexts expose useful independent memory work, not merely whether context switching or prefetch instructions function.

## Experimental contract

- State the claim before changing code. Distinguish latency hiding, request capacity, scheduling overhead, and application throughput.
- Develop on an isolated branch/worktree based on the accepted memory-interleaving checkpoint. Keep protected RPC, new RTL optimizations, and application code in separate PRs unless one cannot function without the other.
- Prefer an application-shaped lookup with dependent misses and multiple independent requests. For the Nano-coroutine comparison, reproduce the algorithmic structure—independent binary searches over one sorted index—not the x86/C++ implementation.
- Keep every compared schedule in one executable behind a runtime selector. Use the same data, query order, code layout, topology, and correctness oracle.

Include the controls needed for the claim:

- serial demand;
- software state-machine or coroutine interleaving;
- hardware worker `prefetch; switch; consume` scheduling;
- matched ideal batching subject to the same request capacity and arbitration;
- switch-only when decomposing hardware-worker overhead.

Before each measured interval, seed the same contexts, clear the same result storage, drain outstanding memory traffic, warm the common instruction path with a separate dataset, and leave the measured data cold. Put explicit begin/end markers immediately around the operation. Keep correctness checks outside every timed interval unless every mode performs identical timed checks.

Use physical-cycle CSR `0xCC0` where available. Record total cycles and, from `TRACE=1`, first/last request acceptance, first/last response, and first/last consuming load. For the hardware worker, report whether all intended requests were accepted before the first response; a lower concurrency ceiling than the batch is a real implementation gap even when totals are similar.

## Iteration and acceptance

- Use `bp-targeted-verification` for test selection and `bp-parallel-safe-runs` before any concurrent or background execution.
- Iterate in simulation. Reuse a matching Verilator model for software-only edits, but clean-rebuild before trace-dependent analysis and review readiness.
- Run the relevant existing dependent-stream regression after shared harness changes.
- Reserve routed FPGA implementation and physical execution for the final accepted checkpoint or an RTL milestone that changes area/timing.
- Do not turn cross-program cycle differences into a speedup. Report the exact benchmark, topology, memory model/platform, and what the result validates.

For a committed, clean Nano lookup checkpoint, launch the full serialized matrix
without blocking the interactive development flow:

```bash
codex-skills/bp-memory-interleaving-app/scripts/launch_nano_lookup_matrix.sh \
  logs/nano-lookup-$(date -u +%Y%m%dT%H%M%SZ)
```

The launcher returns immediately. Its worker holds a simulator-directory lock,
requires a clean worktree and local boot ROM, runs modes 0 through 4 serially,
copies each closed waveform before the next mode, hashes the artifacts, and
performs marker-scoped trace analysis. Run it only in an isolated worktree; do
not edit that worktree or start an unwrapped simulator run while it is active.

## PR and evidence record

Keep an application experiment document on the branch with its purpose, source workload, modes, matched-state contract, commands, results, trace interpretation, rejected measurements, and remaining gates. Update it and the PR body whenever a material benchmark, scope decision, or accepted/rejected result changes.

Record accepted conclusions or scope corrections in `RESEARCH_LEDGER.md`; add only major milestones to `WORK_LOG.md`. Link retained logs rather than copying raw transcripts into documentation.
