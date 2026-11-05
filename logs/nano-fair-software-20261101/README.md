This simulator-only experiment asks whether the historical Nano software batch
was an unfairly weak baseline. It compares stronger compile-time batches and
coroutine schedulers against the unchanged hardware worker, and preserves the
exact transcripts and qualification limits. No FPGA was used.

# Fair software baselines for Nano lookup

## Conclusion

Yes: the old runtime batch exaggerated the hardware advantage. At N=9 in one
exact O2 ELF, hardware takes 3,042 cycles, the old batch takes 5,928, and the
compile-time-unrolled structure-of-arrays (SoA) batch takes 4,134. The fair
hardware/best-software ratio is therefore 1.359x rather than 1.949x. A second
warmup-corrected image reproduces 3,062 versus 4,166 (1.361x).

The advantage does not disappear under stronger optimization. At the selected
N=8 point, paired O2 hardware/batch results are 2,826/3,851 cycles (1.363x),
and paired O3 results are 2,833/3,839 (1.355x). The defensible claim is about
context-private register state plus hardware scheduling, not a twofold
context-switch-latency win.

## Compared implementations

| Mode | Implementation | N=9 cycles | Cycles/node |
| ---: | --- | ---: | ---: |
| 2 | Hardware worker prefetch | 3,042 | 30.727 |
| 3 | Historical runtime-count SoA batch | 5,928 | 59.879 |
| 7 | Compile-time-count, unrolled SoA batch | 4,134 | 41.758 |
| 8 | Compile-time-count batch that recomputes line addresses | 7,681 | 77.586 |
| 9 | Power-of-two lean-queue C++20 coroutine | 7,995 | 80.758 |
| 10 | Direct symmetric-transfer C++20 coroutine | 6,555 | 66.212 |

These six rows use one exact O2 ELF/NBF and all pass the matched checksum and
guest/core/host verdicts. The recompute batch is retained as a losing design
point: avoiding the line-pointer array costs more address/state work here. The
best coroutine is still 2.155x slower than hardware at N=9, but it is not the
best general software baseline; the unrolled SoA batch is.

## Worker-count sweep

The batch sweep uses the warmup-corrected O2 image. Hardware rows except the
bold paired N=8/N=9 controls are the prior accepted exact-model sweep; they are
shown to select the candidate optimum, not presented as a new exact-ELF matrix.

| Queries | Hardware cycles | Optimized batch cycles | Batch / hardware |
| ---: | ---: | ---: | ---: |
| 2 | 2,621 | 2,736 | 1.044x |
| 3 | 2,645 | 2,881 | 1.089x |
| 4 | 2,679 | 3,021 | 1.128x |
| 5 | 2,694 | 3,162 | 1.174x |
| 6 | 2,734 | 3,394 | 1.241x |
| 7 | 2,769 | 3,603 | 1.301x |
| **8** | **2,826** | **3,851** | **1.363x** |
| **9** | **3,062** | **4,166** | **1.361x** |
| 10 | 3,414 | 4,317 | 1.264x |

N=8 is the fair most-advantageous point, though N=9 is effectively tied. The
smooth increase through N=8 is consistent with the intended mechanism:
software explicitly scales search-state manipulation with N, while hardware
keeps each search's state in a resident register context. N=10 loses ground as
the ten-context/request system reaches saturation.

## Fairness controls and scope

- Every timed row performs the same eleven dependent searches per shard over
  the same data, queries, 16-byte hint path, result oracle, and 200-cycle
  pipelined AXI model. Runtime patching changes only mode and worker count.
- Coroutine frames, context seeding, result clearing, and warmup are outside
  the measured window. The corrected harness warms only the selected body and
  then executes switch-only, leaving every mode in one common final frontend
  state.
- O3 initially duplicated global trace labels when it unrolled labeled loops.
  Guarding those assembler labels fixes the diagnostic symbol definition;
  unrolling remains enabled in the optimized batch itself.
- The first isolated worktree setup accidentally requested recursive submodule
  initialization and filled the nearly-full filesystem with unrelated
  toolchains. That untouched worktree was removed and recreated without
  submodules; existing validated simulator/toolchain collateral was then used.
- Results are transcript-qualified simulation evidence. A new clean waveform
  trace and physical-DDR/FPGA qualification were not run, so this is not a
  physical speedup claim or a new retirement-level attribution of the residual
  35.5% O3 gap.

`results.csv` contains the qualified aggregate rows used here. Raw simulator
transcripts and generated images are intentionally omitted from the review
branch to keep the patch small. The O3 ELF SHA-256 is
`4b8257e371027b143763abe5bd4a2b54ba392331f9eacb138490f9f9f9958f21`.
