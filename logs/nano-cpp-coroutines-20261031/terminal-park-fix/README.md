# Terminal park fix and corrected sweep

Simulator only; no FPGA was used. Commit `a78b024f` makes a never-resumed
worker's post-switch path unconditional. The exact executable SHA-256 is
`0a278d19873139bb2fb734cbc5d468a50e28576d9ac6a6f526567a6fc86e2eae`,
the NBF is
`6909d88025499542e42f16a4c481c7299a224c8be13c123b7a29741757dbace0`,
and all three isolated simulator copies used model SHA-256
`799c1dd29297e27312a070ea4a5f60f63d0d02c7d072862dc408fd179414ad78`.
The model configuration is two physical threads, ten logical contexts, ten
detached-prefetch slots, a pipelined 200-cycle synthetic AXI memory, and read
queue depth ten.

| Queries | Worker | C++20 coroutine | Coroutine / worker | Worker cycles/node |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 2,621 | 2,916 | 1.113x | 119.136 |
| 3 | 2,645 | 3,231 | 1.222x | 80.152 |
| 4 | 2,679 | 4,336 | 1.619x | 60.886 |
| 5 | 2,694 | 5,393 | 2.002x | 48.982 |
| 6 | 2,734 | 6,470 | 2.366x | 41.424 |
| 7 | 2,769 | 7,523 | 2.717x | 35.961 |
| 8 | 2,800 | 8,596 | 3.070x | 31.818 |
| **9** | **3,060** | **9,645** | **3.152x** | **30.909** |
| 10 | 3,414 | 10,734 | 3.144x | 31.036 |

N=2 minimizes absolute batch latency. N=9 maximizes both useful-node
throughput and the hardware/coroutine ratio; N=10 is the full-capacity stress
case and is slightly past the measured optimum.

The corrected N=5 controls are serial demand 181,546, demand ring 181,671,
serial prefetch 12,725, coroutine 5,393, explicit batch 4,454, worker 2,694,
and switch-only 766 cycles. Over 55 useful visits, demand/serial-prefetch/
coroutine/batch/worker cost 3,300.836/231.364/98.055/80.982/48.982 cycles per
node. Worker is 67.389x faster than serial demand, 4.723x faster than serial
prefetch, 2.002x faster than the coroutine, and 1.653x faster than the batch.
The demand ratio includes narrower transport; serial prefetch is the cleaner
overlap comparison. Switch-only costs 13.927 cycles per scheduled node and is
not mechanically subtracted.

All 23 Nano runs pass result, checksum, guest, core, and host checks. The
dependent-stream regression (mode 2, four streams, 32 nodes) also passes. Run
and checker transcripts are in `runs/`; `SHA256SUMS` covers every retained
transcript.

Exact N=4/5/6 A/B results are 5,904/2,710/5,962 before and
2,679/2,694/2,734 after, removing 3,225/16/3,228 cycles. Disassembly keeps the
worker entry at `0x800005c0` and consuming load at `0x800005ec`; only the
terminal sequence changes. The baseline root cause and trace-reading
corrections are documented in `../trace-n456-diagnostics/`.
