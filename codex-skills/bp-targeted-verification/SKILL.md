---
name: bp-targeted-verification
description: Use when choosing or running verification for BlackParrot or zynq-parrot changes, especially to match the test scope to RTL, cosim, benchmark, or build-system modifications.
---

This skill chooses the smallest BlackParrot verification set that still gives
credible evidence. It prevents stale artifacts and incorrect hardware
topologies from turning a fast check into a misleading result.

# BlackParrot Targeted Verification

## Core Rule

Verification should match the changed surface.

## Default Mapping

- `bp_be` / `bp_fe` / `bp_common` RTL changes:
  - run the most relevant smoke test
  - rerun the benchmark or workload that exercises the modified path
  - after area-significant storage, port, or datapath changes, launch the routed FPGA fit gate
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

## Iteration Cost Model

- Compile and run one test with `make -C testing run-<test> TRACE=1`; the branch's testing
  harness compiles that source directly and avoids rebuilding every SDK test.
- With parallel Make, finish `make -C testing clean` first and invoke the
  `run-<test>` goal separately with `-j`; never make `clean` and `run` concurrent
  goals because cleanup can delete the ELF or simulator collateral being consumed.
- When a current harness drives a historical RTL worktree, pass that worktree's
  `ZP_DIR` explicitly, force-rebuild the single test ELF, and disassemble the
  relevant CSR/instruction before running. A shared ignored `riscv/` symlink can
  otherwise make an incompatible prebuilt ELF appear up to date.
- Match both the physical-thread and logical-context compile-time dimensions to
  the historical RTL stage; later tests may encode fields that an earlier CSR
  decoder does not yet implement. Before a direct historical-model run, move
  `prog.riscv`, `prog.mem`, and `prog.nbf` aside, regenerate them, and require
  the selected ELF and copied `prog.riscv` hashes to match. Archive and hash the
  regenerated `prog.nbf` with the log and waveform, and require the guest's
  test-specific PASS marker; a generic `CORE PASS` is not sufficient evidence
  that the intended NBF ran.
- For an expected historical-model stall, confirm the printed simulator command
  actually carries the native target-runtime argument. Backport the bounded
  runner support as uncommitted diagnostic infrastructure when the old Makefile
  silently ignores it; do not rely on the variable name alone.
- Copy every closed FST to a revision/test-specific immutable artifact and hash
  it before starting another trace in the same simulator directory.
- Do not use `make -C import/black-parrot-sdk build.bp-tests -B` for ordinary iteration. It is
  the old coarse-grained all-tests path.
- Reuse one Verilator hardware model across software-only test changes.
- Run `make -C testing rebuild-sim` only after RTL, configuration, wrapper, or source-list
  changes. Treat the model rebuild as all-or-nothing because Verilator makes global scheduling
  decisions and incremental reuse is not a reliable correctness gate.
- Do not rewrite upstream Makefiles merely to force fine-grained Verilator compilation unless
  measurements show a maintainable, reliable win.

## Current Test Selection

Use [the maintained test guide](../../testing/README.md) for the accepted
resident smoke, translated nonresident handoff, and global-cycle benchmark.
Confirm that each selected source and harness target exists before launching;
removed historical tests must not be run from leftover prebuilt ELFs.
Do not depend on temporary scripts outside the repository.

For a clean compile, set `VERILATOR_BUILD_JOBS` to the available CPU/memory
budget and inspect the actual nested compiler command. A parallel outer Make
can lose its jobserver in this harness and unexpectedly serialize the model
build. Serial outer Make with explicit inner build jobs avoids that observed
failure; this does not authorize concurrent simulator runs.

For SRAM-backed nonresident handoff work, explicitly elaborate fewer physical
slots than logical contexts, normally:

```bash
make -C testing run-mt_umode_nonresident_handoff_test \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1
```

The test is invalid as nonresident evidence when `NUM_CONTEXTS <= NUM_THREADS`.
Require its test-specific `[BSG-PASS]` marker and `CORE PASS`; a native trace or
target-runtime limit is a failure even if host teardown later prints `BSG PASS`.

## Clean Rebuild Triggers

Do a clean rebuild when:

- stale source lists may matter
- switching to waveform work
- changing host/NBF/cosim infrastructure
- preparing a review-ready branch
- many incremental edits have accumulated without a from-scratch check

For the Zynq Verilator directories, invoke `make clean` and `make build` as two
separate commands. Do not request both goals in one Make invocation: Make may
resolve generated collateral such as `bsg_bootrom.sv` before `clean` removes it,
then fail to regenerate it during `build`.

## Reporting

When done, report:

- command run
- pass/fail
- one-line meaning of the result

Use `bp-fpga-synthesis` at milestone checkpoints; do not put full Vivado implementation in the
per-edit foreground loop.
