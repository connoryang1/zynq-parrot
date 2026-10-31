This document fixes the first seL4/BlackParrot hardware boundary before RTL or
kernel integration.  It refines Stage 4 of
[`SEL4_HARDWARE_IPC_PLAN.md`](../SEL4_HARDWARE_IPC_PLAN.md); the public API in
[`include/protected_rpc.h`](include/protected_rpc.h) remains independent of
BlackParrot CSRs and hardware-context numbers.

# BlackParrot protected-RPC kernel ABI

## First implementation scope

Version 1 has one descriptor slot, one caller, one resident passive server,
four 64-bit request words, and up to four 64-bit reply words.  The service must
be prefaulted and nonblocking.  General endpoint queues, capability transfer,
multiple callers, nested calls, migration, and server faults use ordinary seL4
IPC until separately implemented.

The application continues to name an seL4 endpoint.  A kernel-authorized
runtime binding privately associates that endpoint with an opaque hardware
token; applications never supply a context ID, SATP, entry PC, or stack.

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
[`include/blackparrot_rpc_abi.h`](include/blackparrot_rpc_abi.h).  It also
supplies the initial server stack/global/thread pointers and caller badge; the
hardware installs the badge in a fixed non-message register for the runtime.

The server context's general-register image, including its private stack, is
prepared by the privileged installer.  A token match alone is insufficient:
`pcall` also compares the current SATP and logical caller context.  This keeps a
leaked or guessed token from becoming ambient authority when seL4 schedules a
different process in the same physical hardware slot.

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
| `REVOKED` | no | report stale binding or refresh, never treat as success |
| `COMMITTED_FAILED` | possibly | report failure; never retry |

An invalid, busy, nonresident, wrong-SATP, or otherwise ineligible call returns
a precise non-started outcome from the same instruction.  A separate
"eligible?" CSR is forbidden because revocation or scheduling state could
change between the query and the call.

On acceptance, hardware saves the caller continuation outside both untrusted
contexts, transfers the requested subset of `a0`--`a3` and the validated
request-length metadata in `a5`, installs the fixed server PC/address space,
and marks the descriptor active. The server returns
with CSR `0x809`; `a0`--`a3` carry reply words and `a5` carries reply metadata:
an 8-bit length, an 8-bit service status, and zero reserved bits. Hardware
transfers the configured reply words and metadata, writes
`COMPLETED` to caller `a4`, consumes the continuation exactly once, and resumes
only the recorded caller. The server cannot select a return PC or caller.

The existing prototype's silent rejection and one-word reply are therefore
not the seL4 ABI.  They remain mechanism evidence until this outcome and reply
contract is implemented and tested.

The binding itself is a kernel object/capability derived from authority over
the endpoint and both TCBs. Its finalization invokes synchronous revocation;
the token is merely the runtime encoding of that authority, not an independent
application-created capability. Deleting an endpoint CPtr alone need not tear
down a deliberately retained binding cap, but deleting the last binding cap
must make the descriptor unusable before any referenced object is recycled.

## Privileged control operations

The private OpenSBI extension exposes three operations:

```text
INSTALL(versioned descriptor image) -> slot/token or error
REVOKE(slot, token)                  -> OK, STALE, or BUSY
QUERY(slot, token)                   -> LIVE, STALE, ACTIVE, or UNSUPPORTED
```

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
`STAGE(field, slot)` control word; `COMMIT` publishes all staged fields in one
architectural step. `REVOKE` compares the token most recently written to
`M_DATA` before clearing `valid`, and refuses an active slot. Reading
`M_CONTROL` returns the last control status. This data/control pair keeps the
RTL boundary fixed while the versioned memory image evolves, and prevents a
partially staged descriptor from authorizing a call.

The staged `CONFIG` value packs request words in bits 7:0, reply words in
15:8, caller context in 31:16, and server context in 47:32; bits 63:48 are
reserved zero. Version 1 accepts only slot 0, contexts 0/1, and word counts up
to four, but rejecting other values at `COMMIT` leaves room for later tables.

The seL4 binding object owns the returned slot/token and the TCB/VSpace/endpoint
references that keep the descriptor valid.  Teardown order is: stop both TCBs,
revoke and observe `OK`, remove mappings or capabilities, then release the
binding.  The kernel must not destroy or reuse an object while revocation is
`BUSY`.

## Required acceptance tests

1. Matched requests and four-word replies pass through software and hardware
   backends using the same handler.
2. Wrong token, stale token, wrong caller SATP, wrong caller context, busy slot,
   and nonresident server all report that execution did not begin.
3. `AUTO` falls back exactly once for every non-started case; forced hardware
   never silently falls back.
4. Revocation prevents the next call, token reuse cannot revive an old binding,
   and revocation cannot discard a live continuation.
5. The server cannot forge a caller, return PC, or second return.
6. Logs identify the selected path, and counters distinguish rejected,
   committed, completed, and software-fallback calls.

Any server fault/cancellation path not yet capable of producing an explicit
`COMMITTED_FAILED` result is outside the hardware fast path and must be ruled
out by binding-time eligibility rather than retried after a fault.
