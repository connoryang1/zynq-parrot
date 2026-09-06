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
| `mt_ctxtsw_logical_csr_readback_test` | Committed logical ID and side-effect-free reads of CSR `0x800` |
| `mt_regfile_test` | Integer-context execution, private stack, and return-state isolation |
| `mt_csr_isolation_test` | Independent resident `mscratch` state |
| `mt_frf_isolation_test` | Resident floating-point register isolation; not nonresident FP preservation |
| `mt_abi_preservation_test` | Live `gp` and callee-saved integer registers across a resident round trip |
| `mt_ctxtsw_late_wb_hazard_test` | Source load result survives a resident round trip; source late writeback must not clear the target's scoreboard hazard |
| `mt_ctxtsw_gpr_ring_stress` | Live integer-register sentinels survive a ring through all four logical IDs |
| `mt_ctxtsw_pure_ring_stress_test` | Progress through dense consecutive switches across all four logical IDs |
| `mt_umode_nonresident_handoff_test` | U-mode SRAM-backed handoff without translated fetch |
| `mt_umode_nonresident_sv39_handoff_test` | U-mode handoff with translated instructions |
| `mt_umode_nonresident_sv39_data_handoff_test` | Translated instructions/data and target replay recovery |
| `mt_ctxtsw_nonresident_overhead_benchmark` | Matched resident/nonresident ring spacing using global cycles |

These 13 programs retain distinct state, hazard, and redirect regressions.
The two Sv39 handoff variants include the base handoff source, keeping the
instruction-only and instruction/data cases comparable without duplicate tests.
`make -C testing all NUM_THREADS=2 NUM_CONTEXTS=4` compiles the complete set;
compilation alone is not a runtime pass. Use that topology for the handoff tests
and benchmark: the benchmark specifically compares resident context 1 with
nonresident context 2. The four-ID ring tests require at least four logical
contexts; resident-only isolation tests use contexts 0 and 1.

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

### Ordinary-load overlap probe

`mt_ctxtsw_late_wb_hazard_test` issues a normal load into context 0's `a5`,
immediately requests a resident switch, and runs an independent divide plus
dependent arithmetic in context 1. It checks both contexts' results after the
round trip. Run with `NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1`; contexts 0 and 1
remain resident. No prefetch instruction is used.

PASS establishes correctness, not overlap or speedup. Disassemble the freshly
built ELF to locate `t0_roundtrip` and `t1_entry`; pass their load, switch, and
target arithmetic PCs to `tools/load_switch_vcd_events.py`:

```sh
fst2vcd path/to/archived/dump.fst \
  | python3 tools/load_switch_vcd_events.py --pc <load-PC> --pc <target-PC>
```

The JSON rows sample pre-rising-edge signals; the default period assumes the
normal 20 MHz clock and 1 ps trace ticks. Require a source `miss`, an actual
target `dv=1,dq=1,tid=1` dispatch, and matching source `critical` data arrival
in that order. Check committed target arithmetic (`cv,cp`) and guest results
as well: speculative switch requests or late register writeback alone do not
prove memory-latency hiding. Distinguish initial long misses from short later
misses, which may finish before target execution. Nonresident bank replacement
has an additional drain requirement and is not validated by this probe.

A nonresident result requires `NUM_CONTEXTS > NUM_THREADS`; default all-resident
topologies do not test SRAM eviction. The benchmark reports amortized
cycles/switch, not an isolated redirect latency. Use `0xCC0` across contexts;
context-restored `mcycle` is not a physical elapsed-time counter.

Removed scale, gap/unroll, synthetic-worker, predictor, and alternate timing
experiments remain recoverable at Git checkpoint `f028d66a`. The global-cycle
benchmark replaces their overlapping performance role; the redundant demo and
four-context CSR probe add no independent invariant to the retained suite.
The bare-mode ASID probe could pass without testing translation, while the
privilege and MPRV/Sv39 remap experiments are not accepted gates. The retained
U-mode translated handoff tests cover the accepted path but do not establish
general address-space or privilege isolation.

The suite is not a claim that every topology, FP preservation mode, or
address-space combination is accepted. Avoid resurrecting removed tests from
prebuilt ELFs. See [architecture](../CONTEXT_SWITCH_ARCHITECTURE.md)
for limits, [Linux tests](../linux-tests/README.md) for the application proof, and
[history](../CURRENT_CHECKOUT.md#history-and-recovery) for prior measurements.
