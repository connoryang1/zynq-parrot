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

Five is the selected default: hardware uses 49.6% fewer cycles than the C++20
coroutine control and has the lowest worker cycles per useful load. The sharp
four-query regression makes this an empirical selection, not an inference from
the ten-slot queue capacity.

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
