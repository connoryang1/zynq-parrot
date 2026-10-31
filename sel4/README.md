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

With the ordinary protected-RPC adapter included, the full regression
completed with 118 passing and 51 disabled tests. The full transcript SHA-256
is `5ba5ac5ebf0182f2bbf2dbc53dde8627620cf9a8142a90c3e74a6a046dbec6b6`.

## Project-specific test

`sel4_ipc_baseline.c` adds one matched synchronous IPC workload to sel4test. A
client invokes a server cloned into a distinct CSpace and VSpace, transfers four
message registers, receives a two-word reply, and verifies that server-private
state is not shared with the caller. The measured loop uses ordinary
`seL4_Call` and `seL4_ReplyRecv`; it is the software backend that the future
`pcall`/`preturn` backend must match.

`sel4_rpc_adapter_test.c` exercises the same lifecycle through the public
protected-RPC API. It maps one page into the separate server VSpace, resolves
region/offset/length references using the server's local address, mutates the
shared words, and verifies private state remains isolated. It also proves that
an overflowing range and unknown region fail closed, forced hardware reports
`UNSUPPORTED` without contacting the server, and forced software reports the
software path.

Materialize the test into a pinned sel4test checkout:

```sh
scripts/sel4/materialize_sel4test_ipc_baseline.sh /path/to/sel4test-checkout
```

Then configure the checkout normally with the test filter
`^SEL4IPCRPC0001$`. The helper only creates a source symlink; it does not patch
or commit upstream repositories.

The raw reference test passed 256 measured calls after eight warmups. Its
reported QEMU value was 592,524 host/emulator ticks per call. This number is
retained only to make the run auditable: it is neither a target cycle count nor
comparable to a BlackParrot result.

The adapter test passed the same 256-call shape at 585,897 QEMU ticks per call;
its normalized transcript is
[`results/sel4test-rpc-adapter-qemu.log`](results/sel4test-rpc-adapter-qemu.log).
The difference is dominated by QEMU noise plus adapter validation and must not
be interpreted as a hardware overhead measurement.

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

## Ordinary seL4 backend

`src/protected_rpc.c` implements route selection and the exactly-once fallback
state machine. `src/protected_rpc_sel4.c` implements the initial software
backend with ordinary `seL4_Call`, `seL4_Recv`, and `seL4_ReplyRecv`; seL4
message labels carry the transport/service status, while up to four fast
message registers carry the payload. `src/protected_rpc_hardware_stub.c`
currently reports a precise non-executed result, allowing `AUTO` to fall back
once and forced-hardware tests to remain observable.

The server runtime owns ReplyRecv authority and invokes an application handler
with a caller badge and registered local-region table. The handler never sees
the seL4 reply capability or future hardware continuation. A host-side mock
test covers hardware completion, safe fallback, rejection, committed failure,
and both forced routes:

```sh
scripts/sel4/test_protected_rpc_interface.sh
```

`src/protected_rpc_hardware_blackparrot.c` is the version-1 hardware backend
behind the same boundary. The trusted runtime associates the ordinary endpoint
with the opaque token returned by a kernel binding operation; one atomic CSR
attempt then maps completed, non-started, revoked, and committed-failure
outcomes into the existing fallback state machine. Its host-injected
architecture test covers reply decoding and proves that only a definitely
non-started attempt can reach the software backend. The sel4test build still
selects the hardware stub until the Stage 4 kernel binding and RTL descriptor
are present.

## BlackParrot platform bring-up

Stage 3 uses the same pinned sel4test tree and adds only the platform boundary:
one RV64 hart, 64 MiB at `0x80000000`, a 2 MiB OpenSBI reservation, the
BlackParrot CLINT at `0x300000`, an 8 MHz timebase, SBI console calls, and the
dummy PLIC used by seL4's Spike platform. The platform sources live under
[`platform/blackparrot`](platform/blackparrot); materialize and configure them
with:

```sh
scripts/sel4/configure_blackparrot_rpc.sh \
  /path/to/sel4test-checkout /path/to/build
ninja -C /path/to/build elfloader
```

The configure helper applies one pinned validation-only sel4test patch. It
links only the protected-RPC test into the child image, reduces the generic
libc heap from 1 MiB to 64 KiB, and keeps kernel printing enabled in the
otherwise optimized build. This removes unrelated full-suite load/zero work
from the cycle-accurate boot while preserving the same RPC test and makes its
exact pass marker observable. The RPC-only driver also reserves one 16 MiB
untyped object and delegates one 16 MiB object directly, instead of exhaustively
probing every object size. That bounded pool is ample for the single test and
avoids spending model hours on intentional allocation failures.

The same reduced configuration passes under QEMU before the slow full-core
run; its concise transcript is retained as
[`results/sel4test-rpc-only-qemu.log`](results/sel4test-rpc-only-qemu.log).

The host must provide the pinned checkout's Python packages plus CMake, Ninja,
and `riscv64-unknown-elf-*` on `PATH`. Package the resulting elfloader behind
the qualified BlackParrot OpenSBI platform with:

```sh
SEL4_CROSS_PREFIX=/path/to/riscv64-unknown-elf- \
OPENSBI_CROSS_PREFIX=/path/to/riscv64-unknown-linux-gnu- \
scripts/sel4/package_blackparrot_rpc_nbf.sh \
  /path/to/build /path/to/opensbi-repo /path/to/work sel4-rpc.nbf
```

The packager pins OpenSBI commit `7830e987856eb1319c82664702892b6d50a93e7a`,
disables the unrelated I-cache replay table, embeds the exact seL4 DTB, and
selects the routed 8 MHz timer. It places the payload at the elfloader's linked
entry instead of OpenSBI's default address, avoiding an otherwise redundant
self-relocation in the slow core model. It also defaults to OpenSBI's
no-boot-prints option because character-at-a-time firmware diagnostics consume
several model minutes; set `OPENSBI_FW_OPTIONS=0` when those diagnostics are
needed. Its output is deterministic for fixed inputs.

The simulation NBF loader stages guest DRAM again after configuration writes
because the low BlackParrot unfreeze address aliases guest DRAM through the
model's 32-bit HP0 transform. Physical loading is unchanged. The ordinary RPC
test's exact `Test SEL4IPCRPC0002 passed` line remains the Stage 3 acceptance
gate; OpenSBI or ELF-loader output alone is not counted as a pass.

The bounded runner stops the slow model immediately after that exact gate:

```sh
scripts/sel4/run_blackparrot_rpc_sim.sh sel4-rpc.nbf run.log
```

`BLACKPARROT_SIM`, `ZP_INSTALL_DIR`, and `BSG_TRACE_TIMEOUT_S` override its
model, runtime-library root, and default 90-minute guard respectively. The
runner refuses to start while any BlackParrot testbench process is live, even
when it comes from another worktree.
