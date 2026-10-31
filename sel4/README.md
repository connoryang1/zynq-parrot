This directory contains the reproducible seL4/RV64 baseline used to develop the protected IPC backend described in [`SEL4_HARDWARE_IPC_PLAN.md`](../SEL4_HARDWARE_IPC_PLAN.md). It keeps upstream seL4 sources external and pinned, while versioning only the project-specific test and small materialization helper here.

# seL4 IPC acceleration workspace

## Pinned upstream baseline

- `sel4test-manifest`: `ae4780bcdc221959949a0ec0aeb559337ea503d0`
- seL4 kernel: `15ec7bf82864e0505dc682051c0d688a946f5ece`
- sel4test: `f27e4f4cdd020ef9b37f15ded76a3b38477761f0`
- Platform: `qemu-riscv-virt`, `riscv64`, non-MCS
- Verified simulator: xPack QEMU RISC-V 9.2.4-1

The unmodified baseline built with the existing ZynqParrot
`riscv64-unknown-elf` toolchain and completed 116 enabled tests with:

```text
Test suite passed. 116 tests passed. 51 tests disabled.
All is well in the universe
```

This is functional QEMU evidence, not BlackParrot timing evidence.

After adding the project-specific test, the full regression completed with
117 passing and 51 disabled tests. Its retained source transcript had SHA-256
`c546bf3686dfd355565a12980f8e7c525cab019dfd9e08dedb65240bc4768926`;
the smaller targeted transcript is retained as
[`results/sel4test-ipc-baseline-qemu.log`](results/sel4test-ipc-baseline-qemu.log).

## Project-specific test

`sel4_ipc_baseline.c` adds one matched synchronous IPC workload to sel4test. A
client invokes a server cloned into a distinct CSpace and VSpace, transfers four
message registers, receives a two-word reply, and verifies that server-private
state is not shared with the caller. The measured loop uses ordinary
`seL4_Call` and `seL4_ReplyRecv`; it is the software backend that the future
`pcall`/`preturn` backend must match.

Materialize the test into a pinned sel4test checkout:

```sh
scripts/sel4/materialize_sel4test_ipc_baseline.sh /path/to/sel4test-checkout
```

Then configure the checkout normally with the test filter
`^SEL4IPCRPC0001$`. The helper only creates a source symlink; it does not patch
or commit upstream repositories.

The test passed 256 measured calls after eight warmups. Its reported QEMU
value was 592,524 host/emulator ticks per call. This number is retained only to
make the run auditable: it is neither a target cycle count nor comparable to a
BlackParrot result.

## Official IPC benchmark

The upstream sel4bench reference uses these pins:

- `sel4bench-manifest`: `c7db39cd58202dc207d292c54f68d6dcafe0c5bc`
- seL4 kernel: `15ec7bf82864e0505dc682051c0d688a946f5ece`
- sel4bench: `18f9d5f079bc23551eccbdc2202cae95c72c69d7`

Current sel4bench implements the RISC-V cycle counter but omits RISC-V from
the CMake predicate that enables its benchmark options. As a result, disabled
applications retain an `ON` default and are accidentally packaged. Run
`scripts/sel4/configure_sel4bench_ipc.sh` to apply the pinned one-line
workaround and configure only IPC with the release fast path. The script also
uses sel4bench's `AllowUnstableOverhead` setting because QEMU host scheduling
does not satisfy its hardware-counter stability check.

The official hot-cache benchmark completed all nine IPC cases and printed
`All is well in the universe.` The normalized transcript is
[`results/sel4bench-ipc-qemu.log`](results/sel4bench-ipc-qemu.log). For example,
its separate-address-space zero-word medians were 132,865.5 QEMU ticks for the
Call half and 136,406.5 for the ReplyRecv half. The wide tails and unstable
counter overhead make these functional/structural evidence only; they must not
be presented as seL4 or BlackParrot hardware latency.

## Confirmed call/reply path

The current RV64 software path is:

1. `libsel4` loads message registers `a2`--`a5`, the endpoint CPtr, message
   info, and `seL4_SysCall`, then executes `ecall`.
2. `kernel/src/arch/riscv/traps.S` recognizes Call or ReplyRecv and jumps to
   the corresponding C fast path.
3. `fastpath_call` checks message length and extra caps, endpoint authority,
   a waiting receiver, vspace/ASID validity, scheduling priority/domain,
   grant/reply authority, and affinity before its point of no return.
4. The kernel creates reply authority, transfers up to four message registers,
   switches vspace/thread state, and restores the receiver.
5. `fastpath_reply_recv` validates and consumes the reply authority, queues the
   server to receive again, transfers the reply registers, and restores the
   caller.

The first hardware prototype may cache a kernel-authorized instance of these
checks, but must fall back before execution whenever their conditions do not
hold. It must never execute a request and then retry it through software.

## Protected-RPC interface boundary

[`include/protected_rpc.h`](include/protected_rpc.h) is the public,
microkernel-neutral interface that the ordinary seL4 and future hardware
backends must implement. Its initial contract is deliberately small:

- a synchronous call carries at most four 64-bit request and reply words;
- endpoints and shared regions are opaque kernel-issued values, never context
  numbers, page-table roots, PCs, or pointers;
- a shared buffer is a region token plus an overflow-safe offset and length;
- region permissions and direction are fixed at binding time rather than
  accepted from caller-controlled message bits;
- services resolve buffer references through the runtime in their own address
  space and request the access their operation needs; they never cast the
  opaque token or a caller virtual address;
- the same service handler is hosted by an ordinary `ReplyRecv` loop or by a
  hardware entry/return stub, so benchmarked service logic stays identical;
- forced-software and forced-hardware modes make the selected path observable.

The internal backend boundary in
[`include/protected_rpc_backend.h`](include/protected_rpc_backend.h) makes the
exactly-once rule explicit. A hardware attempt atomically returns one of four
states: completed, safe to fall back because execution definitely never
started, rejected without execution, or failed after its commit point. Only
the safe-to-fallback state may invoke the software backend. A separate
"eligible?" probe is intentionally excluded because endpoint state,
revocation, or scheduling eligibility could change between a probe and a call.

The current BlackParrot primitive can carry four request words but only one
reply word and one fixed descriptor. Supporting the complete interface
therefore requires hardware generalization; the adapter must reject or use
ordinary seL4 IPC for unsupported reply shapes rather than truncate them.
