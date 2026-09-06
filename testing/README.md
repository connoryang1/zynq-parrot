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
| `mt_pointer_compute_benchmark` | Equal-work sequential, single-thread fused, and resident-switched pointer traversal plus arithmetic |
| `mt_independent_requests_benchmark` | Two independent pointer chains: sequential, manually batched loads, and resident load/yield/consume handlers |

These programs retain distinct state, hazard, redirect, and workload comparisons.
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

### Independent memory-bound requests

```sh
make -C testing clean
BSG_TRACE_TIMEOUT_S=900 make -C testing run-mt_independent_requests_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

Reuse the unchanged traced hardware model, or build it first as described above.
Each trial completes 64 dependent loads in each of two independently randomized
pointer chains and checks both order-sensitive digests. The three modes are:

- **Sequential:** finish one request's chain, then the other; no OS scheduling cost.
- **Batched:** one instruction stream issues both ordinary loads before consuming
  their results. This is a current-hardware reference, not an idealized machine
  capable of ten simultaneous prefetches.
- **Resident:** each handler loads, yields directly to its peer, then consumes
  the result on resumption. Both handlers and all 130 timed handoffs finish
  before the ending counter read; no separate scheduler context is required.

The resident mode includes fixed cooperative round-robin control, not a Linux
thread pool or general-purpose scheduler. All modes include the same per-load
checksum work and use physical-cycle CSR `0xCC0`; setup, printing, and collection
of the already-complete second digest are excluded. Common full-ring cache
preconditioning follows mode-specific setup, and trial order is reversed for
the second repetition.

The hot case touches 16 cache lines (1 KiB). The pressure case touches 256 lines
(16 KiB) across a 64 KiB span, with sixteen lines per selected eight-way D-cache
set; the chains use disjoint sets. This is synthetic conflict pressure, not a
uniform capacity or DRAM-latency test. Validate timed miss counts and critical
word/full-refill latencies from the closed waveform before interpreting ratios.
No unrelated arithmetic worker or prefetch instruction is used.

Data IDs are `0=hot/hot`, `1=pressure/pressure`, `2=pressure/hot`, and
`3=hot/pressure`, in handler A/B order. Hot A/B use sets 1/2 modulo eight,
disjoint from pressure A/B's sets 0/4, so the mixed cases do not accidentally
evict the hot handler's ring. Mixed preconditioning traverses 128 steps in
both rings (sixteen laps of the eight-node hot ring). There are two reversed
order repetitions per mode and data case, plus three checked warmups.

Verified four-case simulation on RTL `1b9e611d4`, two resident/four logical contexts,
`TRACE=1` (2026-09-06), total cycles for both 64-load chains:

| Data | Sequential | Batched ordinary loads | Resident handlers |
| --- | ---: | ---: | ---: |
| Hot | 1,057 / 1,057 | 924 / 920 | 1,693 / 1,689 |
| Set pressure | 7,295 / 7,295 | 7,298 / 7,298 | 7,326 / 7,325 |
| Pressure / hot | 4,166 / 4,166 | 3,650 / 3,650 | 3,685 / 3,685 |
| Hot / pressure | 4,156 / 4,156 | 3,650 / 3,650 | 3,672 / 3,668 |

All checks and guest PASS succeed (known post-PASS GPIO teardown assertion).
Counter intervals match waveform cycles exactly; every interval commits 128
digest updates, and resident intervals commit 130 handoffs. Every pressure
trial accepts 128 misses, each with an 11-cycle critical-word response and
53-cycle full refill, with no overlapping accepted ring misses. Sequential
and batched timers end after consuming the final result but 24 and 21 cycles
before its full refill ends; resident timing includes that tail. Hot trials
have no ring misses. These original two cases exactly reproduce the previous
two-case run at top `4ef915ac`, despite the hot-layout adjustment.

The mixed cases each have 64 misses from the pressure chain and zero from the
hot chain, with the same 11/53-cycle response/refill latencies in every mode.
Resident switching saves **11.5–11.7% of cycles (about 1.13× throughput)** and
comes within 1% of batching. Waveforms show the other handler's digest commits
during at least 63 of 64 refill intervals, but none before the requested word
arrives in the resident mode: this hides refill-tail stalls, not simultaneous
DRAM accesses. Every demanded result and digest completes inside timing;
some final refill tails finish afterward (1–5 cycles for hot/pressure resident,
16–21 for mixed batching, 24 for hot/pressure sequential).

There is **no gain when both chains miss**: switching is about 0.4%
slower than sequential, and even batching cannot overlap those fetches. The
current D-cache gates requests on `is_ready`, leaves that state on a blocking
request, and waits for `complete_recv` before accepting another miss
(`import/black-parrot/bp_be/src/v/bp_be_dcache/bp_be_dcache.sv`, request gating
and state machine). This test is a reusable baseline for a future memory-level
parallelism change, not evidence that the intended prefetch/yield application
speedup is already achieved. Evidence, exact ELF/NBF and closed waveform:
`logs/mixed-requests-benchmark-20260906/` (original two-case evidence remains
in `logs/independent-requests-benchmark-20260906/`). All three warmups and 24
measured checks pass; no RTL, Linux, or FPGA change was made.

Two concurrent demand misses are not a configuration-only extension: D-cache
has one descriptor and partial-fill tracker, `bp_uce.sv` waits for a complete
read response, and the L2 slice uses blocking `bsg_cache`. A future experiment
must preserve response/thread ownership and nonresident drain, and prove a
second request is accepted before the first completes. Queuing a second L1
request alone is not proof of concurrent DRAM fetches or acceptable FPGA fit.

### Equal-work pointer traversal and computation

```sh
make -C testing clean
BSG_TRACE_TIMEOUT_S=600 make -C testing run-mt_pointer_compute_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

Reuse an already verified, unchanged traced model; otherwise clean/rebuild the
model first as above. Each measured trial performs 64 dependent pointer loads
with an order-sensitive digest and 512 independent xorshift rounds. Modes are
0 (separate sequential loops), 1 (single-thread fused load/compute/consume), and
2 (load/switch/compute/switch/consume using resident contexts 0 and 1).

Data case 0 is an eight-node, 512-byte hot ring. Case 1 deliberately uses 128
nodes spaced 512 bytes apart: an 8 KiB cache-line footprint within a 64 KiB span,
competing for eight D-cache sets. This is synthetic conflict pressure, not a
claim that uniformly distributed 8 KiB data exceeds the 32 KiB D-cache. Every
trial receives a full untimed ring pass after context setup; trial order is
0,1,2,2,1,0 to expose order effects. Instruction paths are warmed first.

Timing uses physical CSR `0xCC0`, includes loop/call/switch overhead, and ends
after both useful computations finish; setup, preconditioning, final result
collection, and output are excluded. Both digests must match in every trial.
Compare raw total cycles and observed misses, not just switching overhead.
The fused control matters: gains over separate loops alone do not demonstrate
an advantage over compiler/programmer-managed same-thread overlap. No prefetch
opcode, OS scheduling, nonresident eviction, or realistic-application claim is
part of this benchmark.

Initial verified simulation results (two reversed-order trials, unchanged RTL
`1b9e611d4`, two resident/four logical contexts):

| Total cycles for 64 walk steps + 512 mix rounds | Sequential | Fused single thread | Resident switching |
| --- | ---: | ---: | ---: |
| Cache-hot | 3,748 | 3,615 | 4,370–4,374 |
| Sparse cache pressure | 6,864 | 3,885 | 4,971–4,977 |

Both digests pass for all trials. Traces show zero timed ring misses in the hot
case and exactly 64 in every pressure trial: requested data arrives 11 cycles
after miss acceptance, full refill finishes at 53. Resident computation overlaps
all 64 full refills, but not their earlier critical-word arrivals; the sequential
case overlaps only its final refill with computation. Thus resident switching
improves this synthetic case by 1.38× over separate loops, but loses to explicit
single-thread fusion and is slower on hot data. This is not an FPGA/Linux or
DRAM-latency measurement. Evidence: `logs/pointer-compute-benchmark-20260906/`.

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

For faster extraction of the same events from a closed FST, use:

```sh
python3 tools/load_switch_fst_events.py path/to/archived/dump.fst \
  --pc <load-PC> --pc <target-PC>
```

This masks unrelated signals before decoding and reuses the same event parser.
The first invocation builds a small helper against the installed Verilator
FST library using GCC/G++ and zlib; subsequent invocations reuse an ignored,
locked build cache. Its events were byte-compared against full `fst2vcd` output.

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
