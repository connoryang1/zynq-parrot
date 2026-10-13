# Protected local RPC Linux prototype

This document defines the smallest Linux experiment that can test the protected
local RPC claim without first replacing the Linux scheduler. It deliberately
supports one pinned caller, one parked server, and one in-flight call.

## Required hardware boundary

Installing the protected descriptor reserves logical contexts 0 and 1 as a
pair. While the descriptor is installed, U- and S-mode code must not use the
legacy context-switch, NPC/register-seed, direct cache-service, or miss-trace
CSRs to enter, rewrite, or inspect the protected context. M-mode retains those
operations for setup and teardown. CSR `0x808` remains the U-mode call gate and
CSR `0x809` remains the server's U-mode return gate.

The descriptor has three M-mode lifecycle operations:

- install context 0 -> context 1 with one immutable U-mode service entry;
- query whether a call is active;
- revoke only while no call is active, then scrub context 1 before allowing its
  resources to be reused.

The current transport implementation still permits the legacy U-mode CSRs, so
it proves fixed-entry transport but does not yet meet this boundary.

## Userspace interface

An experimental character driver is sufficient for the first prototype. A
server thread pinned to the test CPU opens `/dev/bp_rpc` and issues a register
ioctl containing:

- the U-mode service entry;
- a U-mode initialization trampoline;
- an initial U-mode stack pointer; and
- the address and size of the explicitly shared buffer.

The driver validates executable/readable/writable VMAs, faults and pins the
service, trampoline, stack, and shared pages, takes references to the server
`task_struct` and `mm_struct`, and derives the server SATP root and hardware ASID.
Only one binding may exist. Registration fails unless the server and eventual
caller are pinned to the same supported CPU.

After registration, the server blocks in the ioctl. A caller registered by the
same file descriptor invokes `pcall` directly with four register arguments.
The server returns one register result with `preturn`; the common path performs
no syscall, scheduler entry, or software message copy.

Closing the descriptor or explicitly revoking it first asks M-mode to disable
new calls. Once no call is active, M-mode clears and scrubs context 1, the driver
unpins the pages and drops its task/mm references, and the sleeping server is
woken with either success or an error. Process exit and `mm` teardown use the
same revoke path.

## OpenSBI setup sequence

The existing OpenSBI vendor-extension dispatcher is the M-mode control path.
The register function receives the server SATP, fixed entry, initialization
trampoline, and stack from the trusted kernel.

1. OpenSBI records those values in M-mode-owned state and seeds context 1 to a
   machine bootstrap with the legacy M-only NPC operation.
2. It switches to context 1. The bootstrap installs the server SATP, prepares
   `mepc` and `sp`, disables context 1's interrupt-enable CSRs, and executes
   `mret` into the initialization trampoline.
3. The trampoline performs the one setup-time raw switch back to context 0.
   OpenSBI resumes after its switch instruction, installs the immutable
   protected descriptor, locks the legacy interfaces, and returns from the SBI
   call to Linux.

The fixed service entry is distinct from the initialization trampoline.
`pcall` always replaces context 1's resume PC with the protected entry, so the
trampoline cannot become a callable endpoint.

## First-prototype execution contract

Linux keeps scheduling context 0 normally. Context 1 executes only between
`pcall` and `preturn`, while the registered server task remains asleep. This
means the Linux per-CPU `current` pointer continues to name the caller during
the service. The first prototype is therefore valid only when the service:

- touches prefaulted, pinned pages;
- makes no syscall and takes no page fault;
- has machine and supervisor interrupt enables cleared in context 1; and
- completes within a bounded watchdog interval.

Any synchronous exception or unexpected interrupt from context 1 must be
intercepted by M-mode and fail the binding closed; it must not be delivered to
Linux as though the caller had raised it. Supporting arbitrary faults,
preemption, signals, and blocking calls requires per-context kernel ownership
or a monitor-mediated return to context 0 before Linux handles the event. That
is a later scheduler-integration phase, not part of the first latency result.

## Measurement

Use the same deterministic service body for all paths and report physical core
cycles around the complete caller-visible operation:

1. an in-process function call;
2. protected hardware RPC;
3. a shared-memory request plus futex/event notification; and
4. a Unix-domain socket or pipe round trip.

Measure first call, warm median, p95/p99, and calls per second. Include empty and
small compute/data services so the transition cost and useful-work fraction are
both visible. Verify that the caller cannot read the server-private page, alter
the fixed entry, forge `preturn`, invoke an invalid capability, or reach context
1 through any legacy CSR before accepting the protected result.
