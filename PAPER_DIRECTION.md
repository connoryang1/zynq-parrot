This file records the research motivation and a small next demonstration, not an implementation specification. It distinguishes what the FPGA has proved from the broader claims a future paper would need to establish.

# Research direction

The motivating paper is Jack Tigar Humphries, Kostis Kaffes, David Mazières, and
Christos Kozyrakis, “A Case Against (Most) Context Switches,” HotOS 2021,
DOI [10.1145/3458336.3465274](https://doi.org/10.1145/3458336.3465274).
It proposes many software-managed hardware threads so applications and system
services can hand off execution without repeatedly saving software contexts.

Its broader interface includes start/stop, remote register access, virtual thread
IDs and permissions, and monitor/wait notification. It discusses keeping inactive
state in on-chip storage and warming caches when threads become runnable.
Implementing all of that is not this project's immediate goal.

## What we have proved

The accepted PYNQ image boots Linux and runs a cooperating U-mode C program that
switches 0→2→0 through SRAM backing, executes a target-context Linux syscall,
and verifies register restoration. See [Linux acceptance](LINUX_BOOT_STATUS.md)
for identities, results, and limits.

This is a hardware/software feasibility demonstration—not evidence of faster
syscalls, a production-safe Linux threading API, or application speedup.

## First application experiment

Build a small same-process request/response service using cooperating contexts,
then compare it with an equivalent software-coroutine implementation. Keep useful
work, memory accesses, request counts, and timing boundaries matched; sweep work
per request and working-set size, and report both throughput and latency.

Start with explicit cooperative handoff and integer-only code. Add stress tests
for traps, timer interruption, repeated context reuse, and process lifecycle
before claiming robust Linux integration. Privileged services, independent
address spaces, permission enforcement, and FP preservation are separate work.

A convincing paper needs an application-level benefit plus measured area/timing
cost and limitations. The low switch-cycle result is a mechanism, not by itself
the application claim. Historical research options are preserved in
[the history checkpoint](HISTORY.md).
