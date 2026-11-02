This document fixes the first seL4/BlackParrot hardware boundary before RTL or
kernel integration.  It refines Stage 4 of
[`SEL4_HARDWARE_IPC_PLAN.md`](../SEL4_HARDWARE_IPC_PLAN.md); the public API in
[`include/protected_rpc.h`](include/protected_rpc.h) remains independent of
BlackParrot CSRs and hardware-context numbers.

# BlackParrot protected-RPC kernel ABI

## First implementation scope

Version 1 has one descriptor slot, one caller, one resident passive server,
four 64-bit request words, and up to four 64-bit reply words.  The service must
be prefaulted, nonblocking, and integer-only. Preparation leaves
`mstatus.FS=Off`; floating-point registers are not scrubbed because the service
cannot access them, and any service requiring FP must use ordinary seL4 IPC.
General endpoint queues, capability transfer, multiple callers, nested calls,
migration, and server faults use ordinary seL4 IPC until separately
implemented.

The application continues to name an seL4 endpoint.  A kernel-authorized
runtime binding privately associates that endpoint with an opaque hardware
token; applications never supply a context ID, SATP, entry PC, or stack.

The kernel checks the proposed entry is executable, the stack is writable,
and every nonzero GP/TP is readable in the live server VSpace. TP may name
trusted server-runtime state, but it is never sourced from request data.

Version 1 may additionally bind one 4 KiB shared region. The trusted runtime
supplies a binding-scoped opaque name plus page-aligned caller and server
virtual addresses. The kernel walks both live VSpaces, requires user-readable
4 KiB leaves, requires caller write access and the requested server write
access, and proves both leaves name the same physical page before publishing
the hardware descriptor. The name is not a pointer or capability; endpoint
authority and the validated mappings authorize access. Any later map, unmap,
VSpace replacement, or ASID teardown follows the existing synchronous whole-
binding revocation path before the mapping can be reused.

The server's region table performs the per-call name, offset, length, and
direction check for both hardware and software transport. The hardware shadow
receives only a trusted runtime-state pointer in its initial TP; callers never
provide a server virtual address in a request. Zero region size retains the
scalar-only binding. Larger regions, multiple regions, read-only caller maps,
and selective rather than whole-binding revocation remain later ABI versions.

## Descriptor

The single hardware slot contains:

```text
valid
token                         64-bit opaque value, changed on every reuse
caller_satp                   complete Sv39 address-space identity
caller_context                initially logical context 0
server_satp                   complete Sv39 address-space identity
server_context                initially logical context 1
server_entry                  fixed, canonical user PC
request_words / reply_words   each 0..4
```

The byte-exact versioned installation image and outcome/control values are in
[`internal/blackparrot_rpc_abi.h`](internal/blackparrot_rpc_abi.h).  It also
supplies the initial server stack/global/thread pointers and caller badge; the
hardware installs the badge in `s1` (a fixed, non-message register) for the
trusted runtime, which passes it to the common server dispatcher.

The server context's general-register image, including its private stack, is
prepared by the privileged installer.  A token match alone is insufficient:
`pcall` also compares the effective WARL SATP and logical caller context. The
descriptor's mode, implemented ASID bits, and implemented root-PPN bits are
compared after the same narrowing applied by the core's SATP CSR; the root PPN
therefore remains part of the address-space identity even when software uses a
wider ASID namespace. This keeps a leaked or guessed token from becoming
ambient authority when seL4 schedules a different process in the same physical
hardware slot.

Installation and revocation are M-mode operations reached through one private
OpenSBI extension.  seL4 first suspends the caller and server, pins and
prefaults their required mappings, and validates the endpoint relationship.
OpenSBI then atomically publishes the complete descriptor.  Installation must
not expose a partially written descriptor.  Revocation clears `valid` before
the slot can be reused and fails with `BUSY` while a protected continuation is
active.  Reuse requires a new token, so a stale cached binding fails closed.

The first implementation may use one slot, but the ABI includes a slot and
version so later hardware can add a bounded descriptor table without changing
the public protected-RPC API.

## Atomic call outcome

The call instruction is a read/write CSR operation, not a separate eligibility
probe:

```asm
# a0-a3 = request, a4 = opaque token, a5 = request length metadata
csrrw a4, 0x808, a4
# a4 = outcome; a0-a3/a5 = reply and metadata only when COMPLETED
```

Hardware performs token, caller-SATP, context, residency, descriptor-valid,
and continuation-availability checks as one operation.  It produces exactly
one of these outcomes:

| Outcome | Service began? | Adapter action |
| --- | --- | --- |
| `COMPLETED` | yes, and returned | consume reply; never retry |
| `NOT_STARTED` | no | `AUTO` may invoke ordinary seL4 IPC once |
| `REVOKED` | no | forced hardware reports stale binding; `AUTO` may invoke ordinary seL4 IPC once |
| `COMMITTED_FAILED` | possibly | report failure; never retry |

`REVOKED` is also authoritative permission for the caller runtime to discard
its cached endpoint/token association: kernel lifetime hooks have made that
generation permanently unusable, and a later bind must be able to install a
fresh generation. `NOT_STARTED` is potentially transient and must not clear a
still-live association.

The one-slot prototype learns an implicit revocation lazily on that next
hardware attempt. A rejected zero-argument `UNBIND` is not equivalent proof:
it can also mean that a different TCB attempted the operation, so the adapter
must not discard a possibly live token on that error. A durable binding object
should synchronize kernel finalization and caller-runtime state directly.

Version 1 classifies the token atomically with the call: no live descriptor or
a generation mismatch returns `REVOKED`; a matching live descriptor that is
busy, nonresident, wrong-SATP, or otherwise temporarily ineligible returns
`NOT_STARTED`. Thus only a terminal token result releases the runtime's local
association. A separate
"eligible?" CSR is forbidden because revocation or scheduling state could
change between the query and the call.

On acceptance, hardware saves the caller continuation outside both untrusted
contexts, transfers the requested subset of `a0`--`a3` and the validated
request-length metadata in `a5`, installs the fixed server PC/address space,
and marks the descriptor active. The server returns
with CSR `0x809`; `a0`--`a3` carry reply words and `a5` carries reply metadata:
an 8-bit length, an 8-bit service status, and zero reserved bits. Hardware
transfers the declared reply length, bounded by the descriptor maximum, and
zeroes the remaining reply registers; it writes
`COMPLETED` to caller `a4`, consumes the continuation exactly once, and resumes
only the recorded caller. The server cannot select a return PC or caller.

The resident hardware prototype implements this precise outcome and four-word
reply contract. Its bare-metal descriptor-control, protected-transition, and
distinct-address-space library tests are mechanism evidence; they do not by
themselves prove the seL4 kernel binding or end-to-end accelerated IPC.

### Version-2 synchronous-fault completion candidate

Version 1 deliberately has no server-fault continuation. Version 2 preserves
the 112-byte descriptor layout but sets `version=2` and requires descriptor
flag bit 0, `FAULT_COMPLETION`; the installer maps that flag to staged
`CONFIG[48]`. Version 1 requires both the flag and `CONFIG[63:48]` to be zero.
Version 2 admits synchronous server faults only with the following atomic
contract. The directed hardware model implements the illegal-instruction case;
OpenSBI and seL4 installation remain version 1:

1. Acceptance changes the slot from `LIVE` to `ACTIVE`. A precise synchronous
   exception while the recorded server context is active changes it to
   `FAULTED`; it must not enter a userspace-provided trap vector.
2. Hardware discards younger work, consumes the protected continuation once,
   restores only the recorded caller, and returns `COMMITTED_FAILED`. Earlier
   retired server stores remain visible and are never replayed or rolled back.
3. `a0`--`a3` are zero and cannot expose a partial reply. `a5[7:0]` is a coarse
   failure class: 1 is `SERVER_FAULT`, 2 is `CANCELED`, and 3 is
   `BACKEND_ERROR`; bits 63:8 are zero. The descriptor version defines this
   encoding. Raw cause, fault PC, and fault address remain in a privileged
   per-slot record and are never returned to the caller directly.
4. `COMMITTED_FAILED` is terminal for that binding generation. The trusted
   adapter reports the coarse status, clears its cached token, retains a
   terminal endpoint marker until kernel cleanup, and never uses ordinary IPC
   for the request. A later attempt with the old generation returns `REVOKED`
   without entering the service; a new attach is denied until `UNBIND` reaps
   the quarantined descriptor.
5. `QUERY` exposes `FAULTED` to the kernel. Kernel teardown acknowledges and
   clears the privileged fault record before a new-token `INSTALL`; object and
   mapping references remain pinned until that acknowledgement. An omitted
   userspace cleanup call can leak the quarantined binding but cannot restart
   it or authorize object reuse.

The minimum prototype may unwind directly in hardware and let the kernel reap
the quarantined binding afterward. That is sufficient for at-most-once caller
recovery, but it is not yet equivalent to normal seL4 fault-endpoint delivery.
Claiming that equivalence requires a kernel-owned continuation that converts
the privileged record into the server TCB's ordinary fault protocol. Blocking,
timeouts, maskable interrupts, and asynchronous cancellation remain separate
state transitions rather than being relabeled synchronous faults.

The directed full-core model now injects illegal-instruction, instruction-page,
load-page, and store-page faults after a visible server-side counter update.
Each returns the caller exactly once with zero reply words and `SERVER_FAULT`;
the adapter tests forbid software fallback for the faulting request, and a
hardware retry reports `REVOKED` without changing the counter. Privileged
tests cover `FAULTED` query, token-checked fault-record access, and revoke.
They also revoke the faulted generation, reinstall the same pair under a fresh
token, reject the old token, and prove that the new generation has no readable
fault record. A fault racing revocation remains required. A seL4 fault-endpoint
test is additionally required before making any claim of ordinary seL4
fault-delivery equivalence.

The durable design makes the binding a kernel object/capability derived from
authority over the endpoint and both TCBs. Its finalization invokes synchronous
revocation;
the token is merely the runtime encoding of that authority, not an independent
application-created capability. Deleting an endpoint CPtr alone need not tear
down a deliberately retained binding cap, but deleting the last binding cap
must make the descriptor unusable before any referenced object is recycled.

For the single-slot experimental adapter, binding is requested by invoking a
send-capable endpoint cap while supplying a server-TCB cap. The current TCB is
the authorized caller. Userspace supplies the proposed fixed server entry and
initial SP/GP/TP plus the bounded word counts; the kernel derives both SATPs and
the endpoint badge, validates all addresses, generates the token, and asks
OpenSBI to install the descriptor. Userspace never supplies either context ID
or either SATP. The returned token is handed only to the trusted caller-side
adapter.

Both VSpace caps must still own their recorded entries in seL4's live ASID
table, and their physical root page tables must differ. A copied page-table cap
can retain mapped metadata after ASID deletion; that stale metadata is never
accepted as a way to revive a retired address space through the hardware path.

Resident context 1 is a clean hardware shadow of the server's VSpace, not a
TCB scheduled independently by seL4. The ordinary server TCB remains blocked
on the endpoint so a precisely `NOT_STARTED` call can use normal seL4 IPC on
context 0. Since version 1 is single-core and depth one, the shadow service and
the fallback server never execute concurrently. They use different transport
entries around the same handler and memory-backed private state.

The bind and unbind endpoint labels are reserved kernel control invocations.
The ordinary seL4 IPC fastpath must divert both labels to the invocation
decoder even when an operation such as zero-word `UNBIND` otherwise has a
fastpath-eligible message shape; it must never deliver either label to the
blocked fallback server.

## Privileged control operations

The private OpenSBI extension exposes three operations:

```text
INSTALL(versioned descriptor image) -> token or error (slot 0 in version 1)
REVOKE(slot, token)                  -> OK, STALE, or BUSY
QUERY(slot, token)                   -> OK, STALE, BUSY, or UNSUPPORTED
```

It uses the standard SBI vendor-extension ID derived from `mvendorid`; the
shared `bp_rpc_sbi_extension_id()` helper prevents the kernel and monitor from
disagreeing about that ID. `INSTALL` takes an aligned supervisor virtual
pointer in `a0`; OpenSBI copies it with fault-checked MPRV loads before it
validates or touches descriptor CSRs.

`INSTALL` consumes a fixed-layout image supplied by the seL4 kernel and copies
it before publication.  The monitor validates version, reserved bits, canonical
PCs, word counts, distinct caller/server identities, and supported fixed
contexts.  User mode cannot invoke descriptor control.  `QUERY` is diagnostic;
it is never used as the call eligibility decision.

`bp_rpc_descriptor_v1_valid()` is the shared fail-closed validator: it also
requires nonzero token, Sv39 SATPs, an aligned positive-canonical user entry
and stack, and zero reserved fields. OpenSBI still copies the image before
validation so supervisor memory cannot change underneath the check.

OpenSBI drives two M-mode-only custom CSRs defined in
`blackparrot_rpc_abi.h`. It writes one 64-bit value to `M_DATA`, then writes a
`STAGE(field, slot)` control word. After the final stage, `INSTALL` issues
`PREPARE(GPR_LINE0)`, `PREPARE(GPR_LINE1)`, and `PREPARE(CSR)`. These commands
zero all 31 writable server GPRs and construct an inactive U/Sv39 CSR bank from
the staged server SATP and entry PC. Any subsequent `STAGE` invalidates all
three preparation acknowledgements. `COMMIT` succeeds only after the complete
staged image and all preparation components are valid, then publishes the
descriptor in one architectural step.

`REVOKE` compares the token most recently written to `M_DATA` before clearing
`valid`, and refuses an active slot. Reading `M_CONTROL` returns the last
control status. Version 2 also defines
`READ_FAULT(CAUSE|PC|TVAL, slot)`: M mode first writes the token to `M_DATA`,
writes the read command, requires `OK`, and then reads the selected value from
`M_DATA`. A wrong token returns `STALE`; a live non-faulted slot or unknown
component returns `INVALID`. Revoke clears the record. This command is not yet
exported by the version-1 OpenSBI extension.

This data/control pair keeps the RTL boundary fixed while the
versioned memory image evolves, prevents a partially staged descriptor from
authorizing a call, and ensures that descriptor visibility cannot precede
construction of its protection domain.

The staged `CONFIG` value packs request words in bits 7:0, reply words in
15:8, caller context in 31:16, and server context in 47:32. Version 1 requires
bits 63:48 to be zero. Version 2 sets bit 48 for `FAULT_COMPLETION` and keeps
bits 63:49 zero. Version 1 accepts only slot 0, contexts 0/1, and word counts
up to four, but rejecting other values at `COMMIT` leaves room for later
tables.

The seL4 binding object owns the returned slot/token and the TCB/VSpace/endpoint
references that keep the descriptor valid.  Teardown order is: stop both TCBs,
revoke and observe `OK`, remove mappings or capabilities, then release the
binding.  The kernel must not destroy or reuse an object while revocation is
`BUSY`.

The experimental seL4 adapter implements these lifetime semantics for its
global one-slot record: endpoint and caller/server TCB finalization, TCB VSpace
replacement, ASID or ASID-pool deletion, and any page remap or page/page-table
unmap in a bound address space synchronously revoke before mutation completes. Explicit
unbind uses the same revocation path. This conservative implementation may
revoke for an unrelated mapping in either VSpace; multiple or selectively
pinned bindings should move state into a real kernel capability object rather
than extending the global record.

## Resident-server construction

The privileged installer constructs reserved logical context 1 before
publication; it does not execute untrusted server code as part of binding. Two
line writes clear the complete integer register image, and one CSR preparation
write clears machine/supervisor/debug state, disables interrupts, installs the
staged server SATP, selects U mode with floating point disabled, and records
the fixed entry PC. The call transition later installs only the declared
stack/global/thread pointers, badge, request registers, and metadata. This
removes the legacy bootstrap handoff and prevents a newly bound service from
inheriting observable registers or privileged state from an earlier occupant.

After commit, context 1 is owned by the binding and the ordinary scheduler must
not place another TCB there. Version 1 also defers maskable interrupts from an
accepted `pcall` until its matching `preturn`; the service is bounded,
prefaulted, and nonblocking. An interrupt already selected before the atomic
acceptance prevents the call from starting. Synchronous server faults remain
outside the version-1 fast path and must never cause an automatic retry.

## Required acceptance tests

1. Matched requests and four-word replies pass through software and hardware
   backends using the same handler.
2. Wrong or stale tokens report `REVOKED`; a matching live token with a wrong
   caller SATP/context, busy slot, or nonresident server reports
   `NOT_STARTED`. Every case proves that execution did not begin.
3. `AUTO` falls back exactly once for every non-started case; forced hardware
   never silently falls back.
4. Revocation prevents the next call, token reuse cannot revive an old binding,
   and revocation cannot discard a live continuation.
5. The server cannot forge a caller, return PC, or second return.
6. Logs identify the selected path, and counters distinguish rejected,
   committed, completed, and software-fallback calls.
7. Commit before complete preparation fails, staging after preparation clears
   the preparation state, and a prepared server begins with zero in every GPR
   not explicitly installed by the call transition.
8. A nonzero badge minted into the caller's endpoint cap is derived by the
   kernel and reaches the same handler context through ordinary endpoint IPC
   and protected hardware RPC; the caller cannot supply or alter it in the
   request payload.

Any server fault/cancellation path not yet capable of producing an explicit
`COMMITTED_FAILED` result is outside the hardware fast path and must be ruled
out by binding-time eligibility rather than retried after a fault.
