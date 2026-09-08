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
application benchmark, complete FPGA/Linux acceptance of the current resident
CSR initialization and fetch/replay ownership fixes, while preserving the
nonresident translated handoff and register-target regressions. The
[checkout guide](CURRENT_CHECKOUT.md) records current revisions and the remaining
production-readiness gaps, including lifecycle, FP state, and isolation.

## Second gate: demonstrate actual memory overlap

Trace a cold data request and prove that useful work in another resident context
executes before the refill completes. Check emitted instructions and the active
cache request path; a compiler prefetch builtin that becomes a no-op is not an
experiment. The current Dcache permits some hit-under-miss activity but classifies
load misses as blocking requests, and no software-prefetch instruction has been
established for this endpoint. Nonresident handoffs drain outstanding memory
activity, so measure resident and nonresident behavior separately.

If this gate fails, define and qualify the required nonblocking request and
completion mechanism before expecting a prefetch/yield benchmark to hide
latency. It must handle request ownership, backpressure, traps, and refill
completion correctly. Cheap register-state replacement alone is insufficient.

## Matched application experiment

Once overlap works, compare four modes in one controlled memory workload:

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
