This document defines the seL4 protected-RPC integration, its microkernel-neutral boundary, and the evidence required for a defensible acceleration claim. It also records which staged gates are accepted so future work can distinguish the completed one-pair prototype from optional generalization.

# seL4 hardware IPC plan

## Objective and decision

Use seL4 on RV64 as the first existing microkernel integration for protected
hardware RPC. Preserve the normal capability and IPC model while allowing a
small, kernel-authorized subset of synchronous `seL4_Call`/reply traffic to use
BlackParrot `pcall`/`preturn` without entering the kernel on every invocation.

The intended claim is:

> An existing capability microkernel can retain its IPC API and security policy
> while replacing eligible synchronous IPC with an address-space transition
> close to function-call cost.

seL4 is the preferred first target because it supports RV64 and QEMU/Spike, has
capability-addressed synchronous endpoints, transfers short messages in
registers, creates protected reply authority, publishes an optimized IPC fast
path, and provides established IPC tests and benchmarks. A QEMU target lets the
software integration begin without FPGA access. Fiasco.OC/L4Re remains a
possible second adapter; a new custom microkernel is not the initial target.

## Current disposition

Stages 0--5 are accepted for the scoped single-core, one-caller/one-resident-
server prototype. The public interface and ordinary seL4 backend precede and
remain independent of the BlackParrot backend (RL-060); descriptor transport,
kernel authorization, revocation, and exactly-once fallback pass simulation and
physical FPGA execution (RL-062--RL-063, RL-069); and the matched isolated musl
workload plus component timing show a 1.57x warm speedup over ordinary seL4 IPC
while removing 77.9% of its transport premium over direct execution (RL-064--
RL-069). Version 2 additionally returns precise synchronous server faults
without replay and passes end to end in a fresh full-system model and on the
PYNQ-Z2 (RL-071).

Stage 6 is future generalization, not part of that accepted claim. Multiple
clients or bindings, queues, nested calls, blocking/asynchronous cancellation,
MCS donation, SMP migration, and resumable seL4 fault-endpoint delivery remain
unsupported and must continue to select ordinary IPC or receive a separately
specified atomic protocol before admission to the hardware path.

This plan is based on the protected-RPC library checkpoint `844fcb8c`. That
checkpoint demonstrates a fixed protected service entry, separate Sv39 roots,
private-state isolation, four input registers, one result register, protected
return, and a shared page mapped at different caller/server virtual addresses.
It also establishes the first pointer convention: shared buffer references are
bounds-checked offsets, not raw virtual addresses.

## Scope

The first integration supports one pre-bound caller/server pair and one
synchronous request at a time. It is deliberately narrower than general seL4
IPC:

- the server is resident, initialized, and waiting at a fixed entry;
- request and reply metadata fit in the hardware message registers;
- shared regions were authorized, pinned, and prefaulted before the call;
- the service does not block, fault, transfer capabilities, or invoke the
  scheduler on the hardware path;
- the version-1 service is integer-only; `mstatus.FS` remains off and any
  service needing floating point selects ordinary IPC;
- the kernel can revoke the binding and always retains a software IPC fallback.

Asynchronous notifications, arbitrary endpoint queues, multiple waiting
callers, migration, nested calls, capability transfer, and scheduling-context
donation are follow-on work. Their absence must be visible to the adapter and
must select the ordinary kernel path rather than silently changing semantics.

## Layered design

Keep the hardware protocol below a microkernel-neutral protected-call layer:

```text
application or isolated service
        |
seL4_Call / reply-compatible user API
        |
seL4 endpoint adapter and fast-path eligibility check
        |                         |
hardware backend                 ordinary seL4 syscall
pcall -> service -> preturn       existing kernel IPC
```

Applications must not know CSR numbers, logical hardware-context numbers, the
server SATP, or its entry PC. The kernel installs and revokes those details.
The user-visible identity remains an endpoint capability or an adapter-owned
token derived from one.

The generic layer should expose concepts rather than BlackParrot instructions:

```c
ipc_result_t ipc_call(ipc_endpoint_t endpoint,
                      const ipc_message_t *request,
                      ipc_message_t *reply);

void ipc_reply_wait(const ipc_message_t *reply,
                    ipc_message_t *next_request);
```

An initial implementation may add an explicit experimental
`seL4_HardwareCall` entry point. The eventual transparent version can preserve
`seL4_Call` source compatibility by selecting a backend in `libsel4`, provided
that selection cannot forge or widen the endpoint's kernel-installed authority.

## Semantic mapping

| seL4 concept | Hardware representation | Required invariant |
| --- | --- | --- |
| Endpoint capability | Kernel-installed descriptor identifier and generation | Userspace cannot choose the target context, address space, or entry PC |
| Fast message registers | Atomic `a0`--`a3` transfer initially | The descriptor limits which state crosses the boundary |
| `seL4_Call` | Authorized `pcall` | Call either completes with matching reply or takes the ordinary kernel path |
| Reply capability/object | Hardware-held protected continuation | Only the invoked service can consume it; it is single-use and revocable |
| Reply message | Atomic result transfer on `preturn` | The service cannot redirect execution to an arbitrary caller PC |
| IPC buffer/shared memory | Authorized shared region plus offset and length | No raw pointer is interpreted in another address space |
| Badge/label | Descriptor metadata or a message word | The service receives only a kernel-authorized caller identity |

Persistent server objects use opaque handles containing an index plus a
generation or cookie. Deep pointer graphs must be serialized or represented in
an explicitly shared offset-based arena. Mutable buffers carry direction and
permission information; validation occurs again in the server, not only in the
client stub.

## Fast-path eligibility and fallback

The adapter may issue `pcall` only when all of the following are true:

1. The endpoint has a live hardware descriptor with the expected generation.
2. The current caller is authorized by that descriptor.
3. The server is resident, initialized, and dedicated to this fast endpoint.
4. The request fits the supported message-register and shared-region contract.
5. No capability transfer, endpoint queue operation, or kernel policy decision
   is required.
6. Running the server immediately is consistent with seL4 priority and
   scheduling rules.
7. The call depth and reply state fit the hardware continuation capacity.

If any condition fails, the same logical operation uses ordinary seL4 IPC. A
fallback must not duplicate a request that may already have executed. The
eligibility decision must therefore occur before committing the protected call,
or hardware must report a precise non-executed failure.

The first prototype should use baseline seL4 scheduling rather than MCS. MCS
adds scheduling-context donation, budgets, and explicit reply objects; it is a
valuable later target after the simpler call/reply contract is correct.

## Kernel and hardware responsibilities

The seL4 kernel adapter is responsible for:

- authorizing an endpoint, caller, and server tuple;
- parking or reserving the server so the normal scheduler does not concurrently
  own its hardware context;
- installing the server address-space identity, fixed entry, stack, and allowed
  message/shared-memory resources;
- pinning and prefaulting every mapping used by the non-faulting fast service;
- revoking the descriptor before either process, mapping, or endpoint is
  destroyed or reused;
- handling faults, cancellation, timeout, preemption, and nonresident service
  cases through a defined slow path;
- preserving seL4 badge, priority, accounting, and reply semantics.

The current one-capability prototype will need generalization before this is a
credible kernel facility. A privileged descriptor should eventually include at
least:

```text
valid and generation
authorized caller identity
target logical/resident context
target address-space identity and fixed entry
request/reply register masks
shared-region capability and permissions
protected continuation state
scheduling/fast-path eligibility state
```

Open questions requiring explicit design are descriptor lookup cost, atomic
revocation, server faults and interrupts, nested continuations, multiple
clients, nonresident targets, SMP migration, and what accounting event the
kernel observes when userspace bypasses a syscall.

## Implementation stages and acceptance gates

### Stage 0 — Preserve the mechanism baseline

- Keep `mt_protected_rpc_library_test` passing in full-core simulation.
- Retain separate Sv39 address spaces, different virtual mappings of one shared
  page, invalid-range rejection, fixed entry, private-state isolation, and
  protected return.
- Record current primitive timing separately from later seL4 end-to-end timing.

Acceptance: the existing library test and protected hardware regression pass;
no seL4 claim is made at this stage.

### Stage 1 — Unmodified seL4 reference

- Build and run `sel4test` for `qemu-riscv-virt` RV64.
- Implement a minimal client/server using ordinary `seL4_Call` and
  `seL4_ReplyRecv` with a buffer-oriented service.
- Run the existing seL4 IPC benchmark and retain exact configuration and logs.
- Identify the RISC-V syscall wrapper, kernel fast-path conditions, endpoint and
  reply-object code, register ABI, and scheduler handoff points.

Acceptance: an unmodified, reproducible QEMU result and a written mapping from
the seL4 call/reply lifecycle to the generic protected-call interface.

### Stage 2 — Backend-neutral software adapter

- Define endpoint, message-register, shared-region, handle, and reply types
  without BlackParrot CSR details in the public API.
- Keep authenticated per-call context opaque; expose identity and shared
  regions only through narrow accessors rather than a runtime-private pointer.
- Implement an ordinary seL4 backend first.
- Port the dummy library or another narrow buffer service to that API.
- Add forced-software and forced-hardware selection controls so matched
  workloads cannot accidentally use different service bodies.

Acceptance: the service runs through ordinary seL4 IPC, pointer/handle tests
fail closed, and the backend selection is observable in test output.

### Stage 3 — BlackParrot seL4 bring-up

- Boot minimal RV64 seL4 in BlackParrot full-core simulation before modifying
  IPC.
- Add only the required platform support: boot protocol, physical-memory map,
  console, timer, and interrupt controller.
- Run a minimal `sel4test` subset and the ordinary IPC client/server baseline.

Acceptance: ordinary seL4 IPC passes on the same simulated core that will run
the hardware path. QEMU numbers are development evidence, not the hardware
comparison.

### Stage 4 — Kernel-authorized hardware endpoint

The concrete version-1 descriptor, atomic outcome, privileged control, and
revocation contract is fixed in
[`sel4/BLACKPARROT_RPC_ABI.md`](sel4/BLACKPARROT_RPC_ABI.md).

- Add privileged descriptor installation, revocation, and generation checking.
- Bind one caller/server endpoint with a resident passive server.
- Implement hardware call/reply in the adapter and retain automatic software
  fallback for every ineligible case.
- Initially expose an experimental API if preserving transparent `seL4_Call`
  semantics would obscure which path executed.

Acceptance: the matched service passes through both backends; logs prove which
path ran; invalid, stale, and revoked descriptors fail closed; fallback neither
loses nor duplicates a request.

Current checkpoint (2026-11-02): the lifecycle-qualified routed PYNQ-Z2 image
passes region isolation, mapping-triggered revocation, atomic stale-token
rejection, rebind, nonzero badge authentication, and the complete three-test
suite with clean host termination. The exact full-system simulator independently
reaches the lifecycle marker before its four-hour timing-loop timeout; physical
evidence is the accepted end-to-end gate. See RL-069 and
`sel4/results/sel4test-rpc-lifecycle-fpga.log`.

#### Initial kernel binding shape

The first implementation uses an experimental endpoint invocation rather than
a userspace SBI call or an application-created token. `BIND` invokes the
ordinary endpoint capability and supplies one extra server-TCB capability.
The invoking TCB is the sole hardware caller. Its message provides the fixed
server entry, stack, global pointer, thread pointer, and bounded request/reply
word counts. The kernel must:

1. require a send-capable endpoint cap and authority over the server TCB;
2. require a fresh, single-core, non-MCS binding with distinct mapped caller
   and server VSpaces;
3. derive both SATPs and the endpoint badge itself, validate the fixed user
   addresses, and generate a nonzero generation token;
4. install the complete descriptor through OpenSBI and return only the opaque
   token to the invoking TCB; and
5. retain a kernel binding record until an authorized `UNBIND` completes
   synchronous OpenSBI revocation.

Logical context 1 is a hardware execution shadow of the server protection
domain, not the normal scheduler's copy of the server TCB. The ordinary server
TCB remains blocked in `ReplyRecv` and may run on context 0 only after a
`NOT_STARTED` hardware attempt safely falls back. On the single-core prototype,
the hardware service and fallback server therefore cannot execute
concurrently. Both entries call the same service handler and share its private
memory; only their transport wrappers differ.

The binding record must be revoked before the endpoint, either TCB, either
VSpace root, or any pinned service mapping is destroyed, replaced, or unmapped.
Final-cap deletion and TCB/VSpace reconfiguration paths therefore need hooks;
an explicit `UNBIND` alone is not a sufficient lifetime guarantee. Revocation
is expected to be non-busy while the kernel is executing because version 1
defers interrupts during an accepted protected call. A surprising `BUSY`
result is a kernel invariant failure, not permission to recycle an object.

After an implicit lifetime revocation, the first stale-token hardware attempt
returns `REVOKED` without executing the service. The caller runtime must then
drop that local token so the same logical endpoint can acquire a fresh kernel
generation; a transient `NOT_STARTED` attempt does not drop it. The focused
test maps an unrelated page while bound, requires stale-token rejection,
rebinds, and requires a new hardware call to complete.

This shape intentionally avoids a new public kernel object in the one-slot
prototype. A generalized implementation should promote the global binding
record into a first-class capability object before supporting multiple pairs,
SMP, or MCS scheduling contexts.

### Stage 5 — Evaluation

Compare on the same BlackParrot configuration:

- in-process function call;
- protected hardware call/reply;
- unmodified seL4 fast IPC;
- shared-memory plus notification when applicable;
- a real isolated library workload using identical service logic.

Report cold and warm median, distribution/tails, call and reply components,
cycles spent in useful service work, throughput, code/data-cache conditions,
and end-to-end application impact. Do not compare the current 43-cycle
simulator primitive directly with published seL4 hardware numbers as if they
were measured on the same processor.

Acceptance: correctness and security gates pass before performance is reported;
the software and hardware IPC paths use matched inputs, outputs, mappings, and
timing boundaries.

Current checkpoint (2026-11-01): one shared-page musl service passes QEMU and
the PYNQ-Z2. The latest matched warm medians are 2,786 cycles in-process, 3,150
through hardware RPC, 5,189 through forced ordinary seL4 IPC, and 10,226
through a shared read/write mailbox with separate request/reply notifications.
L1D-cold/L2-warm medians are 3,700/4,335/9,937/15,042; L1D+L2-cold medians are
4,163/4,867/9,431/14,472 in the same order. Hardware RPC is 1.65x faster than
ordinary IPC and 3.25x faster than the notification baseline at warm median.
The notification baseline deliberately has weaker semantics than the protected
paths, yet remains slower because it splits each direction into Signal/Wait
operations instead of using seL4's endpoint Call/ReplyRecv handoff. The
eight-call AUTO fallback remains separate because its failed hardware probe is
intentional extra work.

Component decomposition is accepted on the pinned `ca4a6c...31040` FPGA
bitstream. The current common-dispatch image has warm median pre/service/post
costs of 13/2,884/8 cycles in-process, 342/2,874/171 through hardware RPC,
1,412/2,977/1,304 through ordinary seL4 IPC, and 3,848/2,954/3,729 through
notifications. Hardware reduces ordinary IPC's transport premium over direct
execution by 81.7%; its complete 3,387-cycle median is 1.17x direct, 1.68x
faster than ordinary IPC, and 3.11x faster than notifications. See RL-067 and
`sel4/results/sel4test-rpc-common-dispatch-fpga.log`. RL-066 and
`sel4/results/sel4test-rpc-components-fpga.log` retain the historical
pre-dispatch 3,157-cycle hardware result rather than representing the current
public interface.

The subsequent trusted-runtime checkpoint physically verifies that the
application no longer owns BlackParrot request decoding, installed-register
access, or protected return. With nonzero caller badge 24090 authenticated on
both transports, warm medians are 2,925/3,448/5,479/10,612 cycles for
direct/hardware/software/notification. Hardware remains 1.59x faster than
ordinary IPC and removes 78.7% of its transport premium over the direct
wrapper. See RL-068 and
`sel4/results/sel4test-rpc-trusted-runtime-fpga.log`.

The lifecycle-qualified successor preserves that result while closing the
revocation outcome gap. Its warm medians are 2,934/3,461/5,440/10,597 cycles
for direct/hardware/software/notification; hardware is 1.57x faster than
ordinary IPC and removes 77.9% of its transport premium over direct. L1D-cold
hardware/ordinary medians are 4,821/10,072 and hierarchy-cold medians are
5,421/9,809. See RL-069 and
`sel4/results/sel4test-rpc-lifecycle-fpga.log`.

The first image trapped because the standalone server did not include seL4's
generated platform configuration and emitted `rdcycle`; clean descriptor
construction deliberately clears `scounteren`, and version 1 has no
server-fault continuation. The service now includes the configuration
explicitly, and packaging rejects any BlackParrot server containing `rdcycle`
or fewer than two `0xCC0` reads. Deployment also shares one board lock across
staging, overlay load, and launch and pins the bitstream hash again at launch;
this caught an external replacement before target execution.

### Stage 6 — Generalization

Only after the one-pair result, evaluate multiple clients, endpoint queues,
nested calls, interrupts, nonresident servers, MCS scheduling-context donation,
and additional microkernel adapters. Each feature needs an explicit fallback
and revocation story before it joins the fast-path contract.

## Security and failure tests

The integration is incomplete until tests attempt to:

- call an endpoint without authority or with a stale generation;
- choose a server PC, SATP, context, or reply PC from userspace;
- forge, replay, or consume another call's continuation;
- pass an overflowing or out-of-range shared-buffer reference;
- read or write caller/server private mappings from the other domain;
- use a descriptor after endpoint, process, or mapping teardown;
- fault, block, time out, or receive an interrupt inside the service;
- race revocation with invocation;
- force an ineligible scheduling condition and verify one software execution,
  not a dropped or duplicated operation.

Current coverage (2026-11-02): the routed FPGA closes stale generation,
mapping-triggered revoke/rebind, region identity/permission, runtime-state, and
nonzero-badge cases. Host and directed tests cover malformed buffer references,
descriptor fields, continuation metadata, precise `NOT_STARTED`/`REVOKED`
fallback counts, and no fallback after a committed failure. RL-070 records the
version-1 negative boundary: a post-entry illegal instruction cannot resume the
caller and must never fall back through software.

RL-071 closes that synchronous-fault gap with the opt-in version-2 contract in
`sel4/BLACKPARROT_RPC_ABI.md`. Directed full-core tests cover illegal-instruction
and instruction/load/store page faults (causes 2/12/13/15), exact PC/`tval`, one
visible pre-fault effect, terminal `COMMITTED_FAILED`, zero reply, rejected
retry, token-authenticated fault-record access, revoke, and clean fresh-token
reinstall. OpenSBI installs the version-2 descriptor and exposes the fixed
24-byte record; the seL4 kernel consumes it while reaping the quarantined
binding. The exact fault-only seL4 lifecycle passes independently in a fresh
full-system model and on the timing-clean PYNQ-Z2 route. Artifact identities and
strict-checker results are retained in `logs/sel4-v2-fault-20261102/`.

The remaining generalization gaps are a true fault/revoke race, ordinary seL4
fault-endpoint equivalence, endpoint/TCB/VSpace/ASID destruction variants beyond
the accepted page-map revoke, and block, timeout, cancellation, or interrupt
after hardware acceptance. They are not silently supported by version 2:
version 1 remains the prefaulted/nonblocking contract, version 2 adds only
precise synchronous-fault unwind, and Stage 6 must define a new atomic state
transition before admitting any asynchronous case.

## Resume checklist

When returning to this direction:

1. Start from this plan and protected-RPC checkpoint `844fcb8c` or its accepted
   descendant; do not reconstruct the contract from chat history.
2. Re-run the Stage 0 regressions and confirm the active BlackParrot revision.
3. Begin with unmodified `qemu-riscv-virt` seL4 and archive its exact manifest,
   configuration, and IPC baseline.
4. Keep the seL4 platform port, generic adapter, hardware changes, and benchmark
   interpretation in separate reviewable commits.
5. Update `RESEARCH_LEDGER.md` only when a measured result or accepted design
   decision changes a scoped claim; keep routine porting chronology in
   `WORK_LOG.md`.

## Upstream references

- [seL4 IPC tutorial](https://docs.sel4.systems/Tutorials/ipc)
- [seL4 QEMU RISC-V virtual platform](https://docs.sel4.systems/Hardware/qemu-riscv-virt.html)
- [seL4 supported platforms](https://docs.sel4.systems/Hardware/)
- [seL4 performance results](https://sel4.systems/performance.html)
- [seL4 manual](https://sel4.systems/Info/Docs/seL4-manual-latest.pdf)
