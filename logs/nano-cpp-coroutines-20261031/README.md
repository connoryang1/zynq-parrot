# Nano C++20 coroutine simulator sweep

This directory retains the transcript evidence for the matched hardware-worker
versus compiler-generated C++20 coroutine comparison. No FPGA was used.

All rows use the synthetic pipelined AXI model with 200-cycle read latency,
queue depth ten, two physical threads, ten logical contexts, and ten detached
prefetch slots. Modes and worker/query count are runtime selectors in the same
combined benchmark source. Every retained transcript reports the requested
mode/count, eleven levels, the count-specific matched checksum, benchmark PASS,
`CORE PASS`, `BSG PASS`, and `VALID RUN`.

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

Five is the selected measured default: hardware uses 49.6% fewer cycles than
the C++20 coroutine control and has the lowest worker cycles per useful load.
The adjacent-count trace proves this is not an optimum inferred from the
ten-slot queue capacity. N=4 and N=6 each encounter one 3,239-cycle off-path
I-cache request episode; N=5 avoids it in this exact executable/cache state.

The remaining matched N=5 controls quantify what that headline includes:

| N=5 schedule | Cycles | Cycles/useful node | Relative to hardware |
| --- | ---: | ---: | ---: |
| Serial demand, no hint | 181,548 | 3,300.873 | 66.992x |
| Serial prefetch | 12,708 | 231.055 | 4.689x |
| C++20 coroutine | 5,372 | 97.673 | 1.982x |
| Explicit software batch | 4,458 | 81.055 | 1.645x |
| Hardware worker | 2,710 | 49.273 | 1.000x |

The 66.992x demand ratio combines two changes: ordinary demand fetches full
cache lines serially, while hardware uses narrow detached hints and overlaps
five searches. Serial prefetch uses the same hint transport without
interleaving, so its 4.689x ratio is the cleaner estimate of scheduling overlap.
At this count hardware is also 39.2% faster than the hand-written batch. The
focused trace shows that this comparison benefits from N=5 avoiding an
instruction-front-end artifact found at adjacent worker counts; it is not a
general claim that hardware scheduling intrinsically beats optimized batching.

The N=5 switch-only control is 816 cycles, or 14.836 cycles per scheduled node
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
measurement. Focused valid N=4/N=6 traces accept and consume all 44/66 hints
with zero ordinary D-cache reads. Their full-window/active averages and peaks
are 1.543/3.527/4 and 2.292/5.159/6. Both slow rows accept two consecutive
I-cache requests for raw word address `0x800003c0` (byte line `0x80000f00`),
then resume retirement seven or eight cycles after the final response. The
first-request-to-final-response interval is 3,239 cycles in both cases. See
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
