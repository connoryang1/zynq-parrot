This directory records the first simulation validation of the hardware switch-boundary interlock. It distinguishes functional coverage, waveform activation, and exact performance comparison so the later routed FPGA result can be assessed against a fixed checkpoint.

# One-cycle target-dispatch interlock

BlackParrot commit `6c79a42107a3857e63b6f47bc2468fe4599c5bff` adds one bit in
`bp_be_scheduler`: a committed context switch asserts the bit for the following
cycle, and backend issue is disabled while it is set. Frontend responses may
still enter the issue queue. The change therefore guarantees one edge of
separation before the first target-context dispatch without adding a software
instruction or delaying unrelated execution.

## Validation

The following clean trace-enabled runs used the maintained testing harness:

```sh
make -C testing clean
make -C testing run-mt_umode_nonresident_handoff_test \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
make -C testing run-mt_dependent_stream_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=10 BENCH_MODE=3 STREAMS=10 \
  STREAM_NODES=1280 PREFETCH_ELS=10 TRACE=1 VERILATOR_BUILD_JOBS=12
make -C testing run-mt_dependent_stream_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=10 BENCH_MODE=3 STREAMS=2 \
  STREAM_NODES=1280 PREFETCH_ELS=10 TRACE=1 VERILATOR_BUILD_JOBS=12
```

All three tests printed their test-specific `[BSG-PASS]` marker and `CORE PASS`.
The ten-stream benchmark measured 23,972 simulator cycles. The newly compiled
two-stream image measured 19,270 cycles, but its NBF is not byte-identical to
the archived baseline and is therefore only a correctness result.

The strict performance control ran the archived original k2 NBF, SHA-256
`92b0bdbe635486053a23ca9fc86074678a8f28b11e07626d43a23a11af6a5b0c`,
on the new model. It measured exactly 19,258 cycles, matching its archived
pre-interlock simulator result. The protected cycle is fully overlapped by the
existing frontend/empty-queue gap in this workload. The sanitized direct-run
transcript is `exact-k2-run.strings.log`; the raw transcript SHA-256 was
`0ebf5a662277fa27b66779eecf84c0535de668dfbddcdcee395c185e7fdd60de`.

`extract_interlock.c` checks the retained k2 FST. It finds 1,292 committed
switch pulses and 1,292 settle pulses after reset. The issue queue is empty in
every settle cycle, which explains the zero measured cost. The FST itself is
an ignored local build artifact with SHA-256
`693f82b9b45c347c70682a0b7b51d2bfce46ffd473d6b3d585aeb877a3c6f4a6`.

The known DPI GPIO finalization assertion occurs after guest and host PASS in
the harness runs. Physical correctness is still pending a routed image and an
alternating original ten-stream/baseline matrix; simulation never reproduced
the original corruption.

