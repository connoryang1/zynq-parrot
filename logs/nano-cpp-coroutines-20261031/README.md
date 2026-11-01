# Nano C++20 coroutine simulator sweep

This directory retains the transcript evidence for the matched hardware-worker
versus compiler-generated C++20 coroutine comparison. No FPGA was used.

All rows use the synthetic pipelined AXI model with 200-cycle read latency,
queue depth ten, two physical threads, ten logical contexts, and ten detached
prefetch slots. Modes and worker/query count are runtime selectors in the same
combined benchmark source. Every retained transcript reports the requested
mode/count, eleven levels, the count-specific matched checksum, benchmark PASS,
`CORE PASS`, `BSG PASS`, and `VALID RUN`.

Corrected terminal-path sweep:

| Queries | Worker mode 2 | Coroutine mode 6 | Coroutine / worker | Worker cycles/node |
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

N=2 has the lowest absolute batch latency. N=9 has the best useful-node
throughput and the largest hardware/coroutine ratio, so it is the selected
“most advantageous” point. N=10 is a useful full-capacity stress case but is
slightly past the throughput optimum.

A later same-model scheduler diagnostic shows that the roughly 98-cycle
coroutine floor belongs primarily to this control's checked ten-entry circular
queue, not to coroutine suspension itself. Power-of-two head/tail scheduling
reaches 76.5 cycles/node and direct symmetric transfer reaches 63.8; at N=5
both restore the original coroutine-over-batch ordering. These diagnostic
variants are retained under `coroutine-scheduler-diagnostic/` and do not replace
the complete accepted table above until one receives a full sweep and trace.

The N=9 batch-versus-hardware gap is now retirement-attributed under one exact
diagnostic ELF. Of the 2,888-cycle gap, 2,707 cycles (93.7%) are additional
batch instructions and 181 (6.3%) are additional cycles without retirement.
The dominant instruction cost is explicit array-state load/store and loop
bookkeeping that hardware contexts keep in private registers. Compact reports
and local waveform hashes are under `batch-hardware-attribution/`.

Original rejected sweep:

| Queries | Worker mode 2 | Coroutine mode 6 | Coroutine / worker |
| ---: | ---: | ---: | ---: |
| 2 | 2,624 | 2,929 | 1.116x |
| 3 | 2,644 | 3,247 | 1.228x |
| 4 | 5,904 | 4,307 | 0.729x |
| **5** | **2,710** | **5,372** | **1.982x** |
| 6 | 5,962 | 6,429 | 1.078x |
| 7 | 6,014 | 7,486 | 1.245x |
| 8 | 6,050 | 8,579 | 1.418x |
| 9 | 6,274 | 9,644 | 1.537x |
| 10 | 6,624 | 10,717 | 1.618x |

This original table is retained as rejected tuning evidence. N=4 and N=6 each
contain one artificial 3,239-cycle off-path I-cache refill. The corrected
terminal path and same-model A/B reduce N=4 from 5,904 to 2,679 cycles and N=6
from 5,962 to 2,734, while N=5 changes only from 2,710 to 2,694. The corrected
complete sweep below supersedes the old selection of five.

The remaining matched N=5 controls quantify what that headline includes:

| N=5 schedule | Cycles | Cycles/useful node | Relative to hardware |
| --- | ---: | ---: | ---: |
| Serial demand, no hint | 181,546 | 3,300.836 | 67.389x |
| Serial prefetch | 12,725 | 231.364 | 4.723x |
| C++20 coroutine | 5,393 | 98.055 | 2.002x |
| Explicit software batch | 4,454 | 80.982 | 1.653x |
| Hardware worker | 2,694 | 48.982 | 1.000x |

The 67.389x demand ratio combines two changes: ordinary demand fetches full
cache lines serially, while hardware uses narrow detached hints and overlaps
five searches. Serial prefetch uses the same hint transport without
interleaving, so its 4.723x ratio is the cleaner estimate of scheduling overlap.
At this count hardware is also 39.5% faster than the hand-written batch. The
terminal-path artifact has been removed at every count, so the result no longer
depends on N=5 uniquely avoiding that refill. It remains a result for this
bare-metal implementation, not a universal claim about optimized batching.

The N=5 switch-only control is 766 cycles, or 13.927 cycles per scheduled node
when normalized by the same 55 steps.  It performs no useful loads, and its
terminal ring lap is included, so it is a control rather than a quantity to
subtract mechanically from the data modes.

The trace analyzer now reports exact time-weighted outstanding occupancy as
the sum of transaction lifetimes divided by either the complete measured
window or the first-issue-to-last-completion active interval.  Reanalysis of
the accepted corrected N=10 worker waveform gives 3.445 average UCE hints over
the entire 6,609-cycle window, 7.063 while the request pipeline is active, and
a peak of nine.  The current-build N=5 sweep is transcript-qualified; its
trace teardown issue means it does not yet have an accepted average-outstanding
measurement. Focused N=4/N=6 traces accept and consume all 44/66 hints
with zero ordinary D-cache reads. Their full-window/active averages and peaks
are 1.543/3.527/4 and 2.292/5.159/6. Both slow rows issue one blocking I-cache
refill at byte address `0x800003c0` in `main`'s checksum loop after a parked
worker speculates through its conditional park and following `ret`. The
frontend cannot cancel the refill when the context redirect arrives; retirement
resumes seven or eight cycles after its final response. The request-to-final-
response interval is 3,239 cycles in both cases. The prior word-address mapping,
coroutine-scheduler attribution, and two-request count were trace-reading
errors. See
`trace-n456-diagnostics/` for event cycles, hashes, and qualification limits.

The committed N=10 trace diagnostic used top `f4db758c99433a2567baccf7090ab8f9274a1575`
and BlackParrot `6c79a42107a3857e63b6f47bc2468fe4599c5bff`. Its exact ELF and NBF are under
`rejected-trace-mode6/`; their SHA-256 values are
`24c6463c32da402fa28b7058acaea75e91d65492e56a31a598ef73852ffe8ce7` and
`b55bef9ce1fe91d08b2f52b10dd8ada2ef435f345d7891d6871afcc20cb63ff0`.
The 191-MiB waveform remains temporarily at
`/dev/shm/nano-cpp-coroutine-mode6-f4db758c/mode-6/dump.fst`, SHA-256
`cb8631380b5fd1add86f97c3e0a186476e38608e3ee60ca48a78ff1ec427c6ed`.

That trace is rejected for architectural overlap qualification. The benchmark,
checksum, guest, core, and host checks passed at 10,717 cycles, but the known
post-PASS GPIO shutdown assertion left the converted FST with a nonmonotonic
timestamp before backend commit-PC events were emitted. Consequently it cannot
prove all eight committed windows or 110 consuming-load retirements. The files
are retained to make the rejection reproducible rather than to support a trace
claim.

Representative sweep command:

```sh
make -C testing run-mt_nano_lookup_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 \
  NANO_MODE=6 NANO_WORKERS=5 \
  ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install \
  SIM_DEFINES='BP_AXI_MEM_PIPELINED BP_AXI_MEM_READ_LATENCY=200 BP_AXI_MEM_READ_QUEUE_DEPTH=10'
```
