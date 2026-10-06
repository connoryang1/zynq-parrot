This directory preserves the first accepted end-to-end simulation of the synthesizable I/D accepted-miss recorder. It establishes that custom-CSR control, physical miss capture, synchronous record readout, and the existing context-switch path work together in the maintained Zynq model.

# Accepted cache-miss trace simulation

The trace-enabled model was clean-built with:

```text
make -C testing rebuild-sim NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

The accepted directed run used:

```text
make -C testing run-mt_cache_miss_trace_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

The fail-closed verdict checker reports `VALID RUN: guest and host PASS`. The recorded interval contains two accepted I-cache demand misses and one accepted D-cache demand miss, with no overflow. The intended cold function line appears at core cycle `0x623be`; its intended cold data line appears at `0x623fd`, 63 cycles later. That interval includes instruction sequencing and cold-function execution and is not a standalone DRAM-latency measurement.

A previously accepted test was then run against the same instrumented model with the recorder disarmed:

```text
make -C testing run-mt_ctxtsw_smoke_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

It retained `[BSG-PASS] ctxtsw smoke test completed`, `CORE PASS`, and `BSG PASS`. The earlier first directed attempt returned an all-zero status because the minimal Zynq top instantiates `bp_unicore_lite` directly; explicitly enabling the compile-time recorder parameter at that top is the retained guardrail.

`dump.fst`, `run.log`, the exact ELF/NBF, and their hashes are retained here. The source revisions are the repository commit containing this directory and its recorded BlackParrot and subsystem gitlinks.
