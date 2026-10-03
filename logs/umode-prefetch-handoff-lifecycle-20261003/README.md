# U-mode Sv39 repeated prefetch/handoff lifecycle

This experiment adds translated execution and 4 KiB data mappings to the
six-launch lifecycle test. It isolates whether U-mode Sv39 state is sufficient
to reproduce the fifth-launch stall seen by the physical Linux request
workload.

Each launch sweeps 16 explicitly mapped eviction pages, then two resident
contexts traverse four private 4 KiB request pages apiece. Each context issues
256 `prefetch.r; switch; load` sequences. The guest verifies both per-launch
checksums, both loop completions, preserved address registers, the selected
context, and every unexpected trap's `mcause`, `mepc`, and `mtval`.

The exact trace-enabled command was:

```sh
BSG_TRACE_TIMEOUT_S=1200 VERILATOR_BUILD_JOBS=8 \
  make -C testing run-mt_umode_prefetch_handoff_lifecycle_test \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 TRACE=1
```

The guest, core, and host all pass. The maintained harness accepts the known
DPI-GPIO final-block assertion only after those three completion conditions.

## Trace result

The source has exactly 512 logical hints per launch. Cold translations and
transient D-cache conflicts replay the memory pipeline, so the trace separately
reports translation-stage and D-cache request attempts. Those attempts are not
additional logical hints.

| Epoch | Logical hints | Translation attempts | Translation-miss attempts | D-cache request attempts | Detached completions | Useful side-buffer hits | UCE drops | Residual buffer/UCE state |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 512 | 1,348 | 12 | 1,170 | 334 | 334 | 0 | 0 / 0 |
| 2 | 512 | 1,351 | 13 | 1,171 | 334 | 334 | 0 | 0 / 0 |
| 3 | 512 | 1,351 | 13 | 1,171 | 334 | 334 | 0 | 0 / 0 |
| 4 | 512 | 1,351 | 13 | 1,171 | 334 | 334 | 0 | 0 / 0 |
| 5 | 512 | 1,351 | 13 | 1,171 | 334 | 334 | 0 | 0 / 0 |
| 6 | 512 | 1,351 | 13 | 1,171 | 334 | 334 | 0 | 0 / 0 |

Each completed detached request returns two 8-byte beats, giving 4,008 beats
for 2,004 useful hits over the run. Exactly 65.23% of logical hints complete in
the detached buffer each epoch. The other 178 hints per epoch either lack a
usable translation at the relevant attempt or are suppressed by current cache
state; the selected trace does not assign every suppressed hint to one of those
causes. Translation-miss attempts touch all eight request virtual pages.

Maximum side-buffer, UCE-valid, and UCE-sent occupancy is one entry in every
epoch. All three return to zero at every launch boundary. Epochs 2--6 have
identical behavior, providing no evidence of accumulating translated state.

Sv39 translation alone therefore does not reproduce the physical stall. It
does expose a separate efficiency result: DTLB/cache pressure means only about
two thirds of hints reach a useful detached completion in this schedule. The
next isolation step is the full L2 simulator path, followed by the physical
DDR/Linux environment if the full model also drains cleanly.

`extract.py` discards one boot-time instruction that happens to match the hint
encoding, splits the remaining attempts at the five long inter-launch gaps,
and distinguishes fixed program-level hint count from pipeline replay attempts.
It fails if an epoch records a UCE drop, mismatched response/hit count, or
residual side-buffer/UCE state.

The raw 259 MiB FST is retained locally as `lifecycle.fst`, rather than
committed. Its SHA-256 is
`c3000f8be02de6ad08b7ab1661450384f49e543dd5bbf5c01e1102228d1d75d3`.
The exact guest ELF SHA-256 is
`dca98161e2530a78ee2264eaaab0d6b66b52554b5f0c4d871d105930430eafa3`.
