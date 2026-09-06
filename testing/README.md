This directory contains the active bare-metal tests for resident and SRAM-backed nonresident context switches. Use this guide for the accepted two-resident/four-logical configuration; older scale experiments and measurements remain in the historical Git checkpoint.

# Tests

Run from the repository root. First preserve any logs and waveforms you need;
then finish each cleanup command before launching the consuming build.

```sh
make -C testing clean
make -C cosim/black-parrot-minimal-example/verilator clean
make -C testing run-mt_umode_nonresident_sv39_data_handoff_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

Use the available CPU/memory budget for `VERILATOR_BUILD_JOBS`. Do not assume an
outer `make -j` accelerates every nested build; check the actual compiler jobs.
A successful clean model can be reused for subsequent software tests with
unchanged RTL/configuration. Run guests serially and preserve each closed trace
before the next test overwrites shared `prog.*`, `run.log`, and waveform files.

## Current gates

| Test | What it checks |
| --- | --- |
| `mt_ctxtsw_smoke_test` | Resident 0→1→0 handoff |
| `mt_umode_nonresident_handoff_test` | U-mode SRAM-backed handoff without translated fetch |
| `mt_umode_nonresident_sv39_handoff_test` | U-mode handoff with translated instructions |
| `mt_umode_nonresident_sv39_data_handoff_test` | Translated instructions/data and target replay recovery |
| `mt_ctxtsw_nonresident_overhead_benchmark` | Matched resident/nonresident ring spacing using global cycles |

For example, after the model build:

```sh
make -C testing run-mt_ctxtsw_smoke_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1
make -C testing run-mt_ctxtsw_nonresident_overhead_benchmark NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1
```

Require the test-specific success marker plus `CORE PASS`, and inspect the
unfiltered simulator log. A timeout or guest failure is not success even if host
teardown prints `BSG PASS`. The known GPIO teardown assertion after guest PASS
must be reported separately.

## Scope and interpretation

A nonresident result requires `NUM_CONTEXTS > NUM_THREADS`; default all-resident
topologies do not test SRAM eviction. The benchmark reports amortized
cycles/switch, not an isolated redirect latency. Use `0xCC0` across contexts;
context-restored `mcycle` is not a physical elapsed-time counter.

Other checked-in probes are targeted diagnostics, not a claim that every topology,
FP preservation mode, or address-space combination is accepted. Avoid resurrecting
removed tests from prebuilt ELFs. See [architecture](../CONTEXT_SWITCH_ARCHITECTURE.md)
for limits, [Linux tests](../linux-tests/README.md) for the application proof, and
[history](../HISTORY.md) for prior measurements.
