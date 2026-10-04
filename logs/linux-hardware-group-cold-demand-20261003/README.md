# Cache-displaced Linux versus hardware-context demand on physical FPGA

This accepted run isolates the three terminating modes from the earlier
integrated hardware-group request experiment and raises their evidence from four
incomplete samples to 32 complete samples per mode. Every sample processes the
same two deterministic 4,096-request streams over a 2 MiB data set after a
4 MiB best-effort cache-displacement pass. Mode order rotates within each
sample, and every mode produces the same checksum.

The modes are:

- `linux-threads-demand`: two ordinary pthread workers pinned to CPU 0;
- `batched-prefetch-load`: one Linux thread hints both next addresses and then
  loads them;
- `resident-demand-handoff`: two resident hardware contexts alternate before
  every demand load, with no prefetch hint.

| Mode | Median cycles | Cycles/request | p95 cycles | Maximum | Variation (CV) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Linux threads, demand | 668,902.5 | 81.65 | 711,328 | 726,963 | 3.12% |
| Batched prefetch/load | 789,799 | 96.41 | 826,483 | 861,472 | 2.15% |
| Resident hardware demand | **612,147** | **74.72** | **618,324** | **618,426** | **0.31%** |

The resident hardware path is **1.093x faster** than ordinary Linux demand at
the median and saves 56,755.5 cycles per 8,192-request sample, or 6.93 cycles
per request. A deterministic paired bootstrap over the 32 rotating-order
samples gives a 95% interval of **1.070x--1.100x** and a cycle-saving interval
of 42,646--61,482. Its p95 is 1.150x faster than the Linux p95. The hardware
path is also much tighter: its p95 is 1.01% above its median, versus 6.34% for
Linux.

The 32-sample result corrects the earlier incomplete four-sample diagnostic,
which suggested 1.120x. That partial estimate overstated the accepted ratio by
2.53%. The result also shows that batching these best-effort hints is not an
ideal reference on this workload: its median is 18.07% slower than Linux demand
and 29.02% above hardware demand.

This is an end-to-end implementation comparison. The pthread path includes
thread release and drain and executes C worker loops; the hardware path uses
leaf assembly and performs one hardware handoff per request. Linux amortizes
its scheduler work over each worker's entire 4,096-request stream, so the
hundreds-fold switch-only advantage is expected to become a 9.3% application
gain here. The measurement does not attribute all 56,755 saved cycles to
context switching alone.

The cache displacement is best effort rather than an architectural flush, and
the random streams can revisit lines. “Cache-displaced” therefore does not mean
that every access is proven to miss. The omitted
`resident-prefetch-yield-load` mode still has a separately recorded sustained
lifecycle stall. This run establishes a repeatable hardware-demand application
speedup; it does not establish an integrated hardware-prefetch speedup.

The accepted run verifies all 96 result rows, balanced mode ordering, 786,432
total checked requests, the exact guest ELF, the exact routed bitstream, native
exit zero, runner exit zero, and `CORE[0] PASS`. The physical board powered off
cleanly. Identities are:

| Artifact | SHA-256 |
| --- | --- |
| Guest ELF | `de53ce7c669c469630367b4b93e512a2f85ea5a8b6337c787ad7eb4b5971d2ee` |
| Bitstream | `9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |

Reproduce the analysis with:

```sh
python3 -B logs/linux-hardware-group-cold-demand-20261003/analyze.py \
  > logs/linux-hardware-group-cold-demand-20261003/analysis.stdout
cmp logs/linux-hardware-group-cold-demand-20261003/analysis.json \
  logs/linux-hardware-group-cold-demand-20261003/analysis.stdout
```

The dynamic ELF was built with:

```sh
make -C linux-tests REQUEST_NUM_CONTEXTS=10 \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  request-benchmark-dynamic
```
