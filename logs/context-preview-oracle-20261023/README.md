This directory records the first directed test of a target-context data preview before the final handoff. It keeps the accepted simulator transcript, the local waveform, and the trace-counting procedure together so the measured benefit and its limits can be checked independently.

# Target-context preview oracle

The experiment starts context 1 at a fixed preview stub, returns to context 0 for 128 loop iterations, then resumes context 1 at four loads. Modes execute in repeat-major order: direct, empty preview, correct four-word hints, and stale four-word hints. Each run checks the target checksum and context ID.

| Mode | Repetition cycles | Median |
| --- | --- | ---: |
| Direct | 580, 517, 517 | 517 |
| Empty preview | 547, 540, 540 | 540 |
| Correct hints | 337, 337, 377 | 337 |
| Stale hints | 556, 548, 548 | 548 |

Run from this worktree after `make -C testing clean` completes:

```sh
make -C testing run-mt_context_preview_oracle_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=8
```

`accepted-summary.log` keeps the twelve timings and intact guest/host PASS markers in Git. The full `accepted-run.log`, `baseline-run.log`, and `accepted-dump.fst` remain local artifacts; the familiar GPIO finalization assertion follows host PASS, and the harness reports `VALID RUN: guest and host PASS`. The FST SHA-256 is `d73083dad39ad297ac2500696e407fb7b6bcd5bf8cb473ca210980be0c4ba7fd`; the full accepted transcript SHA-256 is `dcf31f568fb484d5fbaf6757fa8c836f99e0b69fa9f1bebf1576d65e3d5aef4f`. Stream the FST through `fst2vcd accepted-dump.fst | python3 count_prefetch_trace.py` from this directory to count 21 D-UCE prefetch accepts/issues, 42 response-beat assertions, and 14 D-cache side-buffer hit assertions across all modes. These aggregate signal edges do not assign every hit to a specific mode.

## Reproducibility notes

The isolated worktree initially lacked `riscv/bootrom/bootrom.none.riscv`, top-level BaseJump/HardFloat/black-parrot-subsystems submodules, and BlackParrot's three nested source submodules. The build failures were setup failures: copy the bootrom from the canonical checkout with matching SHA-256, initialize the top-level submodules with local-file transport enabled, then initialize and verify the three nested gitlinks before a clean rebuild.

The first complete test printed a long serial result line for every case. The simulator heartbeat interrupted the final `[BSG-PASS]` text, so the harness rejected that transcript even though guest execution and CORE PASS completed. The test now prints only cycles in documented order, and a clean rerun produced an intact marker; keep the provisional transcript separate from accepted evidence.
