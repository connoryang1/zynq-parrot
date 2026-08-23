# Research Direction: Tiered Software-Controlled Hardware Threads

## Source and Motivation

This project is inspired by:

Jack Tigar Humphries, Kostis Kaffes, David Mazières, and Christos Kozyrakis,
"A Case Against (Most) Context Switches," HotOS 2021.

The paper argues that conventional systems multiplex many software contexts
onto a small number of hardware threads, repeatedly paying register-state,
scheduler, privilege-transition, and cache-warming costs. Its alternative is a
large set of software-controlled hardware threads. Software starts, stops, and
modifies these threads; blocked threads wait for events; exceptions and system
services can run in dedicated threads instead of replacing the current
thread's execution context.

The paper's proposed interface includes these concepts:

- many virtual thread IDs mapped onto physical hardware contexts;
- runnable, waiting, and disabled thread states;
- `start` and `stop` operations;
- remote register reads and writes (`rpull` and `rpush`);
- virtual-to-physical thread mappings and permissions through a thread
  descriptor table;
- generalized `monitor`/`mwait` notification, including device/DMA writes;
- a small number of pipeline-sharing contexts backed by a larger, cheaper
  store of inactive context state;
- software-controlled scheduling, priority, protection, and event handling.

Potential uses include interrupt replacement, blocking I/O without polling,
exception-less system calls, dedicated kernel or microkernel services,
isolated hypervisors, and thread-per-request distributed applications.

This repository does not need to implement the paper's entire architecture.
The paper serves as motivation and a vocabulary for selecting one concrete,
measurable use case.

## What This Repository Already Demonstrates

The current BlackParrot implementation separates the number of software-visible
logical contexts from the number of pipeline-facing register banks:

- two physical resident context slots execute through the core;
- additional logical-context state is retained in a dedicated on-chip SRAM
  hierarchy;
- software names logical contexts with custom CSRs;
- hardware resolves resident hits and restores nonresident state;
- inactive contexts do not require a conventional software register-save
  sequence;
- the FPGA implementation fits and meets timing on PYNQ-Z2.

At the accepted checkpoint:

- resident steady-state ring spacing is 5.09 physical cycles/switch;
- nonresident SRAM-backed ring spacing is 12.14 physical cycles/switch;
- incremental nonresident cost over the matched resident ring is 7.04 cycles;
- exact PYNQ simulation and physical FPGA totals match exactly;
- the waveform-derived nonresident redirect-to-first-useful-work result is
  dominated by 12 cycles;
- the design uses 47,518 / 53,200 LUTs, 21,427 registers, 80 block-RAM tiles,
  and 11 DSPs, with routed WNS +1.283 ns and TNS 0.

The core-wide physical-cycle CSR `0xCC0` makes these measurements possible
without relying on virtualized `mcycle` or host-side markers.

## Important Distinction

The current CSR operation is still an explicit transfer from one logical
context to another. The broader HotOS model describes independently runnable,
waiting, and disabled hardware threads selected by hardware under software
policy.

Our current design should therefore be described as a **tiered hardware
context substrate**. It is a mechanism on which a software-controlled hardware
thread API can be built, not yet a complete implementation of the original
paper's scheduling, notification, exception, or protection model.

Resident versus nonresident placement should remain an implementation detail.
Software should eventually name a virtual thread and receive the same API and
correctness semantics regardless of where its state is stored.

## Proposed New-Paper Question

The most achievable and defensible next research question is:

> Can a small number of pipeline-resident contexts plus an SRAM-backed tier
> provide a practical, software-controlled hardware-fiber abstraction under a
> conventional operating system?

This is narrower than eliminating interrupts, system calls, VM exits, and OS
scheduling. It is broad enough to produce a new systems/architecture result:

1. a tiered implementation that scales logical contexts without replicating
   complete pipeline-facing register banks;
2. a Linux-visible API for creating and handing off hardware fibers;
3. measured latency, area, capacity, and application behavior;
4. an analysis of cache effects and the resident/nonresident boundary;
5. a comparison with software fibers and Linux threads.

## Recommended First Application

Implement cooperative hardware fibers inside one trusted Linux process pinned
to one BlackParrot core.

Version one should deliberately use a narrow contract:

- all fibers share one Linux process and one `satp` address space;
- each fiber has an independent PC, stack, integer-register image, and TLS
  pointer;
- a small kernel driver owns allocation and initialization;
- fibers switch cooperatively rather than through timer preemption;
- the process does not migrate between cores;
- floating-point and vector state are initially rejected or explicitly
  unsupported;
- resident/nonresident placement is invisible to the application;
- ordinary Linux process isolation remains outside the hardware-fiber pool.

The user-facing prototype should resemble:

```c
bp_fiber_t worker;

bp_fiber_create(&worker, worker_entry, worker_stack, sizeof(worker_stack));
bp_fiber_yield(&worker);
```

The first application should be a bounded producer/consumer or request-pipeline
workload with more fibers than resident slots. Each fiber performs a small
amount of work and explicitly hands off to the next fiber. This provides:

- a correctness test with shared memory and independent stacks;
- controlled resident and nonresident populations;
- tunable work per handoff;
- a straightforward software-fiber baseline;
- a way to identify when a 5-12-cycle handoff affects end-to-end throughput;
- a foundation for a later blocking queue or event-wakeup experiment.

This workload is preferable to starting with an interrupt replacement or
exception-less syscall. Those use cases require simultaneous changes to
privilege handling, exception delivery, kernel control flow, and device event
routing, making failures difficult to attribute.

## First Milestone

The first milestone is not “port the complete mechanism to Linux.” It is:

> Boot a reproducible Linux image and run one process with two kernel-created
> hardware fibers that share an address space, use independent stacks, exchange
> a counter through shared memory, hand off in both directions, and return
> cleanly to ordinary Linux execution.

Required evidence:

1. Linux boots repeatedly on the accepted FPGA bitstream.
2. A baseline program reads CSR `0xCC0` without switching.
3. The driver allocates a logical context owned by the calling process.
4. Context creation clones safe privilege and address-space metadata from the
   caller and replaces only the documented initial registers.
5. The target executes on its own stack and returns through a defined
   trampoline.
6. Shared-memory values survive at least one million bidirectional handoffs.
7. Timer interrupts are initially disabled around the hardware operation, then
   enabled in a separate validation stage.
8. Failures report creation, dispatch, restore, target-entry, return, and trap
   stages separately.
9. Physical-cycle results are reported separately from syscall/driver setup
   overhead.

This milestone answers the most important feasibility question: whether the
bare-metal context substrate can coexist with Linux virtual memory, privilege,
interrupt, and process state without corrupting the OS.

## Hardware/Software Contract Needed Before Linux Switching

The bare-metal seeding CSRs are not yet a complete Linux-safe creation API.
Before allowing a normal process to switch, define:

- which integer and control registers belong to a logical context;
- how a new context inherits `satp`, privilege, status, and exception state;
- how `tp`, `sp`, `gp`, argument registers, and the return trampoline are
  initialized;
- what happens when an interrupt, fault, or NMI-like event arrives during each
  transfer phase;
- whether a running context may be remotely modified;
- how logical IDs are allocated, reclaimed, and invalidated;
- how context ownership is checked;
- how stale IDs are prevented from naming a different process's context;
- how FP/vector use is detected or rejected;
- whether physical counters and debug status remain core-wide or per-context.

A useful small hardware extension is **clone current context into disabled
logical context N**, with explicit replacement values for PC, SP, argument,
and TLS registers. This avoids asking userspace to reconstruct privileged state
and creates a stable basis for both a kernel driver and later direct userspace
handoffs.

## Evaluation Plan

Compare four implementations on the same BlackParrot/Linux configuration:

1. direct hardware-fiber handoff after setup;
2. kernel-mediated hardware-fiber handoff;
3. a software fiber implementation that saves/restores registers in memory;
4. Linux threads using a synchronization primitive appropriate to the test.

Report:

- physical cycles per handoff;
- user-visible API latency;
- throughput versus work per handoff;
- resident and nonresident population sizes;
- cache-hot and cache-cold behavior;
- FPGA area and timing;
- maximum supported logical contexts;
- correctness under timer interrupts, page faults, and process termination;
- setup/allocation cost separately from steady-state switching.

The primary application graph should scale from two fibers to more fibers than
resident slots. A second experiment can convert the producer/consumer handoff
into a blocking queue once runnable/waiting state or `monitor`/`mwait` support
exists.

## Explicit Non-Goals for the First Paper

- replacing every Linux scheduler context switch;
- eliminating all interrupts;
- exception-less system calls;
- VM-exit or hypervisor integration;
- cross-process hardware-context switching;
- cross-core migration;
- a complete thread descriptor table and arbitrary delegation graph;
- production-ready FP/vector virtualization;
- DMA-triggered generalized `monitor`/`mwait`.

These remain extensions, not prerequisites for demonstrating that tiered
hardware contexts provide a useful Linux-visible execution abstraction.

## Immediate Next Actions

1. Complete the corrected FPGA regression ladder for the accepted bitstream.
2. Acquire or reproducibly build a one-hart Linux/OpenSBI/initramfs NBF.
3. Establish a repeated Linux boot-and-shell baseline with recorded hashes.
4. Audit current context metadata initialization under supervisor and user
   modes.
5. Specify the clone/create ABI before changing RTL.
6. Implement the smallest bare-metal clone-context conformance test.
7. Only then add the Linux driver and two-fiber application.

