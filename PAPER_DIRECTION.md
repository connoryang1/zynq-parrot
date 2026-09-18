This file records the research objective and the acceptance criteria for the next experiment. It separates the context-switch mechanism already demonstrated on BlackParrot from the cache-overlap and application-speedup claims still to be tested.

# Research direction

The objective is to make cooperative context switches cheap enough that one
worker can request data, yield while it arrives, and resume with less exposed
memory latency. The next worker issues its own independent memory request:
the target is overlap between requests, not arithmetic inserted to cover a fill.
Cold-cache cost is a hypothesis to measure for the selected
workload; the existing switch-spacing numbers do not establish that it dominates
or that prefetching will produce a speedup.

The original architectural motivation is Humphries et al., “A Case Against
(Most) Context Switches,” HotOS 2021,
DOI [10.1145/3458336.3465274](https://doi.org/10.1145/3458336.3465274).
The current project implements a subset: cooperative contexts sharing one
pipeline, with inactive integer state in private SRAM. The paper's broader
permission, lifecycle, and notification interface remains separate work.

## Reference benchmark review

[context-switches](https://github.com/connoryang1/context-switches) has a proposal
on `main` (`4235881377f8d4a8f5154abbcacc9b0844375ec5`). The implementation is on
[`initial-benchmarking`](https://github.com/connoryang1/context-switches/tree/63e20a461a5d6bd3e689d0db78bebc6a1ff4a9cf/benchmarking)
(`63e20a461a5d6bd3e689d0db78bebc6a1ff4a9cf`):

| Mode | Implemented work | What to carry forward |
| --- | --- | --- |
| `baseline.cpp` | OS threads perform strided subsets of random loads with a dependency chain | Same deterministic access stream and checksum |
| `ideal.cpp` | One thread batches prefetches followed by loads | A batching comparison to show available memory overlap |
| `coroutines.cpp` | Workers prefetch, suspend, and resume through a software queue | A matched software handoff baseline |

The structure is useful, but its example speedups are not BlackParrot results.
The baseline pins workers to CPU 1 and times thread creation/join; the other
modes have different setup/timing boundaries and do not use that pinning helper.
There is no forced scheduler handoff per load. Therefore the difference does not
isolate context-switch cost. The x86 `_mm_prefetch` instructions also cannot be
ported directly to the current RISC-V implementation.

Use bounded worker counts: the reference coroutine queue has 256 entries, while
its Makefile sweeps up to 4096 workers. The throttler resumes only one suspended
worker before admitting another, which need not free a slot; that sweep is not
a reliable capacity model. The ideal loop also needs explicit batch/tail bounds
when the number of lookups is smaller than the batch. These are review findings,
not changes to the reference repository.

## First gate: finish context-switch qualification

Context switching is already integrated into BlackParrot. Before adding an
application benchmark, qualify resident CSR initialization and fetch/replay
ownership while preserving nonresident translated handoff and register-target
regressions. This gate passed local regressions and September 8 FPGA/Linux
shell acceptance on RTL `aad56bd92`, including resident/nonresident rings,
target syscalls, private registers, usable shell return, and clean poweroff. The
[checkout guide](CURRENT_CHECKOUT.md) records current revisions and the remaining
production-readiness gaps, including lifecycle, FP state, and isolation.

## Second gate: demonstrate actual memory overlap

The earlier arithmetic tests qualify a mechanism only. Their peer performs arithmetic,
not another random load, so they do not implement the reference workload or
establish a speedup for independent requests. The independent-request experiment
and its separate acceptance evidence are described below.

The September 8 load-ahead experiment establishes overlap with a pending full-line
refill. `bp_load_ahead()` in `software/include/bp_load_ahead.h` emits an ordinary
faulting `lbu x0` to valid cacheable data; it is not a nonfaulting prefetch hint.
The deployed baseline unicore Dcache enables hit-under-miss (`features_p=0x1f5`), retains one
outstanding blocking miss, and can continue integer work and resident switching.
Nonresident handoffs still drain outstanding memory activity.

In the controlled simulator test, each of eight cold lines per mode returns its
critical data beat 11 BE cycles after request acceptance and completes the full
refill at +53. Useful peer arithmetic retires at +17 for delayed `ld a5`, or +16
for `lbu x0` followed by a resident switch. Both overlap outstanding full-line
fills, but neither hides critical-word latency in this simulator configuration.
The streaming analyzer distinguishes these boundaries; correctness PASS alone
does not establish either timing claim.

The matched 16-line benchmark gives the following raw totals, including loop and
switch overhead. Each mode consumes identical values and performs 64 additions
per line; ahead modes additionally execute the discarded load. Separate arrays
provide cold first-touch data, and setup/checks/output are untimed.

| Schedule | Simulator cycles | FPGA cycles |
| --- | ---: | ---: |
| Serial demand load then computation | 1,357 | 1,675 |
| Same-context load-ahead then computation | 1,173 | 1,173 |
| Resident computation then demand load | 1,561 | 1,882 |
| Load-ahead, resident computation, demand load | 1,465 | 1,465 |

On FPGA, resident load-ahead reduces cycles by 12.5% versus serial and 22.2%
versus the resident control in this run. Same-context load-ahead is faster still.
The simulator resident load-ahead case remains slower than serial. These are
one small fixed-order first-touch series per platform, not statistical estimates
or a hardware-context advantage over an optimized single-context schedule.
The board and simulator use different startup ELFs, so cross-platform totals
are not identical-binary regression comparisons. The accepted RTL is unchanged.
Full-trace checks find exactly one cold miss for each of all 16 measured lines
in every simulator mode. Same-context load-ahead retires useful arithmetic at
+5 cycles, before the critical beat, for all 16 requests; resident load-ahead
does so at +17 (15 requests) or +21 (the first), after critical but before full
completion. In the resident control, peer work during a pending fill belongs to
the next loop iteration, not to a prefetch of its upcoming demand.
Both new programs pass simulator and FPGA checks; exact sources, hashes, closed
traces/transcripts, and timing analysis are retained in
`logs/resident-cache-overlap-20260908/`.

That baseline does not support multiple simultaneous cold misses. The new
nonfaulting hint path adds separate request slots; ownership, backpressure,
translation/fault handling, and refill completion are acceptance gates. The
original `bp_load_ahead` helper remains unsafe for arbitrary addresses.

## Matched application experiment

The workload models independent requests assigned to a thread pool on one
logical CPU. Each request consumes one random memory load; repeat requests to
obtain stable timing. Each worker owns its request address and result. Do not
pad the request with arithmetic or let one worker prefetch another's addresses
in the threaded cases. The batched case deliberately relaxes that constraint
to represent the ideal scheduling opportunity described in the proposal.

| Case | Required schedule | Purpose |
| --- | --- | --- |
| OS-thread baseline | `n` Linux threads pinned to one CPU, each consuming its own random loads without prefetch or explicit per-request yield | Original independent-request baseline |
| Batched ideal | One thread issues 10 prefetches, then consumes those same 10 loads | Original batching reference, assuming all request addresses are available together |
| Cheap-context candidate | Each worker prefetches its own address, yields to the next worker, and consumes that load when resumed | Test whether cheap handoffs recover the batching benefit |

For the candidate, the initial round is `A: prefetch(A) -> yield`, then
`B: prefetch(B) -> yield`, continuing through the workers. On resumption each
worker consumes its pending load, obtains its next request, prefetches it, and
yields again. Prime and drain the ring explicitly; count only completed useful
loads in throughput. No worker issues multiple requests ahead to create hidden
batching within a thread.

A cache miss in the baseline stalls the running logical CPU; it does not itself
invoke the Linux scheduler. Do not add a forced handoff after every baseline
load. Add separate software cooperative prefetch/yield/load and matched
no-prefetch handoff controls to distinguish scheduler cost from memory benefit;
neither replaces the original OS-thread baseline. A claimed round-robin control
must enforce and verify that order rather than assume `sched_yield()` provides it.

The accepted FPGA has two resident banks and four logical contexts. Start the
hardware candidate with two resident workers and compare it with two OS threads
and batch size two. Retain the original 10-thread/batch-10 reference separately;
do not compare different worker counts as a matched hardware speedup or label
ten software workers as ten resident hardware contexts. Four logical workers
exercise nonresident switches, which currently drain memory activity, and must
be reported separately.

On the deployed baseline RTL, `lbu x0` uses the ordinary load path and the cache has only one
outstanding blocking miss. The batched instruction schedule is therefore a
comparison to measure, not evidence that ten cold fetches run concurrently.
Trace whether B's request is accepted before A's critical data and full refill
complete, and whether a second miss serializes progress. `mt_request_interleave_benchmark` measures this baseline boundary; the
arithmetic-overlap result does not answer it. Its new
`mt_prefetch_interleave_benchmark` variant substitutes the dedicated hint while
retaining the same request streams and correctness checks.

Use the same data values, deterministic per-worker random request streams,
total request counts, and expected checksums across matched cases. Keep one
request outstanding per worker and preserve the per-worker consume-before-next
request dependency. Allocate, seed, create workers, and warm code outside
steady-state timing; use a common start/completion boundary, and account for
ring priming and draining consistently. Report setup and cold-start separately.
Sweep working sets across cache capacity, repeat independent datasets, and
rotate mode order. Random addresses alone do not prove cold misses: verify
cache behavior and document the cache-state preparation used for each sample.

Report raw core-wide `0xCC0` cycles, cycles/request, throughput, sample spread,
and checksum correctness. Pair these with waveform request/refill overlap,
architectural redirect-to-useful-work cycles, and instruction/data cache tails.
Keep FPGA area/timing cost and exact binary/RTL identities with the results.
A speedup must survive these matched controls; the existing 5.10/11.12 FPGA
cycles/switch are a mechanism measurement, not an application-speedup claim.

## Independent-request mechanism result

The September 8 two-resident test passes on the accepted FPGA RTL and a clean
traced simulator, with a known-good resident smoke also passing. Each mode
consumes the same 64 shuffled, first-touch lines without arithmetic padding.
Three disjoint data replicas rotate execution order; each worker's 32-load
count, checksum, and the final peer completion are checked. The OS-thread
comparison remains a separate Linux acceptance gate using matched runtime data.

| Schedule | Simulator cycles, three samples | FPGA cycles, three samples |
| --- | --- | --- |
| Resident no-prefetch handoff control | 3642, 4782, 3642 | 3163, 3563, 3163 |
| Single-context batch2 | 4037, 4037, 4145 | 3089, 3077, 3129 |
| Resident load-ahead/yield/load | 4145, 4309, 4145 | 3110, 3179, 3109 |

These are complete schedule costs, including 66 ring switches and final peer
publication in resident modes; batch2 publishes results after timing. The
three samples show cache-state sensitivity, and do not establish a broad
application speedup. Board and simulator startup ELFs differ.

The accepted trace checks all 768 cold misses across warmup and measured
pages, including each worker's exact request order and 64 distinct lines per
page. All 756 within-page pairs serialize: the next miss is admitted at least
four BE cycles after the previous full refill completes. Peer prefetch
instructions can dispatch during an outstanding fill, but independent cold
misses do not overlap. Dispatch order also differs from memory admission order;
this evidence alone does not establish a dropped-prefetch or replay root cause.

This identifies miss admission as a limit on the proposed overlap. A cheaper
prefetch instruction alone would not establish support for multiple outstanding
fetches. Any follow-up design must address request capacity and ownership as well
as issue overhead. Exact sources, binaries, closed traces, per-request analysis,
and board transcripts are in `logs/independent-requests-20260908/`.


## Nonfaulting prefetch implementation and first simulation result

The `feat/nonblocking-prefetch` implementation adds standard `prefetch.r` decode
and two outstanding physical hint slots in the UCE. Hints warm L2 through an
8-byte cached read; an L2 miss fetches the full 64-byte line. Their replies
never install L1 state or complete an architectural load. Unavailable or denied
translations and unavailable request capacity drop the hint. The ordinary L1
demand path remains blocking. The two-bank configuration preserves the 4 KiB
L2 capacity; same-bank misses still serialize.

The full-system simulator uses an optional four-entry AXI read queue with
40-cycle service latency from each accepted address and ordered responses.
This is controlled memory latency, not a model of physical DDR performance.
The instruction/data correctness, resident smoke, U-mode Sv39 hint permission,
and independent-request tests pass. Standalone UCE tests cover capacity,
backpressure, coalescing, response ownership, same-line demand waits, and credit
drain; malformed responses are rejected.

The same 64-load request schedule gives the following raw totals. The mode order
rotates across three disjoint measured datasets, after an untimed warmup.

| Schedule | Full-system cycles, three samples |
| --- | --- |
| Resident no-prefetch handoff control | 5079, 6022, 5079 |
| Single-context batch2 with `prefetch.r` | 4059, 4059, 4221 |
| Resident `prefetch.r` / yield / load | 4933, 5143, 4933 |

Waveform evidence qualifies each dataset separately. Each page has 64 ordinary
L1 reads with the expected unique lines and per-worker order. Batch2 issues
paired hints one cycle apart; its 18 opposite-bank pairs per dataset each admit
the second AXI read before the first read returns data. Maximum outstanding
data reads is two. This establishes concurrent requests through L2 and AXI.

The resident schedule has no overlapping data/data AXI reads in this run.
Its median successive hint issue gap is 76 cycles, versus a median 60-cycle
hint response lifetime. The first measured pair overlaps at the UCE but uses
the same bank (lines 23 and 25), so its backing reads serialize. This schedule
therefore does not yet demonstrate the intended sustained worker-to-worker
memory overlap. The cycle reduction against its handoff control alone does
not establish that mechanism. Best-effort hints also need not all be accepted:
one dataset allocates 61 of 64 hints, while all useful loads complete correctly.

Evidence is retained in `logs/nonblocking-prefetch-20260908/full-requests/`,
including exact ELF/NBF, closed FST, transaction-aware reports, page summaries,
and source hashes. Region and transaction-lifetime correlation exclude loader
and unrelated instruction reads; aggregate AXI overlap alone is insufficient.
At this initial checkpoint, the remaining work was to localize the resident
schedule's issue gap, then qualify the FPGA image and Linux OS-thread comparison. The prior
FPGA results above remain tied to their original deployed RTL.

### Removing the L2 response bottleneck

The first implementation's shared response metadata FIFO selected a pending
prefetch's bank even while the other bank had a ready demand. In the retained
window, the context switch reaches the peer's load in two BE cycles; the ready
demand then remains unacknowledged for 47 L2 edge opportunities. This is a
response-ordering delay, not the context switch's intrinsic cost.

RTL `070ae616a` keeps headers per bank, preserves global ordinary response order,
and lets ready responses pass pending hints. A selected packet remains locked
through its last accepted beat, including silent store acknowledgements and
backpressure. The isolated controller regression reproduces and rejects the old
behavior, and checks ordinary/same-bank ordering, eight-beat reads and writes,
store response collapse, AMO, capacity, initialization, and uncached draining.

The clean full-system run uses the named FPGA configuration with the same
parameters and the **identical ELF and NBF** as the first implementation.

| Schedule | Cycles, three measured samples |
| --- | --- |
| Resident no-prefetch handoff control | 5079, 6022, 5079 |
| Single-context batch2 with `prefetch.r` | 4059, 4059, 4221 |
| Resident `prefetch.r` / yield / load | 3867, 4100, 3867 |

Each measured resident page now has 12 cold-data prefetch pairs whose second
AXI address is accepted before the first read returns data; all use different
banks, and maximum outstanding data reads is two. Batch2 retains 18 pairs per
page, and the control remains serialized. All 64 useful loads per page retain
the expected unique lines and worker order. The previously blocked demand's
first-response latency falls from 55 to 8 UCE cycles; median successive hint
issue spacing falls from 76 to 55 cycles.

The median resident total is 23.9% below the matched handoff control and 21.6%
below the prior controller. These three controlled simulator samples establish
memory overlap in the proposed resident schedule; they do not establish a Linux
thread-pool or physical DDR speedup. Same-bank requests still serialize and
hints remain best effort. Exact identities, per-page transactions and comparison
reports are in `logs/nonblocking-prefetch-20260908/l2-unblocked/`.

The synthesis-corrected endpoint is RTL `f7eedd955`, pinned by top `fd5a7872`.
Vivado required moving the bank-select declaration before its generated uses;
the first route was canceled after implicit undriven nets were detected. An
isolated old/fixed synthesis comparison reproduces and eliminates those warnings,
and the corrected clean simulator benchmark and smoke retain identical totals.
This is a declaration-order correction, with no protocol logic change.


### Physical FPGA qualification

The exact `fd5a7872` / `f7eedd955` endpoint passes routed PYNQ-Z2 fit and six
bare-metal correctness gates. It uses 51,334 LUTs (96.49%) and 81 BRAM tiles,
with WNS +2.905 ns, TNS 0, WHS +0.020 ns, and THS 0. This leaves 1,866 LUTs
for expansion; the cache remains 4 KiB in total.

The matching board benchmark measures 64 useful loads per sample:

| Schedule | Cycles, three measured samples | Median |
| --- | --- | --- |
| Resident no-prefetch handoff control | 3164, 3541, 3161 | 3164 |
| Single-context batch2 with `prefetch.r` | 2688, 2688, 2757 | 2688 |
| Resident `prefetch.r` / yield / load | 2398, 2495, 2388 | 2398 |

Resident prefetch uses 24.2% fewer cycles than its matched control in this run.
Its median is also 10.8% below batch2 for this particular schedule and sample
size; that does not establish superiority over batching in general. The runner
replays its transcript, so the six displayed rows represent three samples,
not six. The board ELF uses FPGA startup code and differs from the simulator
ELF; comparisons above stay within each platform. Source, binary, and log
checks are in `logs/nonblocking-prefetch-20260908/board-prefetch/benchmark-summary.json`.

The physical board establishes correctness and cycle measurements. The final
simulator trace separately establishes overlapping cold-data transactions;
there is no physical AXI waveform capture in this result. The unchanged Linux
shell resident/nonresident benchmark also passes on the new image, with the
same 5.10546875 / 11.14453125 median cycles per switch and clean process exit,
usable shell, and poweroff. These checks do not qualify the Linux request-pool
benchmark: its second resident launch remains unresolved on the feature branch.
The next application gate is that lifecycle fix, followed by the pinned
OS-thread baseline, matched two-worker candidate, and batch-ten reference.

## Ten logical workers on two resident banks

The simulator now has a direct ten-worker experiment using `NUM_THREADS=2` and
`NUM_CONTEXTS=10`. Each logical worker owns one cold cache line. Demand mode
yields without a hint; candidate mode issues `prefetch.r`, yields, and consumes
the line after resumption. The batched mode issues ten prefetches and then ten
loads. Each schedule runs from a fresh boot because context state is not
reclaimed between independent launches.

The current high-latency control uses the full BlackParrot Zynq top and the
simulation-only pipelined AXI model with 200-cycle reads and ten queue entries.
A dedicated prefetch transport bypasses the blocking L2 DMA path and turns each
64-byte hint into one eight-beat, 64-bit AXI burst with a nonzero transaction
ID. Ordinary instruction, demand, context-state, and write traffic remains on
the existing path with AXI ID zero. The address arbiter locks its selected
source under backpressure, demand has priority between transfers, and the
prefetch bridge reassembles interleaved read beats independently for ten IDs.

The revision-matched fresh-boot results are:

| Schedule | Cycles |
| --- | ---: |
| Ten-worker demand | `0x0acb` (2,763) |
| Ten-worker prefetch/yield/load | `0x040e` (1,038) |
| Single-thread batched reference | `0x0406` (1,030) |
| Two-ring switch-only control | `0x01d8` (472) |

The cheap-context candidate saves 1,725 cycles, a 62.43% cycle reduction or
2.662x speedup over the matched demand schedule. It is eight cycles, or 0.777%,
slower than the ideal single-thread prefetch-then-load reference. After
subtracting the 472-cycle switch-only control, demand spends 2,291 cycles on
its data path while the candidate spends 566. This is the intended result: ten
independent workers recover essentially all of the batching benefit through
cheap handoffs without making their addresses available to one software thread.

Earlier million-cycle rows were invalid benchmark output. The inline-assembly
call did not declare the RISC-V call-clobbered registers, so the shared worker's
`li t1, 1` overwrote the start timestamp held in `t1`; the printed result was
effectively the absolute end cycle. The corrected source makes an ABI-visible
call and the disassembly keeps the timestamp in callee-saved `s2`.

The worker bodies are seeded with per-context data/result pointers, so the timed
body contains no address arithmetic. The UCE accepts hints while its demand FSM
waits, preserves detached credits across handoff, waits for the dcache's matching
replacement metadata before issue, and drops duplicate same-line hints. The
full-top bypass keeps these detached fills out of the L2 path that previously
serialized their external requests.

For attribution, `BENCH_MODE=3` runs the same two complete ten-context rings with
data operations removed. The high-latency control passes in 472 cycles.

The final closed trace passes the transaction gate with all ten hints complete.
It reaches ten simultaneously reserved UCE slots and ten outstanding AXI reads;
both interfaces accept later requests before earlier first responses, and AXI
IDs 1 through 10 all appear. Nine of ten later useful loads have no same-line
normal miss, while context zero joins its still-pending fill once.
AXI acceptance proves outstanding requests, not parallel DRAM-bank service.

All workers execute one shared 64-byte-aligned body, with private data/result
pointers and next-context IDs seeded in registers. This removes ten cold worker
instruction lines from the experiment while retaining ten independent logical
contexts, including eight nonresident contexts. Result bookkeeping is placed in
different L1 sets from the ten measured lines.

The UCE capacity is a configuration parameter rather than a hardcoded ten-entry
override. The ten-worker simulator explicitly requests ten entries and retains
the results above. The first PYNQ-Z2 endpoint used four entries: isolated
job `20260918T041813Z-e66721e2` routes at 51,791/53,200 LUTs (97.35%) with WNS
+2.178 ns, TNS 0, WHS +0.035 ns, and THS 0. Direct response-ID decoding removes
the ten-way response-address CAM while simulation assertions retain address and
live-slot checks. A default-flow ten-entry endpoint still failed placement at
54,081 LUTs and 11,535 required slices versus 11,333 available.

A named Vivado area flow resolves that capacity limit. Fit-only job
`20260918T055255Z-bcf24d47` routes ten entries with four logical contexts at
46,033 LUTs (86.53%). The exact experiment endpoint then expands the same static
configuration to two resident banks and ten logical contexts. Job
`20260918T064050Z-9e4b021d`, top `9e4b021d` and RTL `cc8297dec`, routes it at
48,645/53,200 LUTs (91.44%), 28,029 registers, 83.5 BRAM tiles, and 11 DSPs.
Final WNS/TNS are +0.251 ns/0 and WHS/THS are +0.023 ns/0. The verified package
SHA-256 is
`5b30e21e92d7693133c3e65e2e53721dc40dc1ea2d65faa7f94c1c07245f8b84`; its
bitstream SHA-256 is
`b7e05606979f79c0bf759c3a69fd10705d13ec026d85e2d2e621c643f0555a47`.
The exact benchmark NBF, SHA-256
`56878463ea4e8d3d217e5a26712b47add85d4ded9cdea9770231c86ef4adef28`, passes
the full-system simulator on that static configuration. The image has not been
board-qualified. It predates the current full-top ten-ID transport and is the
fit baseline for route job `20260918T081302Z-154554ae`. That candidate routes
at 49,197/53,200 LUTs (92.48%), 28,065 registers, 83.5 BRAM tiles, and 11 DSPs,
with final WNS/TNS +0.755 ns/0 and WHS/THS +0.037 ns/0. Bitstream DRC reports
zero errors. The verified package SHA-256 is
`65ce394e07a5d176ccc1c94bb767d396c265f8920fec45a66bbb377a2a1d0316` and the
bitstream SHA-256 is
`58d8dc8b945d6db67fc3eb666f3183a3b4670d007e94e1714204802416c46082`.
The current simulation trace establishes downstream concurrency in the real
full top, and the route establishes FPGA capacity and timing. Physical-board
qualification remains.

A prior minimal-top capacity experiment quantified the queue-depth compromise
on the same ten-worker, 200-cycle workload:

| Prefetch entries | Demand cycles | Prefetch/yield/load cycles | Speedup | Cycle reduction |
| ---: | ---: | ---: | ---: | ---: |
| 4 (first routed PYNQ-Z2 capacity) | 35,856 | 32,624 | 1.099x | 9.014% |
| 10 (original experiment) | 35,856 | 10,083 | 3.556x | 71.879% |

All ten workers issue once before any worker consumes. Because hints are
nonblocking, a full four-entry table drops the remaining six hints rather than
stalling the issuing contexts; their later demand loads therefore still miss.
The four-entry result demonstrates a measurable benefit, but it cannot reproduce
the batch-of-ten overlap without enough capacity for all ten outstanding lines.
The current ten-entry candidate removes both that queue limit and the serialized
full-top transport, and it passes routed fit and timing. The hash-identified
benchmark on the physical board is the remaining experiment gate.
