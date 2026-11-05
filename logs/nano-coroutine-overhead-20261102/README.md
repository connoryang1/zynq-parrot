# Hot RISC-V coroutine overhead

This simulator-only control removes cold/random lookup memory latency from the
Nano comparison.
Every row performs 8,192 identical register additions on the same in-order
BlackParrot core. C++20 frames are constructed before the timed markers and
destroyed afterward. The four rows are separately instruction-warmed and
validate their final values; the eight-frame ring uses distinct per-frame
outputs before aggregate validation.

No FPGA was used.

## Result

| Hot O3 implementation | Total cycles | Cycles/operation | Delta from manual |
| --- | ---: | ---: | ---: |
| Inline payload loop | 27,818 | 3.396 | -9.608 |
| No-inline manual state-machine resume | 106,523 | 13.003 | 0 |
| Single coroutine, outer driver resumes each step | 278,573 | 34.005 | +21.002 |
| Eight-frame direct symmetric-transfer ring | 237,939 | 29.045 | **+16.042** |

Direct symmetric transfer saves 4.960 cycles/operation relative to returning
to the outer driver after every suspension. It is nevertheless 16.042
cycles/operation above the manual state machine on this compiler/core. This is
steady-state execution only; it does not charge frame construction or random
lookup misses. Hot coroutine-frame loads and stores remain part of the cost.

At the accepted N=8 memory point, direct coroutine versus optimized batch is
63.261 - 43.375 = 19.886 cycles/node. The hot 16.042-cycle premium is about 81%
of that difference. This is a descriptive comparison rather than subtractive
accounting because the hot counter and binary lookup do not have identical
state. The remaining memory benchmark still includes lookup-frame work and
different request spacing. Batch versus hardware contributes another 11.443
cycles/node through lower sustained overlap, producing the complete 31.329
cycle/node coroutine-versus-hardware gap.

## Does a worker count cross over?

Fresh mode-10 runs used the exact accepted Nano O3 ELF/NBF and changed only the
runtime worker count. N=2--5 cover the plausible low-N crossover region; N=8 is
the accepted headline point.

| N | Hardware | Optimized batch | Direct coroutine | Coroutine / hardware | Coroutine / batch |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 2,595 | 2,710 | 2,903 | 1.119x | 1.071x |
| 3 | 2,638 | 2,835 | 2,981 | 1.130x | 1.051x |
| 4 | 2,688 | 2,973 | 3,048 | 1.134x | **1.025x** |
| 5 | 2,717 | 3,129 | 3,501 | 1.289x | 1.119x |
| 8 | 2,810 | 3,817 | 5,567 | 1.981x | 1.459x |

There is no hardware crossover. N=2 is the closest hardware ratio; N=4 is the
closest optimized-batch ratio. Coroutines still interleave successfully: at
N=8 they cut no-retirement time to 491 cycles versus hardware's 1,163 and are
3.65x faster than serial prefetch. They lose because the in-order core spends
more retired instructions between hints, not because interleaving fails.

## Identities and qualification

- Qualified clean model SHA-256: `85afe9d4e32ac8d05a8378fa257115442355da1f3d4e29c626903e8b9b46b277`
- Hot benchmark ELF SHA-256: `aa3deea30c3e0e2c66e40edabe04a937ad2d2c55f05c4f5b6109aede31c4a857`
- Hot benchmark NBF SHA-256: `3f374927f7239f62cf580e1dfac082d04c3d62b88c5a1602c3580404e3f59784`
- Accepted Nano ELF SHA-256: `98c45aafc6aacd0423e9ac968cdfc38f8c0f08853a16ebdd907ad00160b1e256`
- Accepted Nano NBF SHA-256: `721e75191bd64aad5a748280a78cbb344e1178ea8f9041b987e657f7c67afe4b`
- Compiler: canonical RISC-V GCC C++20 toolchain, `-O3`, freestanding flags
- Model: two physical threads, ten logical contexts, 200-cycle/10-deep
  pipelined synthetic reads (unused by the timed hot operations)

The hot run prints guest and core/host PASS. The standard harness initially
could not rebuild the model because this worktree lacks populated submodule
collateral, so the run reused the already-qualified clean model above and a
fresh NBF. The checker suite passes 17/17 with `TMPDIR=/dev/shm`; the root
filesystem had no free temporary-directory blocks. `compact-results.txt`
was used to extract the decisive guest output. The review branch retains the
aggregate results here rather than generated images or raw transcripts.
