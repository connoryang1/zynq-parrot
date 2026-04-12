# Restore Working State

This repository currently has a known-good, fully committed restore point at:

- `zynq-parrot` commit: `7385642` (`add multithreading validation programs from testing fork`)
- `import/black-parrot` submodule commit: `c39ee12b73528789f8ed1e61848597d0d1ce537d`

That state has been verified with:

- `cosim/black-parrot-example/verilator`: `hello_world` passes
- `testing/run-mt_regfile_test`: passes
- `testing/run-mt_benchmark`: passes, reporting `0x12` minimum round-trip cycles

## Safe Restore

Use this when you want to get back to the known-good committed state without forcibly deleting local changes:

```bash
git checkout 7385642
git submodule sync --recursive
git submodule update --init --recursive
```

This restores:

- the top-level `zynq-parrot` tree to commit `7385642`
- `import/black-parrot` to the submodule commit recorded by that top-level commit
- all nested submodules recursively

## Hard Restore

Use this only if local changes or dirty submodules are causing problems and you want to force everything back to the known-good state.

This discards uncommitted changes in the top-level repo and in submodules.

```bash
git reset --hard 7385642
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

- top-level `HEAD`: `7385642`
- `import/black-parrot`: `c39ee12b73528789f8ed1e61848597d0d1ce537d`

## Re-run Smoke Tests

From the repo root:

```bash
make -C cosim/black-parrot-example/verilator build
make -C cosim/black-parrot-example/verilator run

make -C testing all
make -C testing run-mt_regfile_test
make -C testing run-mt_benchmark
```

Expected pass indicators:

- `Hello World!`
- `CORE PASS`
- `BSG PASS`
- `Min round-trip: 0x0000000000000012 cycles`

## Notes

- The top-level repo may contain an untracked `.codex/` directory. That is not part of the restore state.
- The `testing` source tree used during the port still has two uncommitted experimental BlackParrot edits in its own separate checkout. Those are not part of this repo's known-good state.
