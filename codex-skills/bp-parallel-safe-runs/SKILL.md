---
name: bp-parallel-safe-runs
description: Use when deciding which BlackParrot or zynq-parrot reads, builds, tests, or analysis tasks can run in parallel without corrupting shared outputs or invalidating measurements.
---

# BlackParrot Parallel-Safe Runs

Use this skill when parallelism can speed up work, but shared build artifacts or runtime files may conflict.

## Principle

Parallelize only tasks with disjoint write sets or read-only work.

## Usually Safe In Parallel

- file reads
- `rg`, `sed`, `git diff`, `git status`
- independent analysis commands
- separate test commands that write to different output directories

## Usually Not Safe In Parallel

- multiple runs that share the same `prog.nbf`, `prog.mem`, `run.log`, or simulator working directory
- concurrent rebuilds in the same `verilator` directory
- two tests that both regenerate the same collateral
- benchmarking runs whose outputs or timing can interfere

## BlackParrot-Specific Cautions

- `cosim/.../verilator` directories are usually single-writer workspaces
- benchmark runs against shared `prog.*` collateral should be serialized unless isolated into separate directories
- do not run a clean rebuild in parallel with another command using the same build tree

## Recommended Pattern

1. parallelize context gathering first
2. parallelize non-conflicting static checks next
3. serialize runtime tests unless the working directories are isolated

## Before Parallelizing a Command

Ask:

- does it write build artifacts?
- does it regenerate shared collateral?
- does it overwrite logs?
- could it perturb the timing/result of another run?

If yes to any of those, serialize or isolate it first.

## Reporting

When using parallelism, say briefly:

- what was parallelized
- why it was safe
- what remained serialized

