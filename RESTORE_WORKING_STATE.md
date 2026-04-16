# Restore Working State

This repository currently has a known-good, fully committed restore point at:

- `zynq-parrot` commit: `4a02afe` (`tighten ctxtsw microbenchmark to immediate csr writes`)
- `import/black-parrot` submodule commit: `3affb651`

That state has been verified with:

- `cosim/black-parrot-example/verilator`: `hello_world` passes
- `testing/run-mt_regfile_test`: passes
- `testing/run-mt_benchmark`: passes
- `testing/run-mt_ctxtsw_microbench`: passes, reporting `0x0e` warm round-trip cycles and `0x07` warm single-switch estimate

## Safe Restore

Use this when you want to get back to the known-good committed state without forcibly deleting local changes:

```bash
git checkout 4a02afe
git submodule sync --recursive
git submodule update --init --recursive
```

This restores:

- the top-level `zynq-parrot` tree to commit `4a02afe`
- `import/black-parrot` to the submodule commit recorded by that top-level commit
- all nested submodules recursively

## Hard Restore

Use this only if local changes or dirty submodules are causing problems and you want to force everything back to the known-good state.

This discards uncommitted changes in the top-level repo and in submodules.

```bash
git reset --hard 4a02afe
git submodule sync --recursive
git submodule foreach --recursive git reset --hard
git submodule update --init --recursive --force
```

## Verify The Restore

Check that the expected commits are present:

```bash
git rev-parse HEAD
git submodule status --recursive
```

Expected key results:

- top-level `HEAD`: `4a02afe`
- `import/black-parrot`: `3affb651`

## Re-run Smoke Tests

From the repo root:

```bash
make -C cosim/black-parrot-example/verilator build
make -C cosim/black-parrot-example/verilator run

make -C testing all
make -C testing run-mt_regfile_test
make -C testing run-mt_benchmark
make -C testing run-mt_ctxtsw_microbench
```

Expected pass indicators:

- `Hello World!`
- `CORE PASS`
- `BSG PASS`
- `Warm min round-trip: 0x000000000000000e cycles`
- `Warm min single-switch estimate: 0x0000000000000007 cycles`

## 7-Cycle Result

The `0x07` single-switch result is a microarchitectural context-switch measurement, not a blanket claim about every multithreaded program.

What it means:

- The number comes from `testing/run-mt_ctxtsw_microbench`
- The benchmark measures a warm `T0 -> T1 -> T0` round trip
- The switched-to thread is pre-seeded and immediately switches back with a single `csrwi 0x081, 0`
- The reported single-switch value is `warm_round_trip / 2`

What makes that number achievable in this repo:

- `import/black-parrot` commit `3affb651` allows a forced ctxtsw redirect to escape the shared FE icache `e_miss/e_recover` state instead of waiting behind an old-thread miss
- `testing/mt_ctxtsw_microbench.c` uses immediate CSR writes on both sides, so the benchmark is measuring the hardware switch path instead of extra worker-thread instructions

When you should not expect 7 cycles:

- If the switched-to thread executes extra instructions before switching back
- If the benchmark includes setup, printing, loop bookkeeping, or host I/O in the measured window
- If you use a broader benchmark like `mt_benchmark` instead of the stripped microbenchmark
- If the resumed thread takes an icache miss after the switch instead of hitting on its first instructions
- If you are measuring end-to-end workload latency rather than the isolated ctxtsw path
- If future RTL changes alter FE redirect, icache, or CSR/ctxtsw behavior

## Notes

- The top-level repo may contain an untracked `.codex/` directory. That is not part of the restore state.
- The `testing` source tree used during the port still has two uncommitted experimental BlackParrot edits in its own separate checkout. Those are not part of this repo's known-good state.
