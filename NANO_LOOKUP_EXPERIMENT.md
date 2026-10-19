This document defines and records the Nano-coroutine-style index-lookup experiment. It keeps the workload contract, matched controls, measurements, rejected evidence, and pull-request status together so benchmark changes cannot silently change the paper claim.

# Nano-style index lookup experiment

## Research question

Can ten hardware contexts hide the dependent cold-memory latency of independent binary index lookups, and how closely can they approach a software state machine that batches the same requests?

This is the algorithmic workload from Gor Nishanov's CppCon 2018 “Nano-coroutines to the Rescue” benchmark: multiple independent binary searches over a sorted index. It is not a full database engine. A database integration is justified only if this controlled index workload establishes a useful mechanism and identifies which overhead remains.

## Workload

- Ten absent-key lower-bound queries fan out across ten independent sorted index shards. This preserves Nishanov's multi-lookup decision algorithm while modeling a database/search tier querying independent partitions rather than manufacturing concurrency from one shared root line.
- Each logical shard has 2,047 entries and an immutable eleven-node search path. Every 64-byte node contains the binary-search midpoint key and branch-selected next-node link, yielding eleven dependent cold lines per query and 110 useful loads in every data mode.
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

The primary quantities are `demand-ring cycles / worker-prefetch cycles` and `(worker-prefetch cycles - matched-batch cycles) / matched-batch cycles`. Switch-only is reported as a decomposition control and is not subtracted from another mode.

## Matched-state and timing contract

Every mode seeds the same nine inactive contexts, clears the same ten result records, drains architectural traffic, and runs all five dummy modes in a fixed order. Warmup uses physically separate nodes, so the immutable measured paths remain untouched and cold until the explicit BEGIN marker and physical-cycle `0xCC0` timestamp. END and the second timestamp immediately follow the operation; result verification and printing are outside the timed interval.

Every data mode publishes and checks each query's lower bound, path checksum, step count, and completion flag. Switch-only publishes through the same result storage with zero data results. A transcript is accepted only when its runtime mode, ten-query count, eleven-level count, program-specific PASS marker, `CORE PASS`, and host `BSG PASS` agree.

Trace analysis must report first/last accepted hint, first/last AXI request, first/last response, and first/last consuming load for the measured window. It must also state whether all ten requests in a level were accepted before the first response and compare worker versus batch issue spans under the same capacity and arbitration.

## Commands

Compile or run one mode from the repository root:

```sh
make -C testing "$(pwd)/riscv/bp-tests/mt_nano_lookup_benchmark.riscv" \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10

make -C testing run-mt_nano_lookup_benchmark \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 NANO_MODE=2 TRACE=1 \
  SIM_DEFINES='BP_AXI_MEM_PIPELINED BP_AXI_MEM_READ_LATENCY=200 BP_AXI_MEM_READ_QUEUE_DEPTH=10'

codex-skills/bp-memory-interleaving-app/scripts/launch_nano_lookup_matrix.sh \
  logs/nano-lookup-$(date -u +%Y%m%dT%H%M%SZ)
```

Run modes serially because they share simulator program, log, and waveform artifacts. Preserve and hash each completed waveform before starting the next mode. The launcher returns immediately, refuses a dirty worktree, holds a simulator lock, and performs the five runs plus trace analysis in the background.

## Results and status

The current sharded worker mode passes under `BP_AXI_MEM_PIPELINED`, 200-cycle reads, a ten-entry AXI read queue, ten prefetch slots, two resident threads, and ten logical contexts. It reports 217,970 cycles for 110 checked dependent loads; its marker-scoped trace analysis is still running asynchronously. This is a correctness row, not yet a speedup, because the demand-ring and matched-batch rows are not complete.

| Mode | Total cycles | Request issue span | Last response | Checks |
| --- | ---: | ---: | ---: | --- |
| Demand ring | pending | pending | pending | pending |
| Worker prefetch | 217,970 | analysis pending | analysis pending | pass |
| Matched batch | pending | pending | pending | pending |
| Switch-only | pending | n/a | n/a | pending |

The exact consuming-load labels have been confirmed by disassembly, the generated header is deterministic, and all 17 checker/harness tests pass. A shared-index precursor passed worker mode at 3,601 cycles under the default short-latency model. Its marker-scoped trace had zero UCE/AXI transactions at BEGIN, 110 consuming loads, but only 94 UCE prefetch transactions and a maximum of one reserved slot; common upper-tree lines and six-cycle responses made it unsuitable for the intended ten-request capacity comparison. That result is retained only as a superseded diagnostic in `logs/nano-lookup-interleaving-20261019/sim-default-mode2/`.

The current sharded benchmark still requires all five 200-cycle-model modes, matched trace analysis, and a regression run of `mt_dependent_stream_benchmark` before review readiness.

FPGA implementation is intentionally deferred. If simulation supports the workload claim, run one final routed/physical acceptance after the branch is stable and record exact top/RTL commits, configuration, Vivado version, utilization, timing, NBF/bitstream hashes, and processor-reset sample procedure here and in the PR body.

## Pull request

The branch is independent of protected RPC and is based on `review/protected-rpc-base`. Add the PR URL, exact base/head, benchmark table, accepted commands, and unresolved gates here immediately after the PR is opened, and keep the PR body synchronized with material benchmark changes.
