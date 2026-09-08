This file records the research objective and the acceptance criteria for the next experiment. It separates the context-switch mechanism already demonstrated on BlackParrot from the cache-overlap and application-speedup claims still to be tested.

# Research direction

The objective is to make cooperative context switches cheap enough that one
worker can request data, yield while it arrives, and resume with less exposed
memory latency. Cold-cache cost is a hypothesis to measure for the selected
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

The September 8 load-ahead experiment establishes overlap with a pending full-line
refill. `bp_load_ahead()` in `software/include/bp_load_ahead.h` emits an ordinary
faulting `lbu x0` to valid cacheable data; it is not a nonfaulting prefetch hint.
The active unicore Dcache enables hit-under-miss (`features_p=0x1f5`), retains one
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

Multiple simultaneous cold misses remain unimplemented. Before expanding miss
capacity or adding a nonfaulting prefetch instruction, qualify request ownership,
backpressure, translation/fault handling, and refill completion. The current
software helper must not be treated as a safe hint for arbitrary addresses.

## Matched application experiment

Next, extend the small scheduling experiment to a controlled memory workload
with repeated independent datasets, mode-order rotation, working-set and useful-work
sweeps, then compare these application modes:

1. Serial dependent loads with no prefetch.
2. Single-worker batched prefetch/load.
3. Software coroutine prefetch/yield/load.
4. Hardware context prefetch/switch/load.

Use identical data, deterministic random indices or independent pointer chains,
request counts, worker work, checksums, and timing boundaries. Allocate, seed,
and warm up outside steady-state timing; report cold-start separately. Start
with the supported two-resident/four-logical topology and vary workers within
that capacity, then sweep working-set size across cache capacity and vary useful
work between request and consumption. Include a no-prefetch handoff control to
separate scheduler overhead from cache benefit.

Report raw core-wide `0xCC0` cycles, cycles/request, throughput, sample spread,
and checksum correctness. Pair these with waveform request/refill overlap,
architectural redirect-to-useful-work cycles, and instruction/data cache tails.
Keep FPGA area/timing cost and exact binary/RTL identities with the results.
A speedup must survive these matched controls; the existing 5.10/11.12 FPGA
cycles/switch are a mechanism measurement, not an application-speedup claim.
