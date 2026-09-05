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
