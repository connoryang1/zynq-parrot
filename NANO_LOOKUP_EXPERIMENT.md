This document defines and records the Nano-coroutine-style index-lookup experiment. It keeps the workload contract, matched controls, measurements, rejected evidence, and pull-request status together so benchmark changes cannot silently change the paper claim.

# Nano-style index lookup experiment

## Research question

Can hardware contexts hide the dependent cold-memory latency of independent binary index lookups, and how closely can they approach both a software state machine and compiler-generated C++20 coroutines that schedule the same requests?

This is the algorithmic workload from Gor Nishanov's CppCon 2018 “Nano-coroutines to the Rescue” benchmark: multiple independent binary searches over a sorted index. In the original [`2018_CppCon/src`](https://github.com/GorNishanov/await/tree/master/2018_CppCon/src), `naive.h` performs one binary search, `sm.h` keeps several search frames and rotates among them while prefetching the next midpoint, and `coro.h` expresses the same multi-lookup schedule as one coroutine per search. Our matched batch is the corresponding explicit-state-machine control, the worker mode tests the same idea with BlackParrot context handoffs, and mode 6 now provides a real compiler-generated C++20 coroutine control. The benchmark remains a bare-metal RISC-V adaptation because the original source depends on C++ iterators, `std::vector`, x86 `_mm_prefetch`, and a hosted runtime; direct source reuse would not preserve the target's data, timing, or memory contract.

The BlackParrot adaptation intentionally changes the data and measurement shape: it uses ten deterministic absent-key searches, separate linked 64-byte nodes per shard, aligned 64-bit key/link words that fit the 16-byte hint, explicit cold-data/warm-instruction preparation, and trace-visible BEGIN/END markers. It therefore preserves the lookup/interleaving algorithm, not Gor's exact container layout, compiler output, or reported numbers. It is not a full database engine. A database integration is justified only if this controlled index workload establishes a useful mechanism and identifies which overhead remains.

## Workload

- Two through ten absent-key lower-bound queries fan out across the corresponding number of independent sorted index shards. Ten remains the full-capacity case. This preserves Nishanov's multi-lookup decision algorithm while modeling a database/search tier querying independent partitions rather than manufacturing concurrency from one shared root line.
- Each logical shard has 2,047 entries and an immutable eleven-node search path. Every 64-byte node places the 64-bit midpoint key in one hinted 8-byte word and both 32-bit branch-selected next-node links, packed into one aligned 64-bit load, in the other. This yields eleven dependent cold lines per query and 110 useful key loads in every data mode. The D-cache side buffer consumes each prefetched word once and does not shift subword hits; the benchmark unpacks the selected link in registers.
- Even stored keys and odd query keys prevent early equality termination while retaining real data-dependent branch direction.
- Separate 31-entry shards run every mode before measurement to warm all instruction bodies without consuming measured data.
- The generated image contains only the 110 measured nodes and 50 warm nodes, rather than a sparse 1.25-MiB array. This avoids simulator-only initialization and cache-scrub work while retaining real data-dependent branch and address selection.
- The generated data and queries are deterministic; `testing/generate_nano_lookup_data.py` owns `testing/nano_lookup_data.h`.

The one-node-per-line layout preserves binary-search decisions while representing the index as linked cache-line nodes, closer to a database tree than Nishanov's packed x86 integer array. This deliberate difference makes BlackParrot's cache-line overlap observable with a simulator-sized image and must accompany every cross-platform discussion.

## Runtime-selected modes

One ELF/NBF contains every mode. The host patches only `benchmark_mode` before releasing the processor.

| Mode | Schedule | Purpose |
| ---: | --- | --- |
| 0 | Serial demand | Ordinary binary-search baseline with no explicit handoff or prefetch. |
| 1 | Demand ring | Ten workers calculate a midpoint, switch, then perform the cold load. |
| 2 | Worker prefetch | Each worker prefetches its midpoint, switches, then consumes it when resumed. |
| 3 | Matched batch | One explicit state machine issues the same ten midpoint prefetches, then consumes the same ten values. |
| 4 | Switch-only | The same ten-worker ring and eleven rounds without index accesses. |
| 5 | Serial prefetch | One context hints and immediately consumes every node, isolating the detached hint path from scheduling overlap. |
| 6 | C++20 coroutines | One compiler-generated coroutine frame per query; each hints its next node, suspends, and resumes through a round-robin symmetric-transfer scheduler. |

`NANO_WORKERS=2..10` selects the query/shard count without rebuilding the executable. The primary quantities for the extension are `C++ coroutine cycles / worker-prefetch cycles`, `serial-prefetch cycles / worker-prefetch cycles`, and `(worker-prefetch cycles - matched-batch cycles) / matched-batch cycles`. Switch-only is reported as a decomposition control and is not subtracted from another mode.

## Matched-state and timing contract

Every mode seeds the same selected inactive contexts, clears the same result records, drains architectural traffic, and runs all seven dummy modes in a fixed order. Warmup uses physically separate nodes, so the immutable measured paths remain untouched and cold until the explicit BEGIN marker and physical-cycle `0xCC0` timestamp. END and the second timestamp immediately follow the operation; result verification and printing are outside the timed interval. Trace windows use the committed cycle-counter instruction PCs, because the simulator's MMIO marker printout trails that architectural boundary.

Coroutine frames are allocated from a fixed ten-frame pool during `prepare`, before BEGIN, and destroyed after END. The measured coroutine interval therefore includes compiler-generated suspend/resume and scheduling work but excludes frame construction/destruction. It uses the same aligned loads, prefetch primitive, result records, queries, and correctness oracle as the hardware and explicit-state-machine modes; no hosted allocator or exception runtime is linked.

Every data mode publishes and checks each query's lower bound, path checksum, step count, and completion flag. Switch-only publishes through the same result storage with zero data results. A transcript is accepted only when its runtime mode, ten-query count, eleven-level count, program-specific PASS marker, `CORE PASS`, and host `BSG PASS` agree.

Trace analysis must report first/last accepted hint, first/last AXI request, first/last response, and first/last consuming load for the measured window. It must also state whether all ten requests in a level were accepted before the first response and compare worker versus batch issue spans under the same capacity and arbitration.

## Commands

Compile or run one mode from the repository root:

```sh
make -C testing "$(pwd)/riscv/bp-tests/mt_nano_lookup_benchmark.riscv" \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10

make -C testing run-mt_nano_lookup_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 NANO_MODE=2 NANO_WORKERS=10 TRACE=1 \
  SIM_DEFINES='BP_AXI_MEM_PIPELINED BP_AXI_MEM_READ_LATENCY=200 BP_AXI_MEM_READ_QUEUE_DEPTH=10'

codex-skills/bp-memory-interleaving-app/scripts/launch_nano_lookup_matrix.sh \
  logs/nano-lookup-$(date -u +%Y%m%dT%H%M%SZ)
```

Run modes serially because they share simulator program, log, and waveform artifacts. Preserve and hash each completed waveform before starting the next mode. The launcher returns immediately, refuses a dirty worktree, holds a simulator lock, and performs the six runs plus trace analysis in the background. `NANO_ANALYZE=0` archives all rows first when faster simulator turnaround matters; trace analysis can then operate on the closed waveforms.

## Results and status

The C++20 extension's untraced simulator screening used the same combined executable and synthetic 200-cycle AXI configuration at 2, 6, 8, 9, and 10 active queries. These rows are tuning diagnostics, not the final trace-qualified result:

| Queries | Worker prefetch | Serial prefetch | C++20 coroutine | Coroutine / worker | Serial / worker |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 2,624 | 5,104 | 2,929 | 1.116x | 1.945x |
| 6 | 5,962 | 15,244 | 6,429 | 1.078x | 2.557x |
| 8 | 6,050 | 20,327 | 8,579 | 1.418x | 3.360x |
| 9 | 6,274 | 22,852 | 9,644 | 1.537x | 3.643x |
| 10 | 6,624 | 25,396 | 11,171 | 1.686x | 3.834x |

Ten is the best tested setting for the intended throughput comparison: worker cost per useful load falls from 119.3 cycles at two queries to 60.2 at ten, and ten gives the largest measured advantage over both controls. The non-monotonic ratio at six queries is why the selected count is based on an explicit sweep rather than assumed from queue capacity. The final N=10 hardware/coroutine/batch controls still require a clean trace-qualified matrix from the committed extension before these diagnostic numbers become an accepted result.

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
