This simulator-only artifact tests whether the Nano hardware-context result survives a strong, matched software comparison. It freezes one O3 executable, validates every transcript, discloses the full worker-count sweep, and traces the N=8 hardware and best-batch rows. No FPGA was used.

# Peer-review Nano comparison

## Result

At the most favorable disclosed point, N=8, hardware worker prefetch takes
2,810 cycles and the best tested explicit software schedule, a fixed-count
unrolled structure-of-arrays batch, takes 3,817 cycles. Hardware is therefore
1.358x faster (31.932 versus 43.375 cycles per useful node). The best tested
C++20 coroutine takes 5,567 cycles, or 1.981x hardware, but the batch—not the
coroutine—is the defensible best-software headline.

The 1,007-cycle hardware/batch gap is fully closed by retirement accounting.
Batch retires 63 fewer instructions but has 1,070 more cycles without a
retirement: `(-63) + 1,070 = 1,007`. Request tracing supports a scheduling
explanation: both peak at eight outstanding hints, but hardware averages
6.483 over its whole window versus 4.772 for batch and issues the 88 hints over
2,529 versus 3,359 core cycles.

## Fairness contract

| Control | Hardware vs fixed batch | Other rows |
| --- | --- | --- |
| Executable and data | Same O3 ELF/NBF; runtime patch changes only mode/N | O2 is a separate compiler-sensitivity image and is never mixed into O3 ratios |
| Work | Same N shards, eleven dependent nodes per shard, queries, result records, and oracle | Switch-only has no data work and is diagnostic only |
| Transport | Same 16-byte detached hint and aligned consuming loads | Serial/demand ring use ordinary full-line demand transport and are not headline comparisons |
| Initial history | Every invocation warms all eleven bodies in fixed order on separate warm data, then runs switch-only | Measured nodes remain untouched before BEGIN |
| Timed boundary | Mode/N dispatch, setup, frame construction, and traffic drain precede BEGIN; all bodies use the same indirect call | Coroutine suspend/resume and scheduling remain inside; frame construction/destruction remain outside |
| Optimization | Nano defaults to O3; fixed batches are specialized for N=2..10; coroutine schedulers are compile-time-specialized | O2 control changes the complete image consistently |
| Correctness | Lower bound, checksum, step count, completion, guest PASS, CORE PASS, and host PASS | All 34 Nano transcripts and the dependent-stream regression pass the maintained checker |
| Execution | Shared simulator runs are serialized; isolated lanes contain byte-identical model/NBF files | Trace runs are sequential; no FPGA run is included |

This contract deliberately does not force identical schedulers or state
placement. Hardware keeps each search's live state in context-private
registers and hands off with `csrw 0x800`; software keeps explicit per-search
state and schedules it. That difference is the mechanism under test.

## Exact N=8 O3 matrix

Every row below comes from the same ELF/NBF/model and performs 88 useful node
visits except switch-only. Cycles/node for switch-only is shown only as a
normalization diagnostic and is not subtracted from another row.

| Mode | Implementation | Cycles | Cycles/node | Classification |
| ---: | --- | ---: | ---: | --- |
| 0 | Serial demand | 290,537 | 3,301.557 | transport-mixed baseline |
| 1 | Demand ring | 290,728 | 3,303.727 | transport-mixed diagnostic |
| 2 | Hardware worker prefetch | 2,810 | 31.932 | headline |
| 3 | Historical runtime-count batch | 5,569 | 63.284 | weaker software diagnostic |
| 4 | Switch-only | 1,211 | 13.761 | diagnostic; no subtraction |
| 5 | Serial prefetch | 20,331 | 231.034 | same-hint overlap control |
| 6 | Checked C++20 coroutine | 8,793 | 99.920 | implementation comparison |
| 7 | Fixed unrolled SoA batch | 3,817 | 43.375 | best-software headline |
| 8 | Fixed recompute batch | 4,077 | 46.330 | batch design sensitivity |
| 9 | Lean-queue C++20 coroutine | 6,623 | 75.261 | implementation comparison |
| 10 | Direct C++20 coroutine | 5,567 | 63.261 | best coroutine |

Thus hardware is 7.235x faster than serial prefetch under the same hint
transport, 1.358x faster than the best explicit batch, and 1.981x faster than
the best coroutine. The first ratio measures the benefit of interleaving in
addition to implementation overhead; only the fixed-batch ratio is the
best-software headline.

Switch-only executes 96 handoffs at N=8: eight workers times eleven rounds,
plus one eight-context terminal lap. Its 1,211 cycles are therefore 12.615
cycles per complete handoff on average. The roughly three-cycle target-launch
observation from the focused context trace is only one microarchitectural
portion of that interval; redirect, loop instructions, publication, and
nonresident context handling surround it. Switch-only is still not subtracted
from a data mode because those costs overlap memory differently.

## Disclosed N sweep

The same O3 ELF/NBF/model supplies every row. N=8 maximizes the observed
batch/hardware ratio; it is selected after, and disclosed with, the full sweep.

| N | Hardware | Fixed batch | Batch / hardware |
| ---: | ---: | ---: | ---: |
| 2 | 2,595 | 2,710 | 1.044x |
| 3 | 2,638 | 2,835 | 1.075x |
| 4 | 2,688 | 2,973 | 1.106x |
| 5 | 2,717 | 3,129 | 1.152x |
| 6 | 2,724 | 3,395 | 1.246x |
| 7 | 2,776 | 3,551 | 1.279x |
| **8** | **2,810** | **3,817** | **1.358x** |
| 9 | 3,069 | 4,049 | 1.319x |
| 10 | 3,410 | 4,276 | 1.254x |

`sweep.csv` is generated from qualified transcripts, not hand-entered.

## Sensitivity and repeatability

The O2 N=8 control is hardware/batch/direct-coroutine = 2,795/3,813/5,640
cycles; its batch/hardware ratio is 1.364x versus 1.358x at O3. Three O3 N=8
runs each produce exactly 2,810 hardware cycles and 3,817 batch cycles (zero
observed variance). These deterministic simulation repeats establish
repeatability, not a confidence interval for physical hardware.

## Trace attribution

The clean trace model and O3 image reproduce the non-trace timing exactly.
Committed cycle-counter PCs `0x800059de`/`0x800059e6` select the final of 13
ordered `run_window` pairs; the boundary instructions are excluded.

| N=8 mode | Cycles | Retired | No-retirement | IPC |
| --- | ---: | ---: | ---: | ---: |
| Hardware worker | 2,810 | 1,647 | 1,163 | 0.586 |
| Fixed batch | 3,817 | 1,584 | 2,233 | 0.415 |
| Direct C++20 coroutine | 5,567 | 5,076 | 491 | 0.912 |
| Batch minus hardware | +1,007 | -63 | +1,070 | n/a |
| Direct coroutine minus hardware | +2,757 | +3,429 | -672 | n/a |

The coroutine therefore hides waiting successfully but executes 3.083x as
many instructions as hardware. Its 2,757-cycle deficit closes exactly as
`3,429 - 672`: about 38.966 additional retired instructions per useful node
more than offset its 7.636 fewer no-retirement cycles per node. Symbol ranges
place 4,872 of the 5,076 retirements inside the specialized direct-coroutine
actor and 202 in its operation/drain wrapper; labels divide the actor at the
consuming load, so these ranges are not individual-operation counts.

UCE transaction analysis covers measured indexes `[0x80010000,0x80011b80)`
and begins with zero outstanding measured-region work in all three modes:

| N=8 mode | Hints / UCE transactions | Ordinary UCE reads | Peak | Average, whole window | Average, active interval | Issue span |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hardware worker | 88 / 88 | 0 | 8 | 6.483 | 6.658 | 2,529 core cycles |
| Fixed batch | 88 / 88 | 0 | 8 | 4.772 | 5.108 | 3,359 core cycles |
| Direct C++20 coroutine | 88 / 88 | 0 | 5 | 3.272 | 3.554 | 4,918 core cycles |

All three schedules accumulate the same 18,216 outstanding-request-cycle area,
as expected from 88 identical request lifetimes. Hardware packs that area into
the shortest window. The coroutine executes useful/control instructions almost
continuously, but those instructions space new hints far enough apart that it
never has more than five live requests. This is low overhead relative to an OS
thread or stackful switch, but not zero instruction cost relative to custom
register-context hardware on this fine-grained workload.

The hardware and direct-coroutine traces each record 88 retirements at their
specialized consuming-load PCs, `0x80000d78` and `0x80005074`. The unrolled
batch has multiple generated load sites, so its overlap report does not assert
a single consuming-load PC.
Matched-region AXI correlation returned no transactions despite the documented
address transform; no AXI occupancy or backing-bank parallelism claim is made.
UCE request/response completeness, occupancy, and ordinary-read absence remain
qualified. No-retirement cycles combine memory waiting, redirect, and pipeline
effects; the trace does not uniquely assign every such cycle.

## Reproduction identities

- O3 ELF: `98c45aafc6aacd0423e9ac968cdfc38f8c0f08853a16ebdd907ad00160b1e256`
- O3 NBF: `721e75191bd64aad5a748280a78cbb344e1178ea8f9041b987e657f7c67afe4b`
- O2 ELF: `39294fab6d7085ef0347bfd3fa83da58c8e70d746fe8d22d040afe8535a16ece`
- O2 NBF: `acace5b58ce170727b95cc864b67069692efe7a0e5dcdf4a9d3c8472ee18a62e`
- Clean non-trace model: `85afe9d4e32ac8d05a8378fa257115442355da1f3d4e29c626903e8b9b46b277`
- Clean trace model: `d3f9c56ea24eeee80285ad8d6582a7f6f08dbae192050f91284a33807ba111eb`
- Topology/model: two physical threads, ten logical contexts, ten detached-hint slots, pipelined synthetic reads with 200-cycle latency and queue depth ten
- Compiler: canonical `/home/coyang/zynq-parrot/install` RISC-V toolchain; Nano `-O3` default plus explicit `-O2` sensitivity image

Representative clean build configuration:

```sh
make clean
ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install \
ZP_RISCV_DIR=/home/coyang/zynq-parrot-nano-lookup/riscv \
VERILATOR_BUILD_JOBS=4 make build NUM_THREADS=2 NUM_CONTEXTS=10 \
  EXTRA_DEFINES='BP_AXI_MEM_PIPELINED BP_AXI_MEM_READ_LATENCY=200 BP_AXI_MEM_READ_QUEUE_DEPTH=10 BP_DCACHE_PREFETCH_ELS=10 BP_PREFETCH_AXI_BYPASS'
```

Validate a retained Nano transcript:

```sh
python3 testing/check_run.py path/to/run.log \
  --test mt_nano_lookup_benchmark --exit-code 134 \
  --nano-mode MODE --nano-workers N
```

Regenerate the tables:

```sh
python3 logs/nano-peer-review-20261101/generate_results.py
```

## Evidence layout and rejected attempts

- `runs/` contains 34 qualified Nano transcripts and the independent
  dependent-stream regression.
- `results.csv` and `sweep.csv` are mechanically generated from those logs.
- `trace/` contains accepted run logs, retirement reports, overlap reports,
  executable/image hashes, and raw-waveform hashes. Raw FSTs are not committed.
- `builds/` contains clean non-trace/trace build logs and the failed incomplete-
  worktree build log.

No failed setup produced a retained performance row. An initial clean build
used an empty worktree-local install and stopped before Verilator; the accepted
build was cleaned again with explicit canonical paths. A later regression
wrapper selected incomplete local collateral and also stopped before
simulation; the accepted dependent-stream run uses the exact clean model and
passes the checker. Manual launches missing the Boost library path or NBF
argument never started the guest. Two overlap-analyzer invocations were
self-rejected for conflicting window selectors and missing address bounds;
their outputs were overwritten by the accepted committed-PC reports.
