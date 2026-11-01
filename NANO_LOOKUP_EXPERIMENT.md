This document defines and records the Nano-coroutine-style index-lookup experiment. It keeps the workload contract, matched controls, measurements, rejected evidence, and pull-request status together so benchmark changes cannot silently change the paper claim.

# Nano-style index lookup experiment

## Research question

Can hardware contexts hide the dependent cold-memory latency of independent binary index lookups, and how closely can they approach both a software state machine and compiler-generated C++20 coroutines that schedule the same requests?

This is the algorithmic workload from Gor Nishanov's CppCon 2018 “Nano-coroutines to the Rescue” benchmark: multiple independent binary searches over a sorted index. In the original [`2018_CppCon/src`](https://github.com/GorNishanov/await/tree/master/2018_CppCon/src), `naive.h` performs one binary search, `sm.h` keeps several search frames and rotates among them while prefetching the next midpoint, and `coro.h` expresses the same multi-lookup schedule as one coroutine per search. Our matched batches are corresponding explicit-state-machine controls, the worker mode tests the same idea with BlackParrot context handoffs, and modes 6/9/10 provide compiler-generated C++20 coroutine controls with checked, lean-queue, and direct-transfer scheduling. The benchmark remains a bare-metal RISC-V adaptation because the original source depends on C++ iterators, `std::vector`, x86 `_mm_prefetch`, and a hosted runtime; direct source reuse would not preserve the target's data, timing, or memory contract.

The BlackParrot adaptation intentionally changes the data and measurement shape: it provides ten deterministic absent-key searches and selects two through ten at runtime, with separate linked 64-byte nodes per shard, aligned 64-bit key/link words that fit the 16-byte hint, explicit cold-data/warm-instruction preparation, and trace-visible BEGIN/END markers. It therefore preserves the lookup/interleaving algorithm, not Gor's exact container layout, compiler output, or reported numbers. It is not a full database engine. A database integration is justified only if this controlled index workload establishes a useful mechanism and identifies which overhead remains.

## Workload

- Two through ten absent-key lower-bound queries fan out across the corresponding number of independent sorted index shards. Ten remains the full-capacity case; eight is the default selected by the fair-software simulator sweep below. This preserves Nishanov's multi-lookup decision algorithm while modeling a database/search tier querying independent partitions rather than manufacturing concurrency from one shared root line.
- Each logical shard has 2,047 entries and an immutable eleven-node search path. Every 64-byte node places the 64-bit midpoint key in one hinted 8-byte word and both 32-bit branch-selected next-node links, packed into one aligned 64-bit load, in the other. This yields eleven dependent cold lines per query, or 22 through 110 useful key loads per data mode. The D-cache side buffer consumes each prefetched word once and does not shift subword hits; the benchmark unpacks the selected link in registers.
- Even stored keys and odd query keys prevent early equality termination while retaining real data-dependent branch direction.
- Separate 31-entry shards warm every mode in one fixed order before measurement without consuming measured data; a final switch-only warmup establishes identical cache, predictor, and frontend history.
- The generated image contains only the 110 measured nodes and 50 warm nodes, rather than a sparse 1.25-MiB array. This avoids simulator-only initialization and cache-scrub work while retaining real data-dependent branch and address selection.
- The generated data and queries are deterministic; `testing/generate_nano_lookup_data.py` owns `testing/nano_lookup_data.h`.

The one-node-per-line layout preserves binary-search decisions while representing the index as linked cache-line nodes, closer to a database tree than Nishanov's packed x86 integer array. This deliberate difference makes BlackParrot's cache-line overlap observable with a simulator-sized image and must accompany every cross-platform discussion.

## Runtime-selected modes

One ELF/NBF contains every mode. The host patches only `benchmark_mode` before releasing the processor.

| Mode | Schedule | Purpose |
| ---: | --- | --- |
| 0 | Serial demand | Ordinary binary-search baseline with no explicit handoff or prefetch. |
| 1 | Demand ring | Selected workers calculate a midpoint, switch, then perform the cold load. |
| 2 | Worker prefetch | Each worker prefetches its midpoint, switches, then consumes it when resumed. |
| 3 | Matched batch | One explicit state machine issues one midpoint prefetch per selected query, then consumes the same values. |
| 4 | Switch-only | The same selected-worker ring and eleven rounds without index accesses. |
| 5 | Serial prefetch | One context hints and immediately consumes every node, isolating the detached hint path from scheduling overlap. |
| 6 | C++20 coroutines | One compiler-generated coroutine frame per query; each hints its next node, suspends, and resumes through a round-robin symmetric-transfer scheduler. |
| 7 | Fixed unrolled SoA batch | Compile-time worker count and unrolled issue/consume phases remove runtime-count and much explicit loop bookkeeping. |
| 8 | Fixed recompute batch | Unrolled batch recomputes each issued line address instead of retaining a line-pointer array. |
| 9 | Lean-queue C++20 coroutines | Compiler-generated frames scheduled by a sixteen-entry power-of-two head/tail queue. |
| 10 | Direct C++20 coroutines | Compiler-generated frames transfer directly to the statically known next search. |

`NANO_WORKERS=2..10` selects the query/shard count without rebuilding the executable; eight is the fair-software speedup point selected below. The primary quantities for the extension are `best coroutine cycles / worker-prefetch cycles`, `serial-prefetch cycles / worker-prefetch cycles`, and `best software batch cycles / worker-prefetch cycles`. Switch-only is reported as a decomposition control and is not subtracted from another mode.

## Matched-state and timing contract

Every mode seeds the same selected inactive contexts, clears the same result records, drains architectural traffic, warms all eleven bodies in a fixed order, and then runs switch-only. This leaves identical cache, predictor, and frontend history for every runtime selection. Mode and worker-count dispatch occur before BEGIN; each measured body enters through one identical indirect call. Warmup uses physically separate nodes, so the immutable measured paths remain untouched and cold until the explicit BEGIN marker and physical-cycle `0xCC0` timestamp. END and the second timestamp immediately follow the operation; result verification and printing are outside the timed interval. Trace windows use the committed cycle-counter instruction PCs, because the simulator's MMIO marker printout trails that architectural boundary.

Coroutine frames are allocated from a fixed ten-frame pool during `prepare`, before BEGIN, and destroyed after END. The measured coroutine interval therefore includes compiler-generated suspend/resume and scheduling work but excludes frame construction/destruction. It uses the same aligned loads, prefetch primitive, result records, queries, and correctness oracle as the hardware and explicit-state-machine modes; no hosted allocator or exception runtime is linked.

Every data mode publishes and checks each query's lower bound, path checksum, step count, and completion flag. Switch-only publishes through the same result storage with zero data results. A transcript is accepted only when its runtime mode, selected query count, eleven-level count, program-specific PASS marker, `CORE PASS`, and host `BSG PASS` agree.

Trace analysis must report first/last accepted hint, first/last UCE issue/response, and first/last consuming load where exact generated load PCs are available. It should report matched-region AXI request/response boundaries when correlation is qualified; otherwise it must state the missing evidence and make no AXI or backing-bank claim. It must also report time-weighted whole-window and active-interval occupancy, state whether requests overlap prior responses, and compare worker versus batch issue spans under the same capacity and arbitration.

## Commands

Compile or run one mode from the repository root:

```sh
make -C testing "$(pwd)/riscv/bp-tests/mt_nano_lookup_benchmark.riscv" \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10

make -C testing run-mt_nano_lookup_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 NANO_MODE=2 NANO_WORKERS=5 TRACE=1 \
  SIM_DEFINES='BP_AXI_MEM_PIPELINED BP_AXI_MEM_READ_LATENCY=200 BP_AXI_MEM_READ_QUEUE_DEPTH=10'

codex-skills/bp-memory-interleaving-app/scripts/launch_nano_lookup_matrix.sh \
  logs/nano-lookup-$(date -u +%Y%m%dT%H%M%SZ)
```

Run modes serially because they share simulator program and log artifacts. Waveforms are written directly into each artifact directory and hashed before starting the next mode. The launcher returns immediately, refuses a dirty worktree, holds a simulator lock, and performs the seven runs plus trace analysis in the background. `NANO_ANALYZE=0` archives all rows first when faster simulator turnaround matters; trace analysis can then operate on the closed waveforms.

## Results and status

The corrected C++20 extension sweep uses one combined executable and the same synthetic 200-cycle AXI configuration across every supported active-query count. Every row passes result, checksum, guest, core, and host checks. These are transcript-qualified simulator results, not physical-memory or full waveform-qualified claims:

| Queries | Worker prefetch | C++20 coroutine | Coroutine / worker | Worker cycles / useful load |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 2,621 | 2,916 | 1.113x | 119.136 |
| 3 | 2,645 | 3,231 | 1.222x | 80.152 |
| 4 | 2,679 | 4,336 | 1.619x | 60.886 |
| 5 | 2,694 | 5,393 | 2.002x | 48.982 |
| 6 | 2,734 | 6,470 | 2.366x | 41.424 |
| 7 | 2,769 | 7,523 | 2.717x | 35.961 |
| 8 | 2,800 | 8,596 | 3.070x | 31.818 |
| **9** | **3,060** | **9,645** | **3.152x** | **30.909** |
| 10 | 3,414 | 10,734 | 3.144x | 31.036 |

Two answers to “optimal” are now explicit. N=2 minimizes one batch's absolute latency. N=9 maximizes both hardware-versus-coroutine speedup and useful-node throughput in this sweep; N=10 is slightly worse on both because the ten-slot system is at saturation. The worker time is nearly flat through N=8 while coroutine time grows approximately linearly. Nine is therefore the maintained comparison point when the objective is the most advantageous speedup, while ten remains the full-capacity stress case.

The following original rows are retained as rejected diagnostics so the corrected claim is auditable:

| Queries | Worker prefetch | C++20 coroutine | Coroutine / worker | Worker cycles / useful load |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 2,624 | 2,929 | 1.116x | 119.3 |
| 3 | 2,644 | 3,247 | 1.228x | 80.1 |
| 4 | 5,904 | 4,307 | 0.729x | 134.2 |
| **5** | **2,710** | **5,372** | **1.982x** | **49.3** |
| 6 | 5,962 | 6,429 | 1.078x | 90.3 |
| 7 | 6,014 | 7,486 | 1.245x | 78.1 |
| 8 | 6,050 | 8,579 | 1.418x | 68.8 |
| 9 | 6,274 | 9,644 | 1.537x | 63.4 |
| 10 | 6,624 | 10,717 | 1.618x | 60.2 |

The original sweep is retained below as rejected tuning evidence because its N=4 and N=6 worker rows contain an artificial terminal-path stall. A focused trace and exact-model A/B identify and remove that artifact: N=4 changes from 5,904 to 2,679 cycles, N=5 from 2,710 to 2,694, and N=6 from 5,962 to 2,734. The corrected complete sweep below supersedes the claim that five shards is optimal.

The corrected N=5 controls are serial demand 181,546 cycles, demand ring 181,671, serial prefetch 12,725, C++20 coroutine 5,393, explicit software batch 4,454, hardware worker 2,694, and switch-only 766. Across 55 useful visits, demand/serial-prefetch/coroutine/batch/worker cost 3,300.836/231.364/98.055/80.982/48.982 cycles per node. Hardware is 67.389x/4.723x/2.002x/1.653x faster respectively. The demand comparison mixes narrow detached-hint transport with overlap; serial prefetch is the cleaner overlap control. Switch-only is a decomposition control and is not mechanically subtracted.

A scheduler diagnostic explains why this coroutine control is slower than Nishanov's hand-written state machine comparison. His source uses a 256-entry power-of-two queue with only head/tail state; this benchmark initially used a checked ten-entry queue, making each suspension pay two multiply/shift implementations of `% 10` plus count and safety bookkeeping. At N=9, checked-10/checked-16/Nishanov-style/direct-ring variants cost 100.061/85.253/76.475/63.798 cycles per useful node; exact-binary batch costs 59.758. At N=5, Nishanov-style and direct scheduling beat exact-binary batch by 5.3% and 20.2%, restoring the original qualitative ordering. These are diagnostic-branch results under the same simulator model, not yet replacements for the complete accepted matrix; evidence is under `logs/nano-cpp-coroutines-20261031/coroutine-scheduler-diagnostic/`.

The peer-review follow-up supersedes the preliminary fair-software numbers with one clean exact-image O3 matrix. At selected-and-disclosed N=8, hardware/fixed-unrolled-batch/direct-coroutine cost 2,810/3,817/5,567 cycles, or 31.932/43.375/63.261 cycles per useful node. Hardware is therefore 1.358x faster than the best tested explicit batch and 1.981x faster than the best tested coroutine. The complete hardware/batch N=2..10 ratios are 1.044x/1.075x/1.106x/1.152x/1.246x/1.279x/1.358x/1.319x/1.254x, making the favorable N=8 selection transparent. The O2 N=8 control is 2,795/3,813/5,640 cycles and moves the batch ratio only to 1.364x; three O3 repetitions each reproduce 2,810/3,817 exactly. Serial demand and demand-ring retain ordinary full-line transport and are not headline comparisons, serial prefetch is a same-hint overlap control, and switch-only is not subtracted. All 34 transcripts pass exact mode/N, result, checksum, guest, core, and host checks. No FPGA was used; exact evidence is under `logs/nano-peer-review-20261101/`.

Clean N=8 traces reverse the old runtime-batch attribution for the optimized batch. Hardware is 2,810 cycles/1,647 retired/1,163 no-retirement, while fixed batch is 3,817/1,584/2,233, so the full 1,007-cycle gap closes as 63 fewer batch instructions plus 1,070 additional no-retirement cycles. Both modes issue 88 complete hints, make zero ordinary measured-region UCE reads, begin with zero outstanding work, and peak at eight. Hardware nevertheless averages 6.483 outstanding hints over its whole window (6.658 while active) versus batch's 4.772 (5.108), and spans 2,529 versus 3,359 core cycles from first to last issue. The optimized hardware advantage therefore comes from more sustained overlap rather than fewer executed instructions or a higher request peak. No-retirement time still combines memory waiting, redirect, and pipeline effects; matched-region AXI correlation was unavailable, so no AXI occupancy or backing-bank parallelism is claimed. The older N=9 runtime-batch trace remains valid for that weaker implementation but no longer explains the headline gap.

The trace analyzer reports transaction-lifetime-weighted average occupancy. Historical accepted N=10 evidence gives 3.445 UCE hints outstanding over the whole 6,609-cycle window, 7.063 over its active request interval, and a peak of nine. Baseline N=4/N=6 traces accept and consume every expected hint with zero ordinary D-cache reads, which rejects the proposed dropped-hint/data-fallback explanation. The N=5 waveform is invalid for transaction accounting: its converted stream later jumps backward from timestamp 101,548,007,175 to 91,519,525,000, and an earlier block of glitch clock events produces the apparent response-boundary error. No ninth RTL response beat or N=5 occupancy is claimed from it.

The adjacent-count trace localizes the unexplained cycles. In both slow rows, a parked terminal worker speculates through its conditional park and following `ret`, reaching byte address `0x800003c0` in `main`'s post-measurement checksum loop. The address is already byte-addressed; the earlier mapping to `0x80000f00` and coroutine-scheduler attribution were wrong. One 64-byte I-cache refill begins eight cycles before context-cache target launch, returns its final one of 16 32-bit memory beats 3,239 cycles later, and target retirement follows seven or eight cycles after that. RTL inspection confirms that this historical frontend has no safe refill-cancellation handshake, so the context redirect waits; context-cache launch itself takes only three cycles. A first event extractor also counted both ends of one asserted ready/valid interval as two requests; clock-edge sampling establishes one. Making the never-resumed parked path an unconditional CSR-plus-loop removes the entire discontinuity while preserving the hot worker and consuming-load PCs. Compact evidence is under `logs/nano-cpp-coroutines-20261031/trace-n456-diagnostics/`.

A committed N=10 trace-enabled diagnostic independently passed result, checksum, guest, core, and host checks at 6,624 worker cycles and 10,717 coroutine cycles (1.618x). Its FST is deliberately rejected as trace-qualified evidence: the known post-PASS GPIO shutdown assertion left the converted waveform with a nonmonotonic timestamp before backend commit signals were emitted, so the analyzer could not prove all eight committed windows or the 110 consuming loads. A separate earlier coroutine diagnostic did observe 110 accepted hints and 110 consuming loads, but used a superseded executable and is not substituted for the rejected final trace. The performance sweep therefore remains transcript-qualified simulation evidence, not a new accepted waveform claim.

Separate address spaces are not expected to make this kernel faster by themselves. They add `satp`/ASID state, TLB pressure, and possible page walks; their value is isolation and demonstrating that hardware contexts preserve overlap across independent translations. A matched extension should compare one address space against per-worker Sv39 page tables in two forms: shared physical index pages to isolate translation cost, and private physical copies to include cache effects. Each needs warm-DTLB and cold-DTLB variants. Running ordinary OS processes would additionally measure kernel scheduling and IPC and is therefore a different benchmark from the current bare-metal coroutine comparison.

The first sharded five-mode pilot used a 64-bit key and two 64-bit links. Its detached hint fetched only 16 bytes, leaving the `next_if_value_ge` link outside the hinted region. The worker consequently made 110 hint requests plus 1,040 ordinary AXI reads, while the batch made 110 hints plus 902 ordinary reads. A first compact-node smoke then used a 32-bit key followed by two 32-bit links; it passed correctness in 198,996 cycles but still made 60 ordinary UCE fills (960 AXI reads). The key and `next_if_value_less` shared one 8-byte side-buffer word, which is consumed by the first key load. A second layout packed the links as two 32-bit fields in the second word and finished the measured interval in about 3,800 cycles, but failed the result oracle: the side-buffer hit path does not shift the second half of a subword load. None of these is an accepted latency-overlap result.

The corrected six-mode revision loads each hinted word once with an aligned 64-bit access and selects the link in registers. The completed matrix under a synthetic 200-cycle AXI read latency passes guest, core, host, and result checks in all six modes. Each run used the same ELF SHA-256 `2ca7c71d66270142025acd1877faac3478c51ce3f1adbf7fbd64c89350e4db22`, seven instruction-boundary windows (six dummy modes plus measured), and zero UCE/AXI traffic outstanding at BEGIN. All five data modes consume 110 keys and return the same checksum. The worker and batch each issue 110 hints with zero ordinary UCE/AXI data reads; the demand modes each make 110 ordinary UCE transactions, corresponding to 1,760 AXI beats. Trace summaries and per-mode hashes are under `logs/nano-lookup-interleaving-20261019/aligned-six-mode-531f6efa/`.

| Mode | Total cycles | Request issue span | Last response | Checks |
| --- | ---: | ---: | ---: | --- |
| Serial demand | 361,976 | n/a | +361,932 cycles | pass |
| Demand ring | 365,751 | n/a | +365,707 cycles | pass |
| Worker prefetch | 6,609 | 3,017 cycles | +3,265 cycles from BEGIN | pass |
| Matched batch | 5,924 | 5,234 cycles | +5,550 cycles | pass |
| Switch-only | 1,518 | n/a | n/a | pass |
| Serial prefetch | 25,371 | 25,088 cycles | +25,334 cycles | pass |

The worker schedule is 55.34x faster than demand ring but 11.56% slower than matched batch. The 55.34x ratio combines overlap with the detached 16-byte hint path versus full-line ordinary demand, so it is not a context-switch-only gain. Against serial prefetch, which uses the same hint transport without interleaving, the worker is 3.84x faster. The worker accepts only nine of its first ten hints before the first response and peaks at nine outstanding; batch accepts all ten and peaks at ten. This is a real request-issue capacity gap even though the worker's issue span is shorter over the complete eleven-level traversal.

The 55.34x ratio divides the complete demand-ring schedule (365,751 cycles) by the complete worker-prefetch schedule (6,609 cycles). The demand path makes 110 serialized full-line fills, represented by 1,760 AXI beats, while the worker makes 110 narrow detached-hint reads and overlaps up to nine; both transport and overlap change. The 25,371-cycle serial-prefetch control shows that the narrow hint path alone is already much faster than demand, but it does not supply a clean numerical subtraction of transport cost because scheduling and code paths also differ. The 5,924-cycle hand-written software batch is an optimized ceiling for the same hint path, not a requirement that nonzero-cost hardware switching beat it. The intended application value is to approach that ceiling while allowing each dependent search to remain a straightforward worker rather than an explicit ten-query state machine. Current benchmark setup still manually seeds nine contexts and stacks, so ease of use is a proposed interface benefit, not yet measured or delivered by this test.

For the superseded five-mode pilot, serial demand was 358,994 cycles, demand ring 361,980, worker prefetch 217,970, matched batch 187,721, and switch-only 4,746; all five checked results passed. The nominal worker/demand ratio was 1.66× and worker/batch gap 16.1%, but neither is accepted as the corrected workload's performance result. Instruction-boundary trace analysis found zero UCE/AXI requests outstanding at BEGIN for the four data modes. The worker reserved at most eight hints and issued only eight of the first ten before the first response, whereas the batch reached ten; that request-capacity difference is real. The pilot traces and exact ELF/NBF hashes are retained under `logs/nano-lookup-interleaving-20261019/`.

The exact consuming-load labels have been confirmed by disassembly, the generated header is deterministic, and all 17 checker/harness tests pass. A shared-index precursor passed worker mode at 3,601 cycles under the default short-latency model. Its marker-scoped trace had zero UCE/AXI transactions at BEGIN, 110 consuming loads, but only 94 UCE prefetch transactions and a maximum of one reserved slot; common upper-tree lines and six-cycle responses made it unsuitable for the intended ten-request capacity comparison. That result is retained only as a superseded diagnostic in `logs/nano-lookup-interleaving-20261019/sim-default-mode2/`.

The corrected sharded benchmark still requires a regression run of `mt_dependent_stream_benchmark` before review readiness. After that gate, prioritize a separate, narrow SQLite indexed-lookup feasibility experiment over further tuning this synthetic ratio: retain serial, software-batch, and hardware-context controls, and first verify that an actual SQLite page or index miss exposes an address early enough for the existing 16-byte hint. The older SQLite progress-callback screen demonstrated safe yielding but only 0.19–0.41% total-time advantage over software fibers and no compelling advantage over a direct callback; repeating that seam is not the next application test. Any database or physical-DDR speedup remains unmeasured.

FPGA implementation is intentionally deferred. If simulation supports the workload claim, run one final routed/physical acceptance after the branch is stable and record exact top/RTL commits, configuration, Vivado version, utilization, timing, NBF/bitstream hashes, and processor-reset sample procedure here and in the PR body.

## Pull request

Draft [PR #6](https://github.com/connoryang1/zynq-parrot/pull/6) is independent of protected RPC. Its exact base is `review/protected-rpc-base` at `1f86c605e8c415ad69f284ebaf577977a2803598`; its head is `bench/nano-lookup-interleaving`, initially opened at `ffdd6ba96ed71fc9cebd0ab92dcfe25727069352`. Keep the benchmark table, accepted commands, trace results, and unresolved gates synchronized between this document and the PR body.
