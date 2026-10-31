This document preserves the proposed seL4 integration so the project can return to it after the protected-library work. It defines a microkernel-neutral fast-path boundary, the seL4 adapter, required hardware generalization, and evidence needed for a defensible result; it is a plan, not a record of completed seL4 support.

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

- Add privileged descriptor installation, revocation, and generation checking.
- Bind one caller/server endpoint with a resident passive server.
- Implement hardware call/reply in the adapter and retain automatic software
  fallback for every ineligible case.
- Initially expose an experimental API if preserving transparent `seL4_Call`
  semantics would obscure which path executed.

Acceptance: the matched service passes through both backends; logs prove which
path ran; invalid, stale, and revoked descriptors fail closed; fallback neither
loses nor duplicates a request.

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
