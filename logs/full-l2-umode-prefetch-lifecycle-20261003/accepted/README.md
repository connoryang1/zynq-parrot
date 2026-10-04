# Full-hierarchy translated prefetch/handoff lifecycle

This checkpoint runs the six-epoch U-mode Sv39 lifecycle test through the full
BlackParrot wrapper with two L2 banks, two resident register banks, ten logical
contexts, ten detached-prefetch slots, and the pipelined AXI memory model.
Ordinary demand traffic traverses the L2 hierarchy. The accepted 2/10 endpoint
routes detached hints around L2 with `BP_PREFETCH_AXI_BYPASS`, so this test
checks the interaction between L2-backed demand traffic and bypassed hint
responses; it does not test installing hints into L2.

The trace-enabled command was:

```sh
env DEFINES='BP_ZYNQ_PREFETCH_TWO_BANKS BP_AXI_MEM_PIPELINED' \
  BSG_TRACE_TIMEOUT_S=1200 VERILATOR_BUILD_JOBS=12 \
  make -C testing run-mt_umode_prefetch_handoff_lifecycle_test \
  SIM_DIR="$PWD/cosim/black-parrot-example/verilator" \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 TRACE=1
```

The guest lifecycle marker, core, and host pass. The maintained checker reports
`VALID RUN`; there is no pre-PASS simulator error. The target retires 101,299
instructions over 52,596 MTIME ticks, matching the rejected pre-fix run exactly.
`checker.log` records the independent checker verdict.

## Lifecycle result

Each epoch contains 512 logical hints. A write episode is one contiguous
assertion of `prefetch_buffer_write`; on the 64-bit full-system AXI port, one
episode supplies the requested 64-bit word. Each successful request is paired
in order with its buffer write and later demand hit.

| Epoch | Hints | Request episodes | Useful buffer hits | Coverage | Translation-miss attempts | Maximum UCE occupancy | Residual side/UCE state |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 512 | 503 | 503 | 98.24% | 8 | 2 | 0 / 0 |
| 2 | 512 | 503 | 503 | 98.24% | 9 | 2 | 0 / 0 |
| 3 | 512 | 503 | 503 | 98.24% | 9 | 2 | 0 / 0 |
| 4 | 512 | 503 | 503 | 98.24% | 9 | 2 | 0 / 0 |
| 5 | 512 | 503 | 503 | 98.24% | 9 | 2 | 0 / 0 |
| 6 | 512 | 503 | 503 | 98.24% | 9 | 2 | 0 / 0 |

All 3,018 request episodes produce a side-buffer write and a later useful
side-buffer demand hit. No UCE drop occurs. Side-buffer valid, UCE valid, and
UCE sent state return to zero after every epoch. Epochs 2 through 6 are
identical, so neither the modeled full L2 hierarchy nor repeated translated
handoffs accumulates stale detached state.

The pipelined memory model is configured for a 40-cycle read response from AXI
AR acceptance. Trace pairing measures:

| Interval | Minimum | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Prefetch request to side-buffer write | 45 | 45 | 45 | 45 |
| Side-buffer write to matching demand | 17 | 17 | 17 | 121 |
| Prefetch request to matching demand | 62 | 62 | 62 | 166 |

Thus the normal request receives its data after 45 cycles and the matching
demand arrives 62 cycles after issue. The data is already waiting for a median
17 cycles before demand. This directly verifies latency hiding rather than
inferring it from total benchmark time.

The minimal U-mode model previously completed 334/512 hints per epoch (65.23%)
with maximum UCE occupancy one. That model has a 32-bit, nonpipelined memory
port. This full model has a 64-bit AXI port and a four-entry pipelined read
queue, allowing maximum UCE occupancy two and raising useful coverage to
98.24%. The minimal result was therefore constrained by its memory endpoint,
not by an accumulating handoff leak.

## Host-model bug found while qualifying the run

Two initial full runs reached guest, core, and host PASS but emitted:

```text
BSG-ERROR: ... axil2, AXI M bvalid timeout
```

The GP2 waveform showed address/data acceptance followed by `BVALID` only a
few cycles later. The simulator's main guest loop advanced raw RTL clocks
without resuming outstanding host coroutines, so the watchdog coroutine missed
the short response pulse and eventually printed a timeout. The fix services
host-side AXI coroutines on every simulation step. Hardware builds retain the
original raw tick. After the fix, the identical workload and target cycle
counts pass without the timeout.

`extract_fst.c` uses Verilator's FST reader to select only the twelve lifecycle
signals. From the repository root, regenerate the 21.8 MB event stream and
analysis with:

```sh
cc -O2 -Wall -Wextra \
  -Iinstall/share/verilator/include/gtkwave \
  -Iimport/black-parrot-tools/yosys/libs/fst \
  logs/full-l2-umode-prefetch-lifecycle-20261003/accepted/extract_fst.c \
  install/share/verilator/include/gtkwave/fstapi.c \
  install/share/verilator/include/gtkwave/fastlz.c \
  install/share/verilator/include/gtkwave/lz4.c \
  -lz -pthread -o /tmp/full_l2_extract
/tmp/full_l2_extract \
  logs/full-l2-umode-prefetch-lifecycle-20261003/accepted/dump.fst \
  logs/full-l2-umode-prefetch-lifecycle-20261003/accepted/events.txt \
  2>logs/full-l2-umode-prefetch-lifecycle-20261003/accepted/selected-signals.txt
REUSE_EVENTS=1 python3 -B \
  logs/full-l2-umode-prefetch-lifecycle-20261003/accepted/extract.py \
  >logs/full-l2-umode-prefetch-lifecycle-20261003/accepted/analysis.stdout
```

The C extractor reproduced the archived event stream byte-for-byte. The Python
analysis fails on any UCE drop, unmatched request/write/hit episode, or residual
side-buffer/UCE state.

The raw FST is retained locally as `dump.fst` and is not committed because it
is 193 MiB. Its SHA-256 is recorded in `SHA256SUMS`.
