# Register Context Cache Plan

## Dirty FP Context Preservation (2026-08-24)

FP execution has been restored while preserving the established integer-clean
context-switch path. Nonresident FP state is saved two registers per cycle and
restored one register per cycle, but only for registers whose recoded value
differs from the crt0 initial FP state. The crt0 `fmv.s.x fN, zero` sequence
therefore leaves an integer-only context clean instead of falsely forcing a
32-register FP scan.

BlackParrot checkpoint `7938359e` passes clean/incremental `TRACE=1` runs of
the nonresident FP target test, the repeated contexts 0/2/3 FP eviction ring,
the integer-only nonresident overhead benchmark, late-writeback hazard, ABI
preservation, and resident FP-register isolation. The clean benchmark is
unchanged at 5.12 resident and 12.15 nonresident cycles/switch (7.03 cycles of
matched nonresident increment).

The eight-live-FP-register stress benchmark emits simulator-global marker
pairs because per-context CSR restoration virtualizes `rdcycle`. With the
accepted one-port restore, its steady warm interval is 23,436 cycles and its
cold interval is 28,692 cycles over 256 switches: 91.55 and 112.08
cycles/switch including the FP verification workload, or a 20.53-cycle cold
minus warm increment. The preceding two-write-lane experiment measured 108.09
cold cycles/switch, so serializing restores costs about 3.98 cycles/switch for
this eight-live-register workload and does not affect the integer-clean path.
Waveform analysis over 1,534 switches agrees: resident switches reach the FE
queue / first useful dispatch in 4 / 5 cycles, while dirty nonresident switches
alternate between 25/26 cycles to the FE queue and 26/27 cycles to first useful
dispatch. All 361,989 measured I-cache fetches hit, so this difference is FP
state transfer rather than a cache-refill tail.

The preceding FP-execution-only top-level checkpoint `f7950fb` routed on the
PYNQ-Z2 with Vivado 2024.2 at WNS `+2.739 ns`, TNS `0`, 47,409 / 53,200 slice
LUTs (`89.11%`), 21,428 registers (`20.14%`), 80 block-RAM tiles (`57.14%`),
and 11 DSPs (`5.00%`). The two-write-lane dirty-copy checkpoint
`00a7259`/`4cc5bccf` was rejected after more than one hour in Vivado synthesis
timing optimization: the extra write port dissolved the FP RAM into registers
and made compilation pathological. It is recorded as failed job
`20260824T183043Z-00a7259`, not as an accepted implementation. A routed
implementation of the one-port checkpoint is required before FPGA deployment.

## Physical-Cycle FPGA Measurement (2026-08-23)

A core-wide 64-bit counter is now exposed through standard `rdtime` and the
read-only custom CSR `0xCC0`. It resets only with the core and is deliberately
absent from the virtual context image, so resident and evicted logical contexts
observe one monotonic physical timebase. The implementation is BlackParrot
commit `d65c820f`; the top-level CSR-test checkpoint is `323abe7`.

`mt_ctxtsw_nonresident_overhead_benchmark` now brackets equal 256-switch
resident (`0 <-> 1`) and nonresident (`0 <-> 2`) unrolled rings with CSR
`0xCC0`. Top-level commit `2179a69` also makes every FPGA nonresident target
compile as two physical threads and four logical contexts. This prevents
logical context 2 from silently becoming resident under the old four-thread
FPGA software default.

The exact PYNQ configuration simulator and the physical PYNQ-Z2 produced the
same totals:

| Metric | Total / x100 value | Cycles/switch | Meaning |
| --- | ---: | ---: | --- |
| Resident ring | `0x519`; x100 `0x1fd` | 5.09 | Raw steady-state software-visible spacing for 256 resident switches. |
| Nonresident ring | `0xc25`; x100 `0x4be` | 12.14 | Raw steady-state software-visible spacing for 256 SRAM-backed eviction/restores. |
| Nonresident minus resident | x100 `0x2c0` | 7.04 | Incremental nonresident cost in this matched benchmark shape. |

The board run reported `CORE[0] PASS`. These numbers do not replace the
waveform-derived redirect-to-first-useful-work result: that architectural
metric remains dominated by 12 cycles for nonresident switches and 5 cycles
for resident switches at the routed checkpoint. The benchmark instead proves
that the complete unrolled handoff stream sustains 12.14 physical
cycles/switch on the FPGA without relying on host markers or virtualized
`mcycle`.

The global-counter design routed for PYNQ-Z2 at top revision `323abe7` and
BlackParrot revision `d65c820f`. Independently verified routed artifacts met
timing at WNS `+1.283 ns`, TNS `0`, and used 47,518 / 53,200 slice LUTs
(`89.32%`), 21,427 / 106,400 registers (`20.14%`), 80 / 140 block-RAM tiles
(`57.14%`), and 11 / 220 DSPs (`5.00%`). Package SHA-256 is
`3997df39a9c80116de20f278702e65d649a2b1731819643b2f4f54415e96411d`;
bitstream SHA-256 is
`803ea2933043d26619e703bcdb793fc2afc7898e18edc23d077000a26455569b`.

Deployment exposed a legacy stem mismatch: the package contains
`black_parrot_bd_1.*`, while the board Makefile loads `blackparrot_bd_1.bit`.
Skill checkpoint `5a975c2` adds a guarded staging helper that detects the load
stem, copies BIT/HWH/MAP as one set, and verifies package, bitstream, and NBF
hashes before any privileged overlay load.

## Retirement-Bank Fix and Final Validation (2026-08-22)

Full-system FPGA-configuration simulation exposed a correctness bug that the
minimal model could not trigger: after a speculative handoff, the target FE
packet can still carry the old physical-thread metadata. The context-switch
retirement bookkeeping captured that stale packet field, so the CSR wrapper
could select the wrong per-resident-thread commit bank on a return switch. The
fix captures the architectural `current_physical_thread_id_lo` instead. It adds
no state-machine phase and no context-switch cycles.

- Top-level functional checkpoint: `21dd6bf`
- BlackParrot checkpoint: `c20c7a466bf16471fc718db41dbac1daa5fcdf53`
- Clean traced gates: smoke PASS, late-writeback hazard PASS, nonresident target PASS
- Exact `e_bp_unicore_zynqparrot_cfg` model: resident `0->1->0` and nonresident
  SRAM-backed `0->2->0` staged probe PASS
- Waveform result over 1,023 switches: resident dominant 4 cycles to FE / 5 to
  first useful dispatch; nonresident dominant 11 cycles to FE / 12 to first
  useful dispatch
- I-cache result in the measured window: 78,213 fetches, 100% hits; cold/abort
  tails remain reported separately from the steady context-switch overhead

The FPGA test-image flow now rebuilds only the DRAMFS startup object without
optional FPU register initialization and packages NBFs with the required config
and debug preamble. This keeps the integer-only PYNQ-Z2 configuration usable
without turning floating-point support into an optimization dependency.

The optimized pre-fix bitstream passed the current-toolchain board smoke test
(`CORE[0] PASS`) but reproduced the staged probe's expected failure signature:
integer startup printed `AB`, then the first context-switch round trip stalled.

The retirement-fix implementation routed successfully as FPGA job
`20260822T162606Z-cad5f89`:

- routed WNS `+1.482 ns`, TNS `0.000 ns`
- 47,555 / 53,200 slice LUTs (`89.39%`)
- 21,361 / 106,400 slice registers (`20.08%`)
- 80 / 140 block-RAM tiles (`57.14%`)
- 11 / 220 DSPs (`5.00%`)
- packed artifact SHA-256
  `c987c77f65da3db6852972187464846ccafde7425788640597b9d9cc4e6af4df`
- bitstream SHA-256
  `54791ec50e74974e75221347f320e4c3cc027718785b2300f6069a975bc0f4c2`

That exact bitstream was checksum-verified after extraction and programmed on
the PYNQ-Z2.  The fence-free staged probe printed `ABRrNP`, reported
`CORE[0] PASS`, and exercised both the resident `0->1->0` round trip and the
nonresident SRAM-backed `0->2->0` round trip on hardware.  The run retired
6,989 instructions with an MTIME delta of 1,351 (MTIME is one eighth of a BP
cycle in this host report).

An intermediate `ABR1` probe was not a valid return-switch localization: its
`1` marker was followed by a host-MMIO `fence rw,rw` before the return CSR, so a
stall there could be in the fence/drain path.  Removing target-entry host I/O
and fences restored the intended pure-control test.  Board validation also
requires a normal `control-program` build without the checkout's unconditional
`DRAM_TEST`; that diagnostic path exits after the 64 MiB L2 write and never
loads the NBF.

## PYNQ-Z2 Deployment Attempt (2026-08-18, invalidated)

The board-side flow successfully ran `hello_world.nbf`, verified the ARM GP0
register connection, loaded 3,212 NBF lines, printed `Hello World!!!`, and
reported `CORE[0] PASS`. This result was later invalidated as validation of the
optimized checkpoint: `make unpack_bitstream` did not refresh the already
unpacked collateral, and the programmed `blackparrot_bd_1.bit` retained a
January 2025 timestamp. The accepted package contains an August 17, 2026
bitstream with SHA-256
`1b3680283fdfa631e7ac7276b69019aa4b6bec40eab67585e92963ee6da2f8d1`.

- Top-level revision: `ac256e689f656db010fd20719c1daa50cf7017ed`
- BlackParrot revision: `12fc8983a2b63243b86e878fce4f4f0935a1801b`
- FPGA job: `20260818T015748Z-6986071`
- Artifact SHA-256: `c7f1fc0ccc1975c93fb095148ba82e2396dcbe3ea670a5e7a5d9c31101c0e0cf`
- Board/configuration: PYNQ-Z2, Vivado 2024.2, `e_bp_unicore_zynqparrot_cfg`
- Result: old-image board runtime PASS; optimized-image hardware validation pending

Do not use this run as evidence that the optimized context-cache RTL works in
hardware. Force extraction of the accepted package, verify the unpacked `.bit`
checksum, and then rerun `hello_world` and the staged context-switch probe.

## Current Implementation Status (2026-08-16)

Branch `ctxtsw-context-sram` again has genuinely bounded GPR residency: two
physical integer-register banks serve the two hardware slots, while logical
context images live in a dedicated private context store. The store is
write-through, so ordinary writeback and CSR remote writes keep each logical
image current and eviction requires no save scan. A nonresident miss restores
the incoming 32-register image as two synchronous 16-register lines before
installing its saved NPC/privilege/translation/CSR metadata and redirecting FE.

The physical register file is partitioned into sixteen 64-bit lanes. Each lane
has the normal scalar write path and one restore write, avoiding synthesis of a
single array with sixteen arbitrary write ports. This preserves capacity
separation: increasing logical contexts grows the dense backing store, not the
number of pipeline-facing GPR banks.

Nonresident FP copying is explicitly disabled for this GPR-only configuration;
ordinary resident FP execution remains enabled and passes the clean traced FP
register-isolation test. CSR and execution metadata remain virtualized.

The current checkpoint is verified by clean `TRACE=1` runs of the nonresident
overhead benchmark, nonresident ring test, and late-writeback hazard test, plus
waveform analysis of 1,024 architectural context switches. Early backing-store
reads now overlap the architectural commit/drain wait, reducing the dominant
nonresident path from 13 to 12 cycles/switch without installing speculative
state. Routed FPGA fit remains the active acceptance gate.

## Context-Switch Timing Record

Use global simulator cycles for nonresident timing. `rdcycle` is virtualized
per logical context and is not a wall-clock timer while a context is evicted.

| Configuration | Result | Evidence / interpretation |
| --- | ---: | --- |
| Original resident-only Banyan path | 7 cycles/switch | Original minimal resident warm path; not a nonresident result. |
| Current ISD-forwarded resident path | about 4 cycles added overhead | Best-case warm/steady result: redirect begins when ctxtsw reaches ISD, before architectural commit. |
| Original serialized Dcache GPR service | 203.64 global cycles/switch | `52131 / 256` in the 2026-07-18 global-marker run. Each switch serialized 34 64-bit Dcache requests/responses. |
| Dedicated context memory, one GPR restore port | Absolute cold cost not yet re-baselined | Functional checkpoint. It removes the normal-Dcache transaction dependency and restores from a four-line local buffer. |
| Dedicated context memory, two GPR restore ports | 15 global cycles saved per cold switch vs. one-port dedicated restore | Two otherwise-identical traced runs differed by 7,680 global cycles. Only the two 256-switch cold phases use this path: `7680 / 512 = 15`. |
| Dedicated context memory, two GPR save and restore ports | 66.59 global cycles/switch added over resident control | Direct clean `TRACE=1` measurement: resident markers `0xb1 -> 0xb2` span `31938 / 256 = 124.76` cycles/switch; cold markers `0xc1 -> 0xc2` span `48984 / 256 = 191.34`; `191.34 - 124.76 = 66.59`. |
| Dedicated context memory, GPR-only mode | 41.09 global cycles/switch added over resident control | Clean `TRACE=1` measurement with nonresident FP copy disabled: cold markers span `42456 / 256 = 165.84`; `165.84 - 124.76 = 41.09`. |

The historical serialized-Dcache measurement is not a same-build baseline for this
marker interval, so it cannot be subtracted from the current result. The prior
controlled deltas still attribute 15 cycles to the second restore lane and 11.50
cycles to the second save lane across their respective builds. Measure save/restore
state-machine residency before assigning the current 66.59-cycle added cost to
individual states or comparing it to the old Dcache path.

The benchmark writes host signal markers `0xb1`/`0xb2` around `t0_warm_bench()` and
`0xc1`/`0xc2` around `t0_cold_bench()`. Under Verilator, `bsg_host` records the
simulator timekeeper cycle when each marker packet reaches the host. These are
host-observed whole-loop intervals, not virtualized `rdcycle` values.

### Current Dedicated-Memory Phase Accounting

A clean traced run instrumented the nonresident FSM without changing its
functional inputs or outputs. All 512 cold switches had one of two steady-state
profiles, alternating by direction:

| Direction class | Count | Saved dirty GPRs | Restored GPRs | FSM cycles |
| --- | ---: | ---: | ---: | ---: |
| Full-save direction | 256 | 31 | 31 | 45 |
| Partial-save direction | 256 | 17 | 31 | 38 |

The components of those 45 / 38 cycles are respectively:

| Phase | Full-save | Partial-save | Notes |
| --- | ---: | ---: | --- |
| Wait for `commit_pkt.ctxtsw` | 3 | 3 | The miss cannot repurpose its resident slot before the switching CSR retires. |
| Drain | 2 | 2 | The existing safe-to-evict predicate must observe an empty/no-writeback backend. |
| Two-lane GPR save | 16 | 9 | `ceil(31/2)` or `ceil(17/2)` existing physical-regfile read lanes. |
| Four-line context-memory fetch | 5 | 5 | Four back-to-back synchronous line requests plus response visibility. |
| Two-lane GPR restore | 16 | 16 | `ceil(31/2)` physical-regfile write cycles. |
| FSM tails | 2 | 2 | The registered transition to launch. |
| FE accept handshake | 1 | 1 | `fe_ctxtsw_yumi_i`. |

In GPR-only mode, the full miss-to-launch spans are `45` and `38` cycles, with a
fixed five cycles from FE acceptance to the first target-context BE dispatch.
The average miss-to-launch time is `41.5` cycles, consistent with the measured
`41.09`-cycle cold-vs-resident loop increment. The earlier `66.59` result had
also run the pre-existing FP save/restore phase, contributing 32 or 17 cycles
per direction; it is retained above as a separate full-state historical result.

### Optimization 1: Parallel GPR Eviction and Installation (2026-08-07)

The outgoing physical-regfile reads/context-memory writes now run concurrently
with incoming physical-regfile writes after the four restore lines arrive. The
integer regfile already has independent two-lane read and write paths, so this
does not add ports.

A clean 2-resident/4-context `TRACE=1` run of
`mt_ctxtsw_nonresident_overhead_benchmark` passed, followed by a clean traced
`mt_ctxtsw_nonresident_ring_test` integrity pass. Waveform analysis over 511
switch intervals measured:

| Metric | Serialized baseline | Parallel save/restore |
| --- | ---: | ---: |
| Steady partial-save direction, first useful dispatch | 34 cycles | 32 cycles |
| Steady full-save direction, first useful dispatch | 48 cycles | 32 cycles |
| Dominant steady bucket | split: 222 at 34, 233 at 48 | 455 at 32 |

Cold-I-cache/refill outliers are excluded from those steady buckets and remain
separately visible in the waveform histogram. The remaining 32-cycle path is
now dominated by the two-register-per-cycle restore width plus fixed
commit/drain/launch latency; it is the next optimization target.

### Optimization 2: Atomic Physical-Bank Exchange (2026-08-08)

Because the dual-write physical GPR file already synthesizes as an explicitly
written array, the nonresident path now exposes a drained whole-bank exchange:
the victim bank is masked into the private context store while the target image
is installed under the union of victim/target dirty masks at the same edge.
This removes the remaining serial register loop without changing the resident
context-switch path.

Clean `TRACE=1` evidence on the 2-resident/4-context model:

| Gate / metric | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS |
| Steady first useful target dispatch | 478/511 at 12 cycles; 10/511 at 13 cycles |
| Steady next-context-switch throughput | 470/511 at 12 cycles |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS |
| `mt_ctxtsw_late_wb_hazard_test` (2 slots / 4 contexts) | CORE/BSG PASS |
| `mt_ctxtsw_smoke_test` resident regression (2 / 4) | CORE/BSG PASS |
| `mt_ctxtsw_nonresident_gpr_overhead_benchmark` | CORE/BSG PASS |

For the GPR stress benchmark, the host-observed resident marker interval is
`31938 / 256 = 124.76` cycles/switch and the nonresident interval is
`34134 / 256 = 133.34`, an `8.58` cycle loop-level increment. That loop delta
is distinct from the primary waveform metric: the architectural nonresident
redirect reaches the first useful target dispatch in the dominant 12-cycle
bucket. Longer 68--118-cycle observations correlate with frontend
abort/refill tails and are not register-transfer latency.

### Optimization 3: Virtual-Context Integer Register File (2026-08-14)

The integer register file is now indexed by virtual context rather than by the
smaller set of physical resident slots. This removes the physical-bank/shadow
image GPR transfer entirely. The nonresident FSM still waits for architectural
commit and a safe backend drain, updates the virtual-context slot mapping and
metadata, preserves an ordering tail, and launches the normal FE redirect.

A fresh from-scratch `TRACE=1` build is required for this checkpoint. An older
preserved waveform had been produced with reused generated hardware and mixed
resident and nonresident observations; it is retained only as stale-artifact
evidence and is not used for the current claim. The clean current waveform over
1,023 intervals reports:

| Path / metric | Result |
| --- | ---: |
| Resident first useful dispatch | 502 intervals at 4 cycles |
| Nonresident first useful dispatch | 478 intervals at 12 cycles; 10 at 13 cycles |
| CTXT dispatch to architectural commit | 1,023 intervals at 3 cycles |
| Frontend abort/refill tails | 33 intervals, 60--118 cycles to first dispatch |
| I-cache fetches in measured window | 77,337 / 77,337 hits; no classified misses |

The dominant nonresident accounting is three cycles from CTXT dispatch to
commit, approximately six cycles from commit through drain observation,
mapping/metadata installation, ordering, FE launch, and target FE-queue
arrival, then three cycles from FE-queue arrival to first useful BE dispatch.
The unified register file therefore removes transfer hardware and storage
crossbars without reducing the already fixed 12-cycle architectural path from
the atomic-bank checkpoint. It should not be reported as a 12-to-4-cycle
nonresident speedup; the 4-cycle bucket is resident switching.

This checkpoint was subsequently rejected as the final architecture. It
allocated one complete pipeline-facing GPR bank per logical context, so its
12-cycle result removed the capacity-cache property rather than implementing a
scalable resident/nonresident store. It remains useful only as the measured
control-only lower bound.

Clean acceptance gates for the final RTL checkpoint:

| Gate | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS, 4,021 retired |
| `mt_ctxtsw_late_wb_hazard_test` | CORE/BSG PASS, 5,402 retired |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS |
| Warm benchmark interval | `0x421 / 256 = 4.12` cycles/switch; not a nonresident-only latency |

The PYNQ-Z2 implementation at top revision `2686658` and BlackParrot revision
`02fccc8a` placed and routed at 51,398 / 53,200 LUTs (96.61%) with WNS
`+1.759 ns` and TNS `0`, but bitstream generation correctly failed on Vivado
`LUTLP-1`, a context-redirect/I-cache/UCE combinational-loop DRC. The forced
request acceptance rewrite at top revision `021230c` / BlackParrot `8deb7016`
also routed but failed the same bitstream DRC in FPGA job
`20260814T213419Z-021230c`. BlackParrot revision `af19f5e0` held the
speculative TV stage flushed for the entire pending redirect and passed clean
traced ring and late-writeback tests, but FPGA job
`20260815T222727Z-fb55152` proved that the broader `e_resume` acceptance path
still contained the same FE/I-cache/UCE feedback loop. Revision `e47c3b5e`
forces I-cache acceptance in `e_resume`, making TL acceptance independent of
TV/controller state. This is the current structural loop fix; its routed DRC
result is still pending.

### Optimization 4: Write-Through, Synchronous SRAM Lines (2026-08-15)

BlackParrot revision `fb987b60` restored two physical GPR banks and the active
dedicated context store. Revision `a24d2711` made that store write-through,
eliminating outgoing save traffic. Revision `b945330f` replaced the
non-synthesizable one-edge 2,048-bit exchange with four synchronous 512-bit
restore lines. Its clean benchmark waveform measured a dominant 16-cycle
nonresident first dispatch and next-switch interval, exactly four cycles above
the rejected atomic/control lower bound.

Revision `3de88ae9` doubles the line to sixteen registers and banks the physical
register file by lane. Two synchronous 1,024-bit lines restore a context.
Revision `056da4f5` removes the now-redundant restore tail: the final line is
written on the edge that enters FE launch, so the redirect cannot expose
partial register state. Revision `be73b6e7` banks the dedicated backing store
into the same sixteen 64-bit lanes and replaces data-array reset with compact
valid bits, allowing each lane to infer as a one-read/one-write synchronous
RAM. Revision `e47c3b5e` adds the independent frontend resume-loop fix. Clean
acceptance evidence for the current checkpoint is:

| Gate / metric | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS, 4,021 retired |
| `mt_ctxtsw_smoke_test` | CORE/BSG PASS, 3,515 retired |
| `mt_frf_isolation_test` | CORE/BSG PASS, 13,358 retired |
| `mt_ctxtsw_late_wb_hazard_test` | CORE/BSG PASS, 5,402 retired |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS, 20,280 retired |
| Resident first useful dispatch | 502 intervals at 4 cycles |
| Nonresident first useful dispatch | 474 intervals at 13 cycles; 10 at 14 cycles |
| Steady next-context-switch throughput | 466 intervals at 13 cycles |
| CTXT dispatch to architectural commit | 1,023 intervals at 3 cycles |
| I-cache fetches in measured window | 78,253 / 78,253 hits; no classified misses |

The physical-register and backing-store banking refactors have identical
waveform histograms to their corresponding flat implementation, so neither adds
architectural latency. The live 14-cycle FPGA checkpoint already reports the
resident register file as sixteen inferred `4 x 66` distributed-RAM banks; the
current backing-store banking still requires its own routed checkpoint. No
final FPGA-fit claim is made until the routed reports and bitstream exist.

### Optimization 5: FPGA Block-RAM Mapping (2026-08-16)

The scalable two-slot design exceeded the PYNQ-Z2 LUT capacity because both the
sixteen-lane dedicated context store and the two-read physical GPR file mapped
to distributed RAM and surrounding LUT logic.  Each context-store lane now
requests block RAM.  Each physical GPR lane uses two mirrored one-read/one-write
block memories, one per architectural read port, with identical writes to both
copies.  This preserves the existing two-read/one-write interface and does not
add a register-transfer cycle.

A from-scratch `TRACE=1` Verilator rebuild and clean tests produced:

| Gate / metric | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS, 4,021 retired |
| `mt_ctxtsw_late_wb_hazard_test` | CORE/BSG PASS, 5,402 retired |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS, 20,280 retired |
| Resident first useful dispatch | 502 intervals at 4 cycles/switch |
| Nonresident first useful dispatch | 475 intervals at 13 cycles/switch; 10 at 14 cycles/switch |
| Steady nonresident next-switch throughput | 466 intervals at 13 cycles/switch |
| Sampled I-cache misses | 0 |

The prior accepted waveform had 474 rather than 475 intervals in the dominant
13-cycle first-dispatch bucket because of measurement-window classification;
the steady 466-at-13 next-switch bucket is identical.  Routed PYNQ-Z2 resource,
timing, and bitstream validation failed at placement for top revision `a492da0`
and BlackParrot revision `8097cb9c`: synthesis used 55,261 / 53,200 slice LUTs
(103.87%) and 89 / 140 block-RAM tiles (63.57%). The placer reported 64,751 raw
LUTs, 399 control sets, and 11,625 slices required with 11,165 available. This
proves the RAMs infer correctly, but the scalable checkpoint still needs an
independent area reduction before it fits the PYNQ-Z2.

### Optimization 6: Commit/Drain-Overlapped SRAM Prefetch (2026-08-16)

The two incoming SRAM lines are now requested immediately after a nonresident
miss is captured, while the switching instruction proceeds to architectural
commit and the victim backend drains. Responses remain in private line
buffers. The physical GPR bank is not modified until the existing drain-safe
predicate has been observed, after which the two lines are installed on two
successive clocks. This consumes the existing one-read/one-write context-SRAM
interface and adds no memory ports or register-file ports.

A from-scratch `TRACE=1` model rebuild and clean isolated runs produced:

| Gate / metric | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS, 4,021 retired |
| `mt_ctxtsw_late_wb_hazard_test` | CORE/BSG PASS, 5,402 retired |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS, 20,280 retired |
| Resident first useful dispatch | 502 switches at 4 cycles/switch |
| Nonresident first useful dispatch | 479 switches at 12 cycles/switch; 10 at 13 cycles/switch |
| Steady nonresident next-switch throughput | 470 intervals at 12 cycles/switch |
| Sampled I-cache misses | 0 |

The representative dominant path is: miss dispatch at cycle 0; SRAM line 0
request at +1; line 0 response and line 1 request at +2; line 1 response and
architectural commit at +3; drain observation at +4; line installation at +5
and +6; FE redirect acceptance at +7; and first useful target-context dispatch
at +12. Relative to Optimization 5, overlapping the two synchronous reads
removes exactly one cycle/switch from the dominant scalable SRAM-backed path.

### FPGA Fit Step: Integer-Only ZynqParrot Configuration (2026-08-16)

The failed scalable synthesis checkpoint was 2,061 slice LUTs over the PYNQ-Z2
capacity. A depth-30 hierarchical utilization report attributed 1,654 LUTs to
the FP FMA pipe, 1,262 LUTs to FP divide/square-root, and additional LUTs and
RAM to the FP register/control path. The context-switch workload and target
FPGA image are integer-only, so `fpu_support` is now zero in both ZynqParrot
configuration packages. Integer multiply/divide remain enabled. This is an
FPGA/configuration fit step, not a context-switch cycle optimization.

After a from-scratch `TRACE=1` rebuild, clean isolated validation produced:

| Gate / metric | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS, 4,021 retired |
| `mt_ctxtsw_late_wb_hazard_test` | CORE/BSG PASS, 5,402 retired |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS, 20,280 retired |
| Resident first useful dispatch | 502 switches at 4 cycles/switch |
| Nonresident first useful dispatch | 479 switches at 12 cycles/switch; 10 at 13 cycles/switch |
| Steady nonresident next-switch throughput | 470 intervals at 12 cycles/switch |
| Sampled I-cache misses | 0 |

The waveform histogram is identical to the FP-capable 12-cycle checkpoint, so
the area change adds zero cycles/switch. Routed implementation at top revision
`1c4d260` passed global placement but failed detail packing: 58,113 combined
LUTs and 24,397 FFs required 11,802 slices while 11,188 were available. Vivado
reported 401 control sets; the low FF count and excess combined LUT count show
that LUT/slice pressure, not register or BRAM capacity, remains the limiter.

### FPGA Fit Step: Single-Slice L2 (2026-08-16)

The PYNQ-Z2 unicore configuration now uses one L2 slice and one bank rather
than two of each. This matches the already verified minimal simulation
configuration and reduces replicated L2 control/data-path logic. It changes
aggregate L2 capacity/bandwidth, not the dedicated context SRAM, physical
resident-bank count, or context-switch handoff sequence, so its expected
context-switch cost is zero cycles/switch. `make -j24 prep_lite` and the FPGA
build-readiness audit pass.

Top revision `1341957` with BlackParrot revision `1af58ce5` synthesized,
placed, and fully routed. The placed image uses 47,638 / 53,200 slice LUTs
(89.55%), 21,323 / 106,400 slice registers (20.04%), 80 / 140 block-RAM tiles
(57.14%), and 11 / 220 DSPs (5.00%). All 73,981 routable nets are fully routed
with zero routing errors. Routed timing meets constraints with WNS +1.454 ns,
TNS 0.000 ns, WHS +0.026 ns, and THS 0.000 ns. Bitstream generation was blocked
only by DRC `LUTLP-1`, which found one nine-LUT combinational loop from frontend
context-redirect acceptance through the I-cache/UCE ready path.

### FPGA DRC Fix: Registered Frontend Redirect Slice (2026-08-16)

The BE-to-FE context redirect now crosses a one-entry registered ready/valid
slice. The frontend captures the NPC, physical thread, privilege, translation,
and ASID payload only after the BE has reached its launch point, holds it while
the I-cache is backpressured, and acknowledges I-cache acceptance separately.
This removes the routed ready-to-valid feedback without waiving the DRC or
exposing a nonresident redirect before register installation completes.

A direct valid/ready split was tested first and rejected: although functional
smoke tests passed, waveform analysis showed premature 4-cycle nonresident
redirects and 256 additional retired instructions. That experiment was fully
reverted before implementing the registered slice.

The registered slice passes a from-scratch `TRACE=1` model rebuild and clean
isolated gates: nonresident ring CORE/BSG PASS with 4,021 retired instructions,
late-writeback CORE/BSG PASS with 5,402 retired instructions, and the overhead
benchmark CORE/BSG PASS with 20,277 retired instructions. Waveform analysis of
1,023 switches reports zero sampled I-cache misses. Resident first-useful
dispatch moves from four to five cycles/switch (502 samples), while the primary
nonresident result remains twelve cycles/switch (474 samples; ten at thirteen)
and steady nonresident next-switch throughput remains dominated by twelve
cycles/switch (466 samples). A new routed implementation and packaged bitstream
are still required to prove that `LUTLP-1` is eliminated.

The routed PYNQ-Z2 implementation at top revision `13f996e` and BlackParrot
revision `41569c9b` proves that the registered redirect removed the earlier
BE-to-FE loop. It fits at 47,671 / 53,200 slice LUTs (89.61%), 21,368 /
106,400 registers (20.08%), 80 / 140 block-RAM tiles (57.14%), and 11 / 220
DSPs (5.00%). Routing completed with zero routing errors and met timing with
WNS `+0.434 ns`, TNS `0`, WHS `+0.023 ns`, and THS `0`. Bitstream generation
found one different nine-LUT `LUTLP-1` path through I-cache miss-abort
completion, SRAM arbitration, and UCE refill counters. Reports are preserved
under `logs/fpga/20260816T220048Z-13f996e/routed-reports/`.

### FPGA DRC Fix: Independent I-cache Abort Decision (2026-08-16)

BlackParrot revision `1f28f68f` first removed the abort-decision portion of the
feedback equation without buffering or prematurely accepting a refill packet.
The UCE already holds `cache_req_last_i` and its associated refill packets until
their SRAM handshakes complete, so the I-cache uses that held last-beat intent
only to decide whether a simultaneous frontend force should abort the miss.
Synthesis job `20260818T000026Z-422e84b` then localized a remaining timing loop
through `critical_recv`, tag-SRAM arbitration, and the UCE refill counters. The
job was stopped after synthesis reported the loop, before wasting a placement
run on a design that could not pass bitstream DRC.

BlackParrot revision `629a4757` gives a critical or final UCE refill beat
deterministic priority over a conflicting frontend SRAM access. Thus every
valid tag, data, and stat packet associated with the restart/completion event is
accepted in that same cycle, while ordinary non-event refill beats retain the
existing frontend-fast-path priority. The actual miss-to-recover transition
continues to use `complete_recv`; no response is buffered, replayed, or exposed
before its memory packets are applied.

Synthesis job `20260818T004321Z-2cc1d00` showed that this event-priority mux was
still not structurally acyclic: the UCE sideband selected the priority branch,
while the resulting yumi advanced the counter that generated that sideband.
That job was also stopped after the synthesis timing-loop report. BlackParrot
revision `12fc8983` removes the dependency completely. Any UCE memory packet
stalls the frontend cache pipeline for that cycle and is accepted
unconditionally; a simultaneous forced abort discards the packet while its tag
invalidation takes priority. Consequently critical/last are already aligned
accepted events and no SRAM availability signal feeds a UCE counter. This can
affect only cycles containing I-cache refill/maintenance traffic, not the hot
context-SRAM transfer path.

A combined response-buffer experiment was rejected before this change because
it reproduced the known premature-redirect signature: the tests completed, but
the benchmark retired 20,533 rather than 20,277 instructions. The independent
abort decision preserves the accepted architectural results:

| Gate / metric | Result |
| --- | ---: |
| `mt_ctxtsw_nonresident_ring_test` | CORE/BSG PASS, 4,021 retired |
| `mt_ctxtsw_late_wb_hazard_test` | CORE/BSG PASS, 5,402 retired |
| `mt_ctxtsw_nonresident_overhead_benchmark` | CORE/BSG PASS, 20,277 retired |
| Resident first useful dispatch | 502 switches at 5 cycles/switch |
| Nonresident first useful dispatch | 474 switches at 12 cycles/switch; 10 at 13 cycles/switch |
| Steady nonresident next-switch throughput | 466 intervals at 12 cycles/switch |
| Sampled I-cache fetches | 78,213 / 78,213 hits; no classified misses |
| I-cache data-select audit | 0 bad selections on hits |

A fresh PYNQ-Z2 implementation at top revision `6986071` and BlackParrot
revision `12fc8983` completed as FPGA job
`20260818T015748Z-6986071`. All routable nets were routed, bitstream
precondition DRC completed with zero errors, and the packaged
`black_parrot_bd_1.zynq.pynqz2.tar.xz.b64` artifact was produced. Final timing
is WNS `+2.341 ns`, TNS `0`, WHS `+0.025 ns`, and THS `0`. The placed image
uses 47,950 / 53,200 slice LUTs (90.13%), 21,368 / 106,400 registers
(20.08%), 80 / 140 block-RAM tiles (57.14%), and 11 / 220 DSPs (5.00%). No
`LUTLP-1` or timing-loop finding remains. The console log, packaged artifact,
summary, and preserved routed reports are under
`logs/fpga/20260818T015748Z-6986071/`.

### Cold-I-cache Overlap Assessment (2026-08-18)

`mt_ctxtsw_nonresident_cold_icache_benchmark` forces the two separately aligned
target loops cold with `fence.i`. A 128-instruction runway follows each fence so
cache maintenance is complete before the context-switch CSR dispatches; placing
the CSR directly behind `fence.i` was rejected because the waveform showed the
CSR dispatch while the fence transaction was still active, after which the CSR
never committed. The corrected four-iteration test produces eight alternating
nonresident switches and reaches CORE/BSG PASS with 8,191 retired instructions.

The clean `TRACE=1` baseline contains two cold-tail classes. With no stale
old-context miss, the target request starts 12 cycles after context-switch
dispatch, its critical beat arrives at +24, its final beat at +66, and the first
useful target dispatch occurs at +69 (four samples). When speculative
fall-through fetch has already started an old-context miss, abort begins at +9,
finishes at +59, the target request starts at +60, its final beat arrives at
+114, and first useful dispatch occurs at +117 (four samples). Context-switch
commit itself remains +3. Thus the accepted 12-cycle SRAM transfer floor is
unchanged; the additional 57 or 105 cycles are entirely single-MSHR frontend
abort/refill tails. The data-select audit found zero bad selections across
8,769 hit samples.

An isolated experiment asserted the existing architectural FE context redirect
immediately after context-switch commit and held backend issue suppressed until
the bank exchange completed. A clean traced run deadlocked after NBF load,
before the benchmark banner. The experiment was removed. The existing redirect
is therefore not a safe prefetch mechanism: it mutates FE context/predictor
ownership and participates in a handshake designed to coincide with state
installation.

A safe future implementation needs a separate, non-state-changing I-cache
prefetch request carrying target physical address/ASID/translation metadata,
plus cancellation and MSHR arbitration semantics. Given the observed refill
length and only four committed transfer cycles available for overlap, that is
not justified as part of this minimum-overhead checkpoint without a broader FE
prefetch design and dedicated correctness tests.

The existing critical-beat datapath was also tested as a narrower alternative:
allowing its snooped word through `hit_v_o` before the cache FSM reached
`e_ready` reduced the apparent tail but changed the known-good nonresident ring
from 4,021 to 4,071 retired instructions. That replay/duplication experiment was
fully reverted. A safe critical-word restart needs an explicit one-shot
ready/valid holding stage while refill continues; it is not a low-risk gate
change. A second MSHR could also avoid the 48-cycle stale-miss penalty, but at
90.13% LUT utilization it is a larger area/timing project requiring its own
routed checkpoint.

## Storage Clarification

The older RTL shadow image and the current `bp_be_context_mem` are *not* the
physical ISA register file. The physical active-thread GPR banks are implemented
by `bp_be_regfile_mt.sv` and are indexed by `{physical_thread_id, register}`.
Arrays such as `context_cache_int_shadow_r` and the `mem` array inside
`bp_be_context_mem` describe separate hardware storage for nonresident logical
contexts.

In RTL simulation, a `logic` array behaves like stored values. In synthesis it
may infer flops or a memory macro depending on the coding style, reset behavior,
and target technology. It does not silently reuse the processor's physical GPR
cells. The problem with the original design was primarily the serialized
64-bit Dcache save/restore protocol, not that the shadow array itself was a
physical regfile. The current private-memory module is an interface intended to
map to dedicated SRAM/BRAM later; its behavioral array is still a model, not a
PPA claim.

## Goal

Support more software-visible contexts than the number of physically resident hardware slots. The fast resident-hit path must preserve the current ISD-forwarding behavior. Resident misses are correctness-first: stall, save the evicted resident slot to a reserved cacheable memory image, restore the requested logical context into a resident slot, then resume through the existing context-switch redirect path.

## Current Branch Scope

The current `ctxtsw-regfile-caching` branch implements a restore-capable prototype:

- resident-hit ctxtsw remains on the existing fast path
- nonresident GPR state is saved to and restored from the reserved cacheable L1-backed image
- nonresident FP state is saved to and restored from an RTL shadow image, with two regfile
  scan lanes; it is not yet L1-backed
- logical NPC / privilege / translation-enable / ASID metadata is virtualized
- virtual CSR state is saved/restored on a resident miss

`mt_ctxtsw_nonresident_fp_ring_test` and `mt_ctxtsw_nonresident_fp_target_test` pass on
this branch. The implementation has not yet been validated for every CSR architectural corner
case, and restoring virtual `mcycle` means `rdcycle` is not a wall-clock performance metric
across a nonresident switch.

## Measured Nonresident Cost (2026-07-18)

The minimal nonresident benchmark was measured with global testbench cycle markers, rather
than `rdcycle`:

- resident `0 <-> 1`: `1053 / 256 = 4.11` global cycles per switch
- nonresident `0 <-> 2`: `52131 / 256 = 203.64` global cycles per switch

The apparent old `rdcycle` result of `3.55` cold cycles/switch is invalid. A nonresident
launch restores virtual CSR state, including `mcycle`, so each logical context excludes time
while the other context owns the resident slot.

Debug state accounting in the timed cold region establishes the steady-state alternating
directions:

| Direction | GPR dirty state at save/restore entry | GPR FSM cycles | FP FSM cycles | Approx. launch-to-launch cost |
| --- | --- | ---: | ---: | ---: |
| `0 -> 2` | save 31, target has 3 | 195 | 32 | 239 |
| `2 -> 0` | save 3, target has 31 | 139 | 17 | 170 |

Each direction has exactly 34 GPR L1 requests and responses: 31+3. The GPR path is serialized
because `bp_be_top.sv` allows one context-cache GPR request at a time, and
`bp_be_pipe_mem.sv` holds `context_cache_dcache_active_r` until that load/store responds.
The FP path does not issue these D-cache requests; it uses the direct two-lane regfile scan path.

This makes the first performance conclusion unambiguous: dirty-mask tuning cannot remove the
dominant cost for a context that genuinely owns a broad register image. A material improvement
requires a bounded multiword/line context-copy service or a distinct context-store interface.
Do not attempt to increase GPR scan picks alone: the D-cache service interface still permits only
one active 64-bit request.

## Starting Point

- The current optimized path is ISD forwarding for resident context switches.
- The current implementation has a resident map for already-resident logical contexts. Resident misses are detected and stopped in simulation; save/restore is not implemented yet.
- The intended experiment is to evaluate two resident slots with more logical contexts. The actual area/fmax benefit is unverified; `BANYAN_PARITY.md` marks current synthesis/PPA comparison as future work.
- This plan is for a new phase of work after the repo is cleaned. Keep it separate from unverified I-cache abort experiments.

## Verified RTL Facts

These are grounded in the current code and constrain the implementation:

- `thread_id_width_p` is derived from `num_threads_p`, while `context_id_width_p` is derived from `num_contexts_p` in `bp_common_aviary_defines.svh`.
- ISD CTXT decode now preserves the target as `context_id_width_p` through the dispatch/reservation path. `bp_be_top.sv` translates logical context IDs to physical resident slots and stops nonresident targets in simulation until the save/restore FSM exists.
- Existing context resume metadata is physically indexed by `thread_id` in `bp_be_top.sv`: NPC, privilege mode, translation enable, and ASID.
- Full CSR state is physically resident too: `bp_be_csr_wrapper_mt.sv` instantiates one `bp_be_csr` per `num_threads_p` and muxes outputs by `current_thread_id_i`.
- `commit_pkt.ctxtsw` is the architectural commit indication for a context switch. It is generated by `bp_be_csr.sv` as `retire_pkt_cast_i.instret & retire_ctxtsw_v_i`.
- The integer and floating-point regfiles are physically indexed by `{thread_id, reg_addr}` in `bp_be_regfile_mt.sv` and have one write port. Restore must not collide with normal writeback or CSR `rpush`.
- The detector scoreboards are already thread-tagged by physical resident slot. That is correct for resident slots, but it does not by itself prove a victim slot is safe to evict.
- Normal D-cache requests are formed inside `bp_be_calculator/bp_be_pipe_mem.sv` from a pipeline reservation and then passed to `bp_be_dcache.sv`. `bp_be_top.sv` only exposes the lower cache-engine interface, so a context-cache memory engine is not a trivial top-level request mux.
- Normal memory operations enter the D-cache through the DMMU in `bp_be_calculator/bp_be_pipe_mem.sv`. A context-service path that wants physical backing addresses must either disable translation for its generated request or bypass/supply translation explicitly.
- Existing software can remotely write another resident slot through CSR `0x083`, but no remote-read or `rpull` path exists in the current RTL/tests.

Concrete code references:

- `bp_common_aviary_defines.svh:53-56`: `num_threads_p`, `thread_id_width_p`, `num_contexts_p`, and `context_id_width_p`.
- `bp_be_defines.svh:68-73`: dispatch packets carry physical `thread_id` and logical CTXT target as `context_id_width_p`.
- `bp_be_defines.svh:90-92`: reservation packets carry physical `thread_id` and logical CTXT target as `context_id_width_p`.
- `bp_be_defines.svh:267-274`: packet width macros account for both physical `thread_id_width_p` and logical `context_id_width_p`.
- `bp_common_core_if.svh:57-67`: FE context-switch command operand is explicitly a target hardware thread ID.
- `bp_fe_controller.sv:157-164`: FE redirects to `ctxtsw_thread_id_i` and writes that physical ID into branch metadata.
- `bp_fe_pc_gen.sv:86-91`: FE PC/predictor selection register is physical `thread_id_r`.
- `bp_fe_pc_gen.sv:180-206` and `240-269`: BTB/BHT arrays are selected by physical `thread_id_r`.
- `bp_be_csr.sv:251`: CTXT CSR writes are excluded from normal CSR writes through `~retire_ctxtsw_v_i`.
- `bp_be_csr.sv:326-334`: privilege and translation enable are sequential CSR state.
- `bp_be_csr.sv:467-490`: SATP and many privilege CSRs are normal CSR state.
- `bp_be_csr.sv:730-735`: memory translation info comes from CSR state, including SATP base PPN and ASID.
- `bp_be_csr.sv:756-771`: bootstrap CSRs `0x082` and `0x083` also encode target IDs with `thread_id_width_p`.
- `bp_be_csr_wrapper_mt.sv:108-119`: one CSR instance is generated per resident hardware thread.
- `bp_be_csr_wrapper_mt.sv:165-179`: CSR outputs and bootstrap side effects are selected from `current_thread_id_i`.
- `bp_be_calculator/bp_be_pipe_mem.sv:222-259`: normal D-cache packets are constructed from pipeline reservations inside the memory pipe.
- `bp_be_calculator/bp_be_pipe_mem.sv:134-185`: normal D-cache requests use DMMU lookup and `trans_info_cast_i.translation_en`.
- `bp_be_dcache.sv:837-838`: D-cache busy/ordered are internal state derived from cache pipeline/credits.
- `bp_be_dcache_decoder.sv`: `e_dcache_op_ld`/`e_dcache_op_sd` decode as doubleword load/store operations, so 64-bit context-image words match an existing D-cache operation size.
- `testing/mt_seed.h`: software seeding helpers derive `BP_TID_BITS` from `BP_NUM_THREADS`, so they also address physical slots today.

## Terminology

- `logical_context_id`: software-visible context ID written to CSR `0x081`.
- `resident_slot_id`: physical hardware slot used by the frontend PC/predictor state, backend regfile bank, scheduler hazards, and writeback routing.
- `resident hit`: target logical context is already mapped to a resident slot.
- `resident miss`: target logical context is not currently resident and must be restored from memory before it can run.

## Design

### Resident Map

Add a small mapping table near the context-switch ownership logic:

- `slot_valid[2]`
- `slot_logical_id[2]`
- `logical_resident_v[num_contexts_p]`
- `logical_resident_slot[num_contexts_p]`
- `current_logical_context_id_r`

Keep existing `current_thread_id_lo` as the resident physical slot ID. Add a separate `context_id_width_p = BSG_SAFE_CLOG2(num_contexts_p)` and keep CTXT CSR targets at that width until the resident map translates them.

This requires updating the CTXT-specific path before truncation:

- scheduler CTXT target decode in `bp_be_scheduler.sv`
- dispatch packet CTXT target field in `bp_be_defines.svh`
- reservation packet CTXT target field in `bp_be_defines.svh`
- width macros for dispatch/reservation packets in `bp_be_defines.svh`
- calculator fast CTXT handoff fields in `bp_be_calculator_top.sv`
- pending CTXT target registers in `bp_be_top.sv`

Normal FE/BE thread ownership remains based on `resident_slot_id`.

Do not widen FE physical thread IDs. FE command and predictor state remain resident-slot based. Translate logical IDs before FE redirect.

### Fast Path: Resident Hit

If the target logical context is already resident:

1. Translate logical target ID to `resident_slot_id`.
2. Use the existing ISD-forwarding path.
3. Do not enter the context-cache FSM.
4. Preserve current performance counters and waveform expectations for two-context tests.

Verify resident-hit behavior before implementing resident misses. This catches width/plumbing regressions early.

### Slow Path: Resident Miss

If the target logical context is not resident:

1. Suppress early FE sideband launch for that switch.
2. Stall issue/FE queue so no target-context instructions dispatch before restore.
3. Remember:
   - old logical context ID
   - target logical context ID
   - victim resident slot
   - target NPC / resume PC
4. Wait for `commit_pkt.ctxtsw` so the old context state is architecturally settled.
5. Wait until the victim resident slot is safe to save.
6. Save the victim slot state to reserved cacheable memory.
7. Restore target logical context state into the victim slot.
8. Update resident map.
9. Launch the normal FE redirect using the restored resident slot.

The slow path must not use the current early FE sideband until restore is complete. Launching FE before restore would make the target stream use a resident slot whose regfile/context metadata still belongs to the victim.

### Context-Cache FSM

Use a serialized first implementation:

1. `idle`
2. `wait_ctxtsw_commit`
3. `wait_drain`
4. `save_regs`
5. `save_npc`
6. `restore_regs`
7. `restore_npc`
8. `install_slot`
9. `launch_fe`
10. `done`

The FSM owns the regfile scan path and D-cache access path only while normal instruction issue is stalled.

The exact `wait_drain` condition is a required design item, not an implementation detail. At minimum it must prove:

- no new issue from the FE queue
- no late writeback can still target the victim resident slot
- memory pipe is not busy and is ordered
- PTW/replay/resume paths are not injecting work for the victim slot
- detector dependency pipeline no longer contains live victim-slot entries that can write back later

### Saved State V1

Save and restore:

- integer registers `x1-x31`
- NPC / resume PC
- privilege mode
- translation enable
- ASID
- metadata needed to validate the context image

Do not save/restore in V1A:

- `x0`
- floating-point registers
- per-logical predictor state
- full CSR file except any fields explicitly added below

Design decision to verify before implementation:

- If V1 must pass address-space/privilege tests, it needs SATP and selected CSR state, not just ASID. Current translation information is derived from CSR state in `bp_be_csr.sv`, and full CSR state lives in per-resident-slot CSR instances.
- If V1A is only a GPR/NPC scaling prototype, tests must explicitly avoid SATP, privilege changes, FP state, and full CSR isolation across nonresident eviction.

Tests for V1A must avoid relying on the omitted state across nonresident evictions.

Practical V1 recommendation:

- V1A: GPR + NPC + existing resume metadata only. This validates logical-to-resident mapping, resident miss detection, and save/restore sequencing. Synthesis scaling remains a separate measurement.
- V1B: add SATP and the minimum CSR state required for address-space/privilege tests.

Do not claim support for Banyan-style different address spaces until V1B works.

### Backing Store

Use a reserved cacheable memory range:

```text
context_base + logical_context_id * context_stride + field_offset
```

Suggested layout:

- `0x000`: magic
- `0x008`: version
- `0x010`: logical context ID
- `0x018`: valid word
- `0x020`: NPC
- `0x028`: privilege / translation / ASID metadata
- `0x030`: SATP or reserved CSR metadata
- `0x040`: `x0`
- `0x048`: `x1`
- ...
- end of integer register area, rounded to a 512-byte stride

`testing/mt_context_image.h` defines this concrete V1A image format, and `mt_ctxtsw_context_cache_cooperative_image` verifies the stride, field offsets, and independent logical image slots without requiring transparent hardware eviction. Start with 64-bit word accesses because the existing D-cache supports doubleword load/store operations. The exact hardware service path is still a design item: a request through `bp_be_calculator/bp_be_pipe_mem.sv` must deal with DMMU translation, while a lower path near `bp_be_dcache` must supply physical tag/metadata correctly. Line-wide transfers can be a later optimization.

### Regfile Access

Extend `bp_be_regfile_mt` with a debug/service scan port or tightly scoped context-service port:

- one read per cycle for save
- one write per cycle for restore
- selected by `{resident_slot_id, reg_index}`
- active only when the scheduler is stalled/drained

Current `bp_be_regfile_mt` uses synchronous memories and one write port. The least invasive candidate based on current ports is:

- reuse an existing read port for save only while ISD is blocked
- reuse the existing write mux shape for restore, similar to CSR `rpush`
- give context-restore writes priority only after the drain condition proves no normal writeback/rpush collision is possible

Adding a dedicated service port remains a later optimization candidate, but it increases area and is not part of the first version.

### D-Cache Access

Add a context-engine load/store request path inside or adjacent to `bp_be_calculator/bp_be_pipe_mem.sv`, where normal D-cache packets are already constructed.

Do not start with a top-level LCE-side mux. At `bp_be_top.sv`, the interface is already below the load/store abstraction, after tag/data/stat memory arbitration and cache request metadata are involved.

V1 constraints:

- one outstanding context-engine request at a time
- no overlap with normal load/store issue
- no attempt to optimize miss latency yet
- waveform-visible state for request, response, current reg index, and target address
- service path must respect D-cache busy/ordered/credit behavior

Alternative implementation to consider before RTL edits:

- use existing software-visible stores/loads to initialize/check context memory images for a first test
- optionally use cooperative self-save/self-restore test code
- then replace the software-only image handling with the hardware context FSM once the saved-image format and tests are proven

This is especially useful because current bootstrap CSRs `0x082` and `0x083` are physical-slot addressed. Nonresident logical contexts need either:

- a memory image initialized by software before first switch, or
- new logical-context bootstrap CSRs, or
- widened versions of the existing bootstrap CSRs.

The memory image is the least invasive starting point.

Limitation: software cannot non-cooperatively save an arbitrary resident slot's GPRs today. CSR `0x083` is remote write only; no remote-read/`rpull` equivalent was found. Hardware regfile scan is still required for transparent eviction.

## Concrete Implementation Surfaces

### Parameter And Type Plumbing

Likely files:

- `bp_common_aviary_cfg_pkgdef.svh`: add `num_contexts` to the processor configuration struct if we want it to be a first-class config parameter.
- `bp_common_aviary_defines.svh`: derive `num_contexts_p` and `context_id_width_p`.
- `bp_be_defines.svh`: add logical CTXT target fields to dispatch/reservation packets and update packet width macros.
- `bp_be_scheduler.sv`: decode CTXT target into `context_id_width_p` while preserving issue packet `thread_id` as physical.
- `bp_be_calculator_top.sv`: carry logical CTXT target through reservation/fast handoff until `bp_be_top.sv` can translate it.
- `bp_be_top.sv`: own resident map, pending logical target, physical resident target, and slow-path FSM.

### FE Boundary

Keep FE physical:

- `fe_ctxtsw_thread_id_o`
- `bp_fe_cmd_pc_redirect_operands_s.context_switch_thread_id`
- branch metadata `thread_id`
- PC-gen predictor array selection

Logical IDs must never enter FE in this design. FE only needs the resident slot selected by the map.

### CSR Boundary

CSR `0x081` is the software-visible logical context ID. The read path now carries `current_context_id_i` from `bp_be_top.sv` through `bp_be_calculator_top.sv`, `bp_be_pipe_sys.sv`, and `bp_be_csr_wrapper_mt.sv` into `bp_be_csr.sv`, where CSR reads return the logical ID rather than the physical resident slot. Existing resident-only tests cover this as a no-regression path; a logical-ID-not-equal-physical-slot runtime check still needs the nonresident restore path.

CSR `0x082` and `0x083` currently seed physical slots. Options:

- keep them physical-only and use memory images for nonresident context initialization
- add new logical-image init CSRs
- widen/redefine them to use `context_id_width_p`

Keeping these CSRs physical-only avoids RTL changes to the existing bootstrap CSRs for the first resident-cache experiment, but it requires new tests that initialize logical context memory images directly.

### Drain Detection

Signals that are already available near `bp_be_top.sv` and must be evaluated:

- `hazard_v`
- `ordered_v`
- `mem_busy_lo`
- `mem_ordered_lo`
- `late_wb_v_lo`
- `late_wb_yumi_li`
- `late_wb_pkt.thread_id`
- `cmd_full_n_lo`, `cmd_full_r_lo`, `cmd_empty_n_lo`, `cmd_empty_r_lo`
- scheduler `ptw_busy_lo` is local today, so exposing a PTW-busy/drained signal may be necessary.

Verify the drain condition with waveform before save begins.

### Regfile Service

The least invasive candidate is to add service controls to `bp_be_regfile_mt` and connect them through `bp_be_scheduler`:

- service read enable/address/thread
- service read data valid/data, accounting for synchronous memory latency
- service write enable/address/thread/data
- arbitration against normal writeback and `rpush`

Because `bp_be_regfile_mt` has one write port, restore must occur only when normal writeback/rpush are inactive by construction.

### D-Cache Service

Do not start by muxing at the top-level LCE interface. Add a context-service request source where `bp_be_calculator/bp_be_pipe_mem.sv` currently constructs `bp_be_dcache_pkt_s`, or add an adjacent service path next to `bp_be_dcache` that still respects:

- DTLB/physical addressing choice for the reserved backing region
- cache busy/ordered state
- cache request credits
- one outstanding request at a time for V1

Open design point: the context image would be simplest with physical/cacheable backing addresses, but the current `bp_be_calculator/bp_be_pipe_mem.sv` path normally uses the DMMU. Choose between:

- generating a request with translation disabled or with a known direct-map address
- adding a lower physical request path near `bp_be_dcache`
- intentionally using virtual addresses and requiring valid translation state for the context engine

The third option has a concrete ordering risk for V1 because context restore may need to work before the target context's SATP/translation state is restored.

## Verification Plan

### Cleanup Checkpoint

Before implementing:

- archive or revert any unverified diffs
- revert failed experiments
- remove generated waveform/debug clutter
- verify both repos are clean except this planning document

### Build Checks

- `git diff --check`
- `git -C import/black-parrot diff --check`
- `make -j24 prep_lite`

### Resident-Hit Regression

Use existing two-context tests. Passing resident-hit tests must not enter the context-cache FSM:

- `mt_ctxtsw_smoke_test`
- `mt_ctxtsw_microbench`
- controlled gap tests previously used for ISD forwarding
- register isolation/regfile tests

Run with:

```sh
make -C cosim/black-parrot-minimal-example/verilator clean run PROG=<test> TRACE=1
```

### New Resident-Miss Tests

Add focused tests:

- `mt_ctxtsw_context_cache_smoke`: three logical contexts with two resident slots.
- `mt_ctxtsw_context_cache_ring4`: four logical contexts round-robin, forcing repeated eviction and restore.
- `mt_ctxtsw_context_cache_dirty_regs`: each context writes distinct integer register values, gets evicted, then verifies restore.
- `mt_ctxtsw_context_cache_hit_miss_mix`: alternate resident hits and resident misses to verify fast path is preserved.
- `mt_ctxtsw_context_cache_metadata`: verify NPC, privilege/translation metadata, and ASID/SATP behavior according to the chosen V1 scope.
- `mt_ctxtsw_context_cache_cooperative_image`: software initializes/checks logical context images in memory without requiring transparent hardware eviction.

Before these, add a narrow plumbing test:

- `mt_ctxtsw_logical_id_decode`: build with two resident slots and at least four logical contexts; write CTXT target `2` or `3`; verify waveform shows the full logical ID before resident-miss handling, not a truncated physical slot.

### Waveform Acceptance

Resident hit:

- no context-cache FSM activity
- sideband/ISD forwarding behaves like current optimized path
- no extra stalls beyond known resident-hit behavior

Resident miss:

- early FE sideband is suppressed
- no target logical context dispatches before restore completes
- `commit_pkt.ctxtsw` is observed before victim save begins
- drain condition is satisfied before first victim regfile read
- victim registers are saved with the old resident slot ID
- target registers are restored into the selected resident slot
- restored NPC/priv/translation/ASID metadata is visible before FE redirect
- resident map updates before FE redirect
- normal instruction issue remains blocked while context-cache FSM owns regfile/D-cache service ports

## Performance Reporting

Report resident-hit and resident-miss performance separately:

- resident-hit context-switch overhead
- resident-miss hot-L1 save/restore cycles
- resident-miss cold-cache behavior
- cycles spent in each FSM state

V1 resident misses serialize 31 register saves and 31 register restores with word accesses, plus metadata and D-cache service latency. That makes resident misses structurally slower than the current resident-hit path, but the exact cost is unmeasured until the service path exists.

## Explicitly Unverified Or Out Of Scope

- Area/fmax benefit from reducing resident slots after adding the resident map and context-cache FSM.
- Exact drain predicate for a victim resident slot.
- Exact D-cache service insertion point and translation/bypass mechanism.
- Resident-miss cycle cost.
- Minimum CSR subset for address-space/privilege tests.
- Predictor isolation beyond the resident physical slots.
- RTL build/simulation for this document revision; this pass is code-analysis and planning only.

## Risks And Open Questions

- Whether the cleanest regfile service path is a new port or a mux around existing read/write ports.
- Whether D-cache arbitration is easiest in `bp_be_calculator/bp_be_pipe_mem.sv` or in a small side engine next to `bp_be_dcache`.
- Exact drain condition required before saving the victim slot.
- How to initialize backing memory for never-before-resident logical contexts.
- Which CSR/translation state V1 must preserve.
- Whether synthesis is improved enough by reducing resident slots to two after adding the context-cache FSM and maps.
- Whether a software image prototype should precede the hardware save/restore FSM to prove image format and tests.
- Whether the D-cache service should bypass DMMU or use a direct-map virtual address.

## Commit Strategy

Use small commits:

1. Done: add `num_contexts_p` / `context_id_width_p` and CTXT logical-target plumbing with no behavior change for `num_contexts_p == num_threads_p`.
2. Done: add resident map and logical-to-resident translation for resident hits; verify existing resident tests.
3. Done: add resident-miss detection that reports an explicit unsupported/halt condition; verify target IDs above resident count are no longer truncated.
4. Done: add context image format and tests that initialize/check images without hardware eviction.
5. Done: add passive context-cache FSM skeleton with counters/waveform signals but no active save/restore. Verified with `git -C import/black-parrot diff --check -- bp_be/src/v/bp_be_top.sv`, `make -j24 prep_lite`, clean traced `mt_ctxtsw_smoke_test`, and clean traced `mt_regfile_test`.
6. Done: add explicit scheduler/calculator drain-ready observation signals and gate the passive FSM's `wait_drain -> save_regs` transition on the combined drain-safe condition. Verified with `git -C import/black-parrot diff --check`, `make -j24 prep_lite`, clean traced `mt_ctxtsw_smoke_test`, and clean traced `mt_regfile_test`.
7. In progress: add regfile scan save/restore support without D-cache traffic. Current checkpoint adds integer-regfile scan read/write plumbing and local shadow storage, verified not to disturb resident-hit smoke/regfile flows; it is not yet end-to-end exercised because nonresident switches still stop at the intentional simulation fatal before scan states run.
8. Add D-cache save path.
9. Add D-cache restore path.
10. Add resident-miss end-to-end tests.
11. Clean debug instrumentation and document measured costs.
