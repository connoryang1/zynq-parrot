# Demand-path attribution with matched assembly controls

This experiment explains the preceding cache-displaced hardware/Linux result by
adding two stackless single-context controls to the same random-request
benchmark. All four modes use the same two deterministic 4,096-request streams,
2 MiB data set, 4 MiB best-effort displacement pass, demand-load count, and
checksum:

- ordinary pinned Linux pthread demand;
- resident hardware contexts alternating before every demand;
- one assembly context executing stream 0 and then stream 1;
- one assembly context alternating the streams without switching.

The accepted bounded run contains 12 samples per mode with each mode appearing
exactly three times in every order position:

| Mode | Median cycles | Cycles/request | Relative to interleaved assembly |
| --- | ---: | ---: | ---: |
| Linux threads | 680,919.5 | 83.12 | 1.200x |
| Resident hardware handoff | 611,886 | 74.69 | 1.078x |
| Sequential leaf assembly | 575,671 | 70.27 | 1.014x |
| Interleaved leaf assembly | **567,541.5** | **69.28** | 1.000x |

The hardware path costs 44,344.5 cycles more than the matched interleaved
assembly control, or **5.413 cycles per request**. A deterministic paired
bootstrap gives a 95% interval of **4.959--5.708 cycles/request**. This contains
the independently measured 5.125-cycle resident register-target handoff cost.
The observed hardware/interleaved ratio is 1.078x, with bootstrap interval
1.071x--1.083x.

This accounts for the result mathematically: the hardware loop executes roughly
one resident switch per demand, and its entire excess over the no-switch
interleaved control is approximately that switch cost. The demand instruction
runs only after a context returns, so switching does not create multiple
outstanding demand loads. Interleaving two streams in one context improves only
1.4% over executing them sequentially. Hardware switching is still faster than
the Linux pthread implementation, but both optimized single-context controls
are faster than hardware switching for this blocking-demand workload.

The implication is that cheap switching alone cannot hide this memory latency.
The application needs a nonblocking request before the switch—such as the
project's prefetch hint—or hardware that permits outstanding demand work. That
is also why repairing the sustained prefetch-plus-handoff lifecycle remains the
important integration task.

## Longer-run lifecycle result

The first run requested 32 samples. It completed and checksum-verified samples
1--16 in all four modes, then printed
`SAMPLE_BEGIN sample=17 order=0 mode=resident-demand-handoff` and produced no
result before the control watchdog ended the run. It is retained as a measured
stall and is excluded from accepted timing. Its complete prefix independently
reproduces the medians: 611,879 hardware, 575,531 sequential, 567,243.5
interleaved, and 678,199 Linux cycles.

The accepted retry deliberately requested 12 samples, passed all 48 rows,
native exit zero, runner exit zero, and `CORE[0] PASS`, then powered off cleanly.
Its timing claim is therefore bounded to that declared run. The sample-17
failure is not yet a general 16-launch limit: the preceding demand-only binary
completed 32 hardware samples on the same bitstream. Code layout, mixed-mode
state, and asynchronous physical behavior remain possible causes.

A subsequent demand-only run of this exact ELF completed samples 1--26, then
reported a hardware context/completion verification failure in sample 27 and
did not return. Mixed modes are therefore not required, and 16 is not a fixed
launch limit. The demand routines are opcode-identical to the older
32-sample-passing ELF but moved by 264 bytes; the controlled placement and
failure-value experiments subsequently show variable outcomes. An exact repeat
stops in sample 3, a shifted diagnostic completes 64, and a controlled
64-byte-aligned build stops in sample 51. Alignment is therefore not a fix;
the aggregate evidence identifies an intermittent lifecycle hazard. See
`logs/linux-hardware-demand-lifecycle-repeats-20261003/`.

Cache displacement is best effort rather than an architectural flush, and
random streams can revisit lines. Every request is not proven to miss.
`CLOCK_MONOTONIC` values are retained but conclusions use the core cycle
counter.

| Artifact | SHA-256 |
| --- | --- |
| Guest ELF | `8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643` |
| Bitstream | `9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |

Reproduce the analysis with:

```sh
python3 -B logs/linux-hardware-group-demand-attribution-20261003/analyze.py \
  > logs/linux-hardware-group-demand-attribution-20261003/analysis.stdout
cmp logs/linux-hardware-group-demand-attribution-20261003/analysis.json \
  logs/linux-hardware-group-demand-attribution-20261003/analysis.stdout
```

Rebuild the exact dynamic ELF from its retained source with:

```sh
/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  -I linux-tests -O2 -Wall -Wextra -Werror \
  -march=rv64imafdc_zicsr -mabi=lp64d -mcmodel=medany \
  -no-pie -std=c11 -pthread -DBP_NUM_THREADS=2 -DBP_NUM_CONTEXTS=10 \
  -DBP_REQUEST_LOAD_AHEAD=0 \
  -o /tmp/request_attribution_rebuilt \
  logs/linux-hardware-group-demand-attribution-20261003/request_benchmark.c
cmp /tmp/request_attribution_rebuilt \
  logs/linux-hardware-group-demand-attribution-20261003/request_benchmark_dynamic
```
