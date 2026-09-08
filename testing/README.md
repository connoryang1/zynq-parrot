This directory contains the active bare-metal tests for resident and SRAM-backed nonresident context switches. Use this guide for the accepted two-resident/four-logical configuration; older scale experiments and measurements remain in the historical Git checkpoint.

# Tests

Bare `make -C testing` shows help; cleanup must be requested explicitly.
The harness defaults to the accepted two-resident/four-logical topology.
`make -C testing check-harness` checks the simulator verdict logic and stale-artifact
guards. `python3 -B tools/test_ctxtsw_vcd_stream_events.py` checks that waveform
reports distinguish logical contexts from physical register banks.
Each selected test ELF is rebuilt to match the requested topology/compiler flags.
The runner clears old transcripts before building and requires fresh guest and
host PASS markers and the selected program's completion marker before CORE PASS,
rejecting timeouts and unrelated assertions even after PASS.

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
| `mt_csr_isolation_test` | First-seed CSR inheritance, independent `mscratch`, and NPC reseed preservation |
| `mt_frf_isolation_test` | Resident floating-point register isolation; not nonresident FP preservation |
| `mt_abi_preservation_test` | Live `gp` and callee-saved integer registers across a resident round trip |
| `mt_ctxtsw_register_target_test` | Fresh computed targets and returns after ALU/load/multiply/divide/CSR producers, including same-context writes and SRAM restores |
| `mt_ctxtsw_late_wb_hazard_test` | A source-context late writeback must not clear a target-context scoreboard hazard |
| `mt_ctxtsw_load_overlap_test` | Delayed source load and faulting byte-load-ahead preserve data and private registers across resident switching; timing requires its trace |
| `mt_ctxtsw_gpr_ring_stress` | Six live GPR sentinels survive peer overwrites; all three peers record their logical IDs |
| `mt_ctxtsw_pure_ring_stress_test` | Eight consecutive switches per context, followed by a lap verifying every peer completed |
| `mt_umode_resident_sv39_data_handoff_test` | First resident initialization, cold translated fetch/data, U-mode traps, and private GPR state |
| `mt_umode_nonresident_handoff_test` | U-mode SRAM-backed handoff without translated fetch |
| `mt_umode_nonresident_sv39_handoff_test` | U-mode handoff with translated instructions |
| `mt_umode_nonresident_sv39_data_handoff_test` | Translated instructions/data and target replay recovery |
| `mt_ctxtsw_nonresident_overhead_benchmark` | Matched global-cycle rings, with untimed completion checks for both peers |
| `mt_load_ahead_benchmark` | Serial, same-context load-ahead, and resident schedules with/without load-ahead; equal useful demand loads and arithmetic, verified data/peer completion |
| `mt_request_interleave_benchmark` | Two independent resident request streams, matched no-prefetch handoff and batch2 controls; shuffled first-touch lines, per-worker counts/checksums and final drain |

These 18 programs retain distinct state, hazard, redirect, and memory-scheduling checks.
The two Sv39 handoff variants include the base handoff source, keeping the
instruction-only and instruction/data cases comparable without duplicate tests.
Each variant emits its own completion marker, and unexpected traps invalidate
the result even if the round-trip checks had already completed.
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

The load-ahead experiments use ordinary `lbu x0` on valid cacheable data. This
can warm a line without a destination register; it still performs translation,
can fault, and must not be used on MMIO as a harmless hint. No new prefetch ISA
instruction or additional outstanding-miss capacity is implemented.

`mt_ctxtsw_load_overlap_test` verifies eight distinct cold lines for each of
delayed `ld a5` and discarded `lbu x0`, after separate instruction-path warmups.
Peer arithmetic uses the same architectural register as the delayed source
load to check bank ownership. Its PASS verifies values, identities, and return;
it does not by itself prove that the peer ran before a refill.

Stream its closed FST through `tools/cache_overlap_vcd.py`. Use `nm -n` on the
exact ELF to locate `input` and `overlap_peer_work`; measured delayed-load lines
start at `input+64`, and load-ahead lines at `input+576`. `--address` identifies
the first physical cache line, `--span-lines 8` selects the series,
`--target-pc` identifies the useful peer instruction, and `--target-thread 1`
selects its physical bank. `--require-overlap` requires architectural retirement
strictly before the critical data beat; `--require-full-refill-overlap` checks
retirement before full-line completion. Each gate requires at least one proven
request, so inspect the per-request results to qualify a whole series.
The analyzer samples stable values before BE rising edges and rejects missing
or ambiguous required signals. Run its host controls with
`python3 -B tools/test_cache_overlap_vcd.py`.

`mt_load_ahead_benchmark` uses 16 separate initialized 64-byte lines per mode,
one useful demand byte load and 64 dependent additions per line. Only ahead
modes pay for the extra discarded load. Each mode has distinct, initially
untouched data; warmups use a separate region. All four modes warm before any
measurement, with a fixed measurement order. Peer setup, final checksum/count
checks, fences, and console output are outside the global-counter intervals.
Resident modes include two switches per line and peer loop bookkeeping.
These are small scheduling measurements, not a random-access application or
evidence of multiple concurrent misses. The peer performs arithmetic, so this
does not test workers taking turns prefetching their own independent requests.
The required OS-thread baseline, batched ideal, and prefetch/yield/load schedule
are specified in [the application experiment](../PAPER_DIRECTION.md#matched-application-experiment).
Retain exact ELF and board/simulator
identities; do not compare their raw totals as identical-binary results.

`mt_request_interleave_benchmark` tests independent memory requests without
arithmetic padding. Each worker owns alternate entries of a fixed 64-line
permutation, starts one faulting load-ahead operation, yields, then consumes
that request on resumption. The resident control removes only load-ahead;
batch2 prepares and preloads both addresses before consuming either. Each mode
consumes 64 useful loads, with separate per-worker checksums (1076 and 1004)
and counts. The ring explicitly drains the peer's last load and records its
context ID. It performs 66 switches, including priming and draining.

One untimed warmup per mode uses separate data. Three measured trials rotate
mode order and use disjoint NBF-initialized pages with identical values and
request order. The printed rows are raw `0xCC0` cycles in control/batch2/ahead
order. Resident intervals include final peer result publication and return;
batch2 publishes its results after stopping the counter. Do not attribute the
entire batch-to-ring difference to cache behavior or isolated switch cost.
This first-touch mechanism test does not measure Linux scheduling; that
comparison is specified in [the application experiment](../PAPER_DIRECTION.md#matched-application-experiment).

To check actual request admission, obtain `request_data` and
`request_peer_prefetch` addresses from the exact traced ELF. Each
`request_data[sample][mode]` occupies 4096 bytes (sample 0 is warmup; modes
0/1/2 are control/batch2/ahead). Stream the closed waveform through:

```sh
fst2vcd path/to/dump.fst | python3 -B tools/request_overlap_vcd.py \
  --address <selected-page-address> --span-lines 64 \
  --target-pc <request_peer_prefetch-address> --target-thread 1 \
  --expected-requests 64 --require-serialized
```

The last option asserts serialized admission for the current single-miss RTL;
it does not establish an improvement. The report separates attempted peer
instruction dispatch from accepted cache requests and critical/full refill
boundaries. It rejects incomplete evidence and conflicting untagged refills;
hardware with multiple outstanding requests will need transaction-aware analysis.

The 46-case register-target regression fails on RTL `1b9e611d4` and passes on
`6c97bcc0a` with the same executable. Its scoped fix waits for same-bank GPR
writeback before classifying a register-form switch; immediate targets are
unchanged. Both simulator and FPGA regression evidence, plus the accepted Linux
and performance gates, are recorded in [the checkout guide](../CURRENT_CHECKOUT.md).

A nonresident result requires `NUM_CONTEXTS > NUM_THREADS`; all-resident
topologies do not test SRAM eviction. Maintained nonresident gates enforce the
accepted `NUM_THREADS=2 NUM_CONTEXTS=4` configuration. The benchmark reports amortized
cycles/switch, not an isolated redirect latency. Use `0xCC0` across contexts;
context-restored `mcycle` is not a physical elapsed-time counter.
The benchmark's warm/cold labels refer to resident/nonresident register state;
both rings have untimed warm-ups. They do not measure cold instruction/data
caches. The reported nonresident-minus-resident increment may be negative. Peer
completion checks happen after the stop counters. Although the timed loop
instructions are unchanged, the hardened benchmark is a new ELF; retain its
identity rather than calling it an identical-binary comparison with older runs.

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
