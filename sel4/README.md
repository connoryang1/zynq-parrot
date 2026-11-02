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
software path. On BlackParrot, the same test additionally binds a second
blocked server through the kernel, executes 256 forced hardware calls, unbinds
it, and uses automatic routing for eight more calls. The detached hardware
backend reports a precise non-executed attempt, so each call falls back exactly
once to the same service through ordinary endpoint IPC. The focused BlackParrot
build skips the much slower 256-call software buffer workload, which remains
unchanged in the generic/QEMU regression. The cycle-accurate full-system gate
passes all 256 hardware calls and all eight post-unbind fallback calls.

Materialize the test into a pinned sel4test checkout:

```sh
scripts/sel4/materialize_sel4test_ipc_baseline.sh /path/to/sel4test-checkout
```

For the complete protected-RPC QEMU case, use a fresh build directory:

```sh
scripts/sel4/configure_qemu_rpc.sh /path/to/sel4test-checkout /path/to/build
```

This materializes only the software hardware-stub backend before configuring
the `SEL4IPCRPC0002` test. The BlackParrot configuration helper replaces that
stub with the real CSR backend. Keeping backend selection platform-specific
prevents a shared sel4test checkout from silently contaminating one build with
the other platform's sources.

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
backends must implement. The `include` directory contains only this application
header. Backend, trusted-runtime, and hardware-protocol headers live under
`internal` so a normal application include path cannot depend on tokens,
context IDs, SATPs, or BlackParrot instructions. Its initial contract is
deliberately small:

- a synchronous call carries at most four 64-bit request and reply words;
- endpoints and shared regions are opaque kernel-issued values, never context
  numbers, page-table roots, PCs, or pointers;
- a shared buffer is a region token plus an overflow-safe offset and length;
- buffer-reference encoding rejects invalid messages and zeroes any newly
  exposed word gap, so stale caller storage never becomes payload;
- region permissions and direction are fixed at binding time rather than
  accepted from caller-controlled message bits;
- services resolve buffer references through the runtime in their own address
  space and request the access their operation needs; they never cast the
  opaque token or a caller virtual address;
- handler call context is opaque; services read authenticated identity through
  `protected_rpc_caller_badge()` and cannot inspect or replace the trusted
  runtime region-table pointer;
- the same service handler is hosted by an ordinary `ReplyRecv` loop or by a
  hardware entry/return stub, so benchmarked service logic stays identical;
- forced-software and forced-hardware modes make the selected path observable.

The internal backend boundary in
[`internal/protected_rpc_backend.h`](internal/protected_rpc_backend.h) makes the
exactly-once rule explicit. A hardware attempt atomically returns one of four
states: completed, safe to fall back because execution definitely never
started, rejected without execution, or failed after its commit point. Only
the safe-to-fallback state may invoke the software backend. A separate
"eligible?" probe is intentionally excluded because endpoint state,
revocation, or scheduling eligibility could change between a probe and a call.
`AUTO` therefore may retry an unsupported, temporarily ineligible, or revoked
hardware binding through ordinary IPC only when the atomic hardware outcome
proves that service execution never began. Forced hardware reports that
outcome directly.

The current BlackParrot primitive carries up to four request and four reply
words in one fixed descriptor. General endpoint queues, capability transfer,
multiple simultaneous bindings, blocking services, and server faults remain
outside version 1 and must take ordinary seL4 IPC before execution begins.

## Ordinary seL4 backend

`src/protected_rpc.c` implements route selection and the exactly-once fallback
state machine. `src/protected_rpc_sel4.c` implements the initial software
backend with ordinary `seL4_Call`, `seL4_Recv`, and `seL4_ReplyRecv`; seL4
message labels carry the transport/service status, while up to four fast
message registers carry the payload. `src/protected_rpc_hardware_stub.c`
currently reports a precise non-executed result, allowing `AUTO` to fall back
once and forced-hardware tests to remain observable.

The server runtime owns ReplyRecv authority and invokes an application handler
with an opaque authenticated context and registered local-region table. The
handler never sees the table representation, seL4 reply capability, or future
hardware continuation. A host-side mock
test covers hardware completion, safe fallback, rejection, committed failure,
both forced routes, and the common server dispatcher. Software IPC, protected
hardware entry, and the notification control all enter that dispatcher, which
authenticates transport-provided context, clears replies, validates the trusted
region table, and canonicalizes malformed handler output. The dispatcher is an
internal runtime operation rather than a public function that could accept an
application-supplied badge.

```sh
scripts/sel4/test_protected_rpc_interface.sh
```

`src/protected_rpc_hardware_blackparrot.c` is the version-1 hardware backend
behind the same boundary. The trusted runtime associates the ordinary endpoint
with the opaque token returned by a kernel binding operation; one atomic CSR
attempt then maps completed, non-started, revoked, and committed-failure
outcomes into the existing fallback state machine. Its host-injected
architecture test covers reply decoding and proves that only a definitely
non-started attempt can reach the software backend. The atomically published
RTL descriptor and bare-metal call/return transport are implemented and
tested. Rejected calls classify the supplied token in the same CSR operation:
an absent descriptor or generation mismatch returns `REVOKED`, while a
matching live descriptor that is temporarily ineligible returns
`NOT_STARTED`. Generic/QEMU builds select the non-executed hardware stub;
BlackParrot builds select the real CSR backend and the kernel binding wrapper.
`src/protected_rpc_blackparrot_server.c` owns the matching fixed entry: it
decodes hardware request metadata, invokes the common dispatcher, and consumes
the protected continuation. Service code supplies only its ordinary server
configuration and never reads transport registers or emits `preturn`.

## Experimental seL4 kernel binding

The pinned kernel patch in
[`patches/sel4-blackparrot-rpc-kernel.patch`](patches/sel4-blackparrot-rpc-kernel.patch)
adds two private endpoint invocation labels. `BIND` requires the endpoint's
send authority plus one server-TCB extra cap. The kernel requires that TCB to
be the endpoint's sole blocked receiver, derives both SATPs and the endpoint
badge, confirms that both VSpace roots remain live in the ASID table and are
physically distinct, validates a fixed entry/SP/GP/TP and bounded word counts,
generates a fresh token, and installs the descriptor through OpenSBI. `UNBIND`
is accepted only from the recorded caller through the recorded endpoint.

The trusted wrapper in `src/protected_rpc_blackparrot_sel4.c` converts that
token into the backend-private association used by `protected_rpc_call()`.
Applications still name only their ordinary endpoint; SATPs, hardware context
IDs, slots, and tokens are not application inputs. Endpoint/TCB finalization,
TCB VSpace replacement, ASID and ASID-pool deletion, and page/page-table
mapping mutation synchronously revoke the descriptor before referenced state
can change or be recycled. This one-slot global binding is intentionally an experimental
non-MCS implementation; a general facility should use a first-class binding
capability.

The kernel, real backend, wrapper, and end-to-end test compile and link in a
fresh pinned BlackParrot image. The focused route, shared-page service, and
common-dispatch variants also pass on the routed PYNQ-Z2; the exact normalized
evidence and limitations are recorded below.

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
exact pass marker observable. The RPC-only driver uses 10-bit test-process and
private-helper CSpaces (1,024 slots each), reserves 512 KiB for itself, and
delegates one bounded 512 KiB untyped, instead of using
sel4test's generic 17-bit CSpaces and exhaustively probing every object size.
A 17-bit seL4 CNode occupies 4 MiB because each capability slot is 32 bytes;
the focused client/server test needs only a small, fixed set of capabilities.
Both CNodes are therefore 32 KiB. The dedicated-server QEMU boundary sweep
fails at 256 KiB while loading the server ELF and passes at 512 KiB, which is
the retained bound. It covers the server CNode, mappings, page tables, frames,
stack, IPC buffer, and allocator bookkeeping. The untyped cap itself is not
scrubbed, so the direct model saving comes from reducing allocated objects
rather than merely narrowing that cap. The preceding 12-bit/4 MiB
configuration had already cut roughly 40
minutes from BlackParrot setup relative to the generic configuration; the
10-bit result is QEMU-qualified for its common/software path and
full-core-qualified through hardware-test process construction. The same mode
suppresses the generic bootinfo/untyped inventory; the exact test verdict stays
enabled, while character-at-a-time diagnostic output no longer dominates boot.

The former helper path used `sel4utils_bootstrap_clone_into_vspace` to
allocate, temporarily map, copy, and unmap all 108 loadable pages of the test
image. The focused test now embeds a stripped 74 KiB server ELF and maps its 41
loadable pages instead. Including the embedded archive's 19-page footprint in
the client image, this reduces server-related setup from 108 pages to roughly
60 while preserving a distinct server VSpace. QEMU validates the ELF loader,
entry-address handshake, eight matched software calls, and clean completion;
the exact BlackParrot full-core image also qualifies the dedicated server,
same-physical-VSpace rejection, hardware route, unbind, and automatic fallback.

The same reduced configuration passes under QEMU before the slow full-core
run; its concise transcript is retained as
[`results/sel4test-rpc-only-qemu.log`](results/sel4test-rpc-only-qemu.log).

The first full-core protected call isolated an integration mismatch rather
than an RPC transport failure: all call predicates passed except SATP identity.
seL4 assigned caller/server ASIDs 2 and 3, while this BlackParrot configuration
implements one ASID bit; the old comparison narrowed only the live SATP. The
captured predicate row is retained in
[`results/sel4test-rpc-satp-diagnostic.log`](results/sel4test-rpc-satp-diagnostic.log).
The corrected comparison applies the SATP WARL narrowing to the descriptor as
well and still compares the implemented root PPN. The widened-ASID directed
regression passes with descriptor ASIDs 2 and 3 on the one-bit-ASID model; the
accepted full-core seL4 gate uses the corrected model.

The accepted full-core transcript reports 90,308 cycles for 256 hardware calls
(352 cycles/call) and 24,942 cycles for eight automatic software fallbacks after
unbind (3,117 cycles/call). Thus this focused in-guest comparison measures an
8.86x lower per-call cost for the hardware route. The fallback row includes the
precise failed hardware probe plus ordinary seL4 IPC, so it is not a claim about
all seL4 IPC workloads. The exact model and NBF SHA-256 values are
`4a58a55c...32f26e` and `00428b15...d04d`; normalized evidence is retained in
[`results/sel4test-rpc-only-blackparrot.log`](results/sel4test-rpc-only-blackparrot.log).

The same no-debug mechanism and routed configuration also pass on the PYNQ-Z2.
The physical image reports 95,975 cycles for 256 hardware calls (374/call) and
25,738 cycles for eight fallbacks (3,217/call), an 8.60x focused per-call
advantage. The suite reports three tests passed and no disabled tests, then a
test-only release-build syscall proxies to OpenSBI shutdown outside the timed
region, producing `CORE PASS`, `BSG PASS`, and runner exit zero. Physical image
SHA-256 is `00f32b95...03b4a3`; routed bitstream SHA-256 is
`ca4a6cbd...331040`, with +1.037 ns WNS. Normalized physical evidence is retained in
[`results/sel4test-rpc-only-blackparrot-fpga.log`](results/sel4test-rpc-only-blackparrot-fpga.log).
`KernelBlackParrotTestFinish` defaults off and is enabled only by the focused
test configurator; it is not part of the protected-RPC ABI or a production
userspace shutdown interface.

The next gate replaces the four-word arithmetic stub with a bounded library
service over a shared page. The caller fills 1 KiB with `a`, places `z` in the
last byte, and passes only `{region, offset, length, needle}`. A distinct
server VSpace maps that physical page read-only. Both transports invoke the
same handler, which makes two non-inlined musl `memchr` calls and returns the
match and NUL offsets. Before the valid bind, the FPGA test proves that the
kernel rejects a different physical page, a write-permission escalation, and
an unmapped runtime-state pointer.

On the PYNQ-Z2, the matched warm averages are 2,963 cycles for a direct call to
the handler, 3,347 for hardware RPC, and 5,649 for forced ordinary seL4 IPC.
Hardware therefore adds 384 cycles over the useful handler, versus 2,686 for
ordinary IPC, and is 1.69x faster end to end. Eight automatic fallbacks average
6,545 cycles in the retained run because they include the precise failed
hardware probe before
ordinary IPC; that row remains a correctness gate rather than the primary
software baseline. The smaller application ratio than the scalar gate is
expected because nearly 3,000 cycles of page scanning are common service work.
Separate 64-call warm samples report medians of 2,782/3,138/5,283 and p95
values of 4,955/5,319/7,474 for in-process/hardware/software. Hardware's
incremental warm cost is therefore 356 cycles at median and 364 at p95, while
ordinary IPC adds 2,501 and 2,519.

The same physical run uses BlackParrot's whole-L1D writeback/invalidate
instruction before every timed call. It leaves L1I and the lower cache warm,
so this is an L1D-cold experiment rather than a DRAM-cold claim. The resulting
medians are 3,708/4,319/10,045 cycles and p95 values are
7,313/7,955/13,874. Hardware adds only 611 cycles over the cold direct handler
at median, while ordinary IPC adds 6,337; the complete hardware service is
2.33x faster.

A second matched condition scans four page-aligned pages—four times the exact
4 KiB L2 capacity and eight lines per set—then flushes L1D again. This makes
L1D and L2 cold while leaving L1I warm and deliberately makes no DDR row-buffer
claim. Its medians are 4,190/4,880/9,585 and p95 values are
8,173/8,868/12,829. Hardware adds 690 cycles over direct work versus 5,395 for
ordinary IPC and is 1.96x faster end to end. Evicting L2 adds 482/561 cycles to
the compact direct/hardware medians but no additional software penalty in this
run, consistent with the ordinary IPC path already exceeding and self-evicting
the small L2 working set.
The routed bitstream is unchanged; the final NBF SHA-256 is
`be672bed...4ce1`. QEMU separately validates the
dedicated server, shared mapping, handler, and software transport. Normalized
evidence is retained in
[`results/sel4test-rpc-shared-search-fpga.log`](results/sel4test-rpc-shared-search-fpga.log)
and
[`results/sel4test-rpc-shared-search-qemu.log`](results/sel4test-rpc-shared-search-qemu.log).

A subsequent physical run adds the remaining shared-memory notification
control without changing the handler, protected data page, routed bitstream,
or timing boundaries. Its mailbox is shared read/write—strictly weaker than
the protected RPC contract—and two one-way notifications carry only wakeups.
Warm medians are 2,786/3,150/5,189/10,226 cycles for
in-process/hardware/software/notification. L1D-cold medians are
3,700/4,335/9,937/15,042, and L1D+L2-cold medians are
4,163/4,867/9,431/14,472. Thus the notification design is 1.97x slower than
ordinary endpoint IPC and 3.25x slower than hardware RPC at warm median. This
is expected from the mechanism: endpoint `Call` plus server `ReplyRecv`
provides a direct request/reply handoff, while the notification protocol needs
separate caller `Signal`/`Wait` and server `Wait`/`Signal` operations plus
mailbox publication. It is therefore a useful negative baseline, not a better
software implementation to optimize against. The accepted NBF is
`0d90d7bf...1e99b`; normalized evidence is in
[`results/sel4test-rpc-notification-fpga.log`](results/sel4test-rpc-notification-fpga.log).

A timestamped physical run separates transport from useful work using
BlackParrot's core-wide `0xCC0` counter at handler entry and exit. Warm median
pre/service/post costs are 13/2,779/8 cycles in-process, 232/2,766/159 through
hardware RPC, 1,363/2,847/1,317 through ordinary endpoint IPC, and
3,708/2,847/3,718 through notifications. Thus hardware's two transitions and
wrappers cost 391 cycles around a 2,766-cycle service, versus 2,680 cycles
around the ordinary-IPC service. Relative to the direct 21-cycle wrapper, the
hardware path removes 86.1% of ordinary IPC's transport premium and completes
the whole call only 1.13x slower than direct execution. Component arrays are
sorted independently, so their medians need not sum exactly to the separately
sorted total median. Normalized evidence is in
[`results/sel4test-rpc-components-fpga.log`](results/sel4test-rpc-components-fpga.log).

Those numbers predate the final common server boundary. In the first
common-dispatch image,
ordinary endpoint IPC, protected hardware entry, and notifications all invoke
`protected_rpc_dispatch()`, which validates the trusted server configuration
and request, supplies the authenticated caller badge, clears the reply, and
canonicalizes malformed handler output. The current warm total medians are
2,905/3,387/5,696/10,541 cycles for
in-process/hardware/software/notification, and pre/service/post medians are
13/2,884/8, 342/2,874/171, 1,412/2,977/1,304, and 3,848/2,954/3,729.
Hardware therefore remains 1.68x faster than ordinary IPC and removes 81.7%
of its transport premium over direct execution. The validation cost is
visible: hardware pre/post increased from 232/159 to 342/171 cycles rather
than being attributed to useful service work. Current-interface evidence is
in
[`results/sel4test-rpc-common-dispatch-fpga.log`](results/sel4test-rpc-common-dispatch-fpga.log);
the preceding component file remains the historical pre-dispatch result.

The current trusted-runtime image additionally moves BlackParrot request
metadata decoding, installed `s1`/`tp` state, reply metadata, and the sole
`preturn` instruction out of the service executable. The application supplies
only the same transport-neutral handler and region configuration used by the
ordinary seL4 path. Its physical run verifies kernel-derived caller badge
24090 through both software and hardware paths and reports warm medians of
2,925/3,448/5,479/10,612 cycles for
in-process/hardware/software/notification. The corresponding pre/service/post
medians are 15/2,901/9, 363/2,902/183, 1,302/3,002/1,176, and
3,864/3,000/3,737. Hardware is 1.59x faster than ordinary IPC and removes
78.7% of its transport premium over the direct wrapper. L1D-cold and
L1D+L2-cold hardware medians are 4,884 and 5,748 cycles, versus 10,106 and
9,792 for ordinary IPC. The retained evidence is
[`results/sel4test-rpc-trusted-runtime-fpga.log`](results/sel4test-rpc-trusted-runtime-fpga.log).

The lifecycle-qualified image additionally verifies mapping-triggered
revocation, atomic stale-token rejection, and successful rebind on the routed
PYNQ-Z2. Its warm medians are 2,934/3,461/5,440/10,597 cycles for
in-process/hardware/software/notification, so hardware is 1.57x faster than
ordinary IPC and 1.18x direct. L1D-cold hardware/ordinary medians are
4,821/10,072; data-hierarchy-cold medians are 5,421/9,809. The strict physical
checker accepts the lifecycle, badge, shared-buffer, component, test-suite,
core, host, and exit markers in
[`results/sel4test-rpc-lifecycle-fpga.log`](results/sel4test-rpc-lifecycle-fpga.log).
The wrapper's duplicated live-plus-saved output is retained separately under
`logs/sel4-rpc-lifecycle-20261102/` and is intentionally rejected as evidence.
The exact full-system simulator independently reaches the region guard and
complete revoke/stale-token/rebind marker, then hits its four-hour trace limit
before the timing loops; it is partial lifecycle evidence, not a simulation
performance or suite-pass claim.

The initial component image hung because the separately compiled stripped
server did not include seL4's generated platform configuration and emitted
`rdcycle`; the clean hardware server intentionally has no permission for that
architectural counter. The service now includes `<sel4/config.h>` explicitly,
and the NBF packager rejects a BlackParrot server containing `rdcycle` or fewer
than two `0xCC0` reads.

The host must provide the pinned checkout's Python packages plus CMake, Ninja,
and `riscv64-unknown-elf-*` on `PATH`. Package the resulting elfloader behind
the qualified BlackParrot OpenSBI platform with:

```sh
SEL4_CROSS_PREFIX=/path/to/riscv64-unknown-elf- \
OPENSBI_CROSS_PREFIX=/path/to/riscv64-unknown-linux-gnu- \
scripts/sel4/package_blackparrot_rpc_nbf.sh \
  /path/to/build /path/to/opensbi-repo /path/to/work sel4-rpc.nbf
```

The same default, no-debug image is used by the full-core simulator and the
physical `control-program` path. Do not add `nbf.py --debug`: OpenSBI expects
ordinary M-mode entry and has no `dret` startup stub. A debug-start image runs
until its first synchronous feature probe, then redirects to the debug
exception entry instead of OpenSBI's `mtvec` handler. The packager therefore
rejects `NBF_DEBUG=1` rather than producing an image that can restart silently.

Board staging is not a reservation: another host workflow can acquire the
remote lock after staging and before overlay load. Recheck both local board
orchestrators and the remote runner immediately before any power cycle and
again immediately before loading; if a new owner appears, cancel the pending
loader so it cannot resume after that run. The serialized overlay and program
helpers remain authoritative at their individual launch boundaries.

For FPGA qualification, use `e_bp_unicore_zynqparrot_sel4_cfg`. Its two
resident threads, four logical contexts, 50-bit branch metadata, and one L2
bank match the accepted full-core model. It differs from the general-purpose
FP-capable endpoint only by pruning floating-point state and divide/square-root
hardware that the version-1 integer-only service does not execute; integer
multiply/divide and the complete RPC/context topology remain. Do not use the
historical `prefetch5` endpoint for this test: its ten contexts, detached data
prefetch hardware, and second L2 bank are unrelated to the fixed contexts 0/1
RPC path and exceed the XC7Z020 placement capacity in the current source tree.

The packager pins OpenSBI commit `7830e987856eb1319c82664702892b6d50a93e7a`,
disables the unrelated I-cache replay table, embeds the exact seL4 DTB, and
selects the routed 8 MHz timer. It places the payload at the elfloader's linked
entry instead of OpenSBI's default address, avoiding an otherwise redundant
self-relocation in the slow core model. It also defaults to OpenSBI's
no-boot-prints option because character-at-a-time firmware diagnostics consume
several model minutes; set `OPENSBI_FW_OPTIONS=0` when those diagnostics are
needed. `OPENSBI_RISCV_ISA=rv64imafdc` supports older toolchains whose base ISA
already includes CSR and fence instructions; the default remains the explicit
`rv64imafdc_zicsr_zifencei` spelling. Its output is deterministic for fixed
inputs. If the OpenSBI cross
compiler is unavailable, `OPENSBI_BASE_FIRMWARE=/path/to/fw_payload.elf` reuses
a previously qualified firmware container whose `.payload` address matches the
new elfloader. The packager replaces only that section, extracts it again, and
requires byte equality before generating the NBF.

The simulation NBF loader stages guest DRAM again after configuration writes
because the low BlackParrot unfreeze address aliases guest DRAM through the
model's 32-bit HP0 transform. Physical loading is unchanged. The ordinary RPC
test's exact `Test SEL4IPCRPC0002 passed` line remains the Stage 3 acceptance
gate; OpenSBI or ELF-loader output alone is not counted as a pass.

The bounded runner stops the slow model immediately after that exact gate:

```sh
scripts/sel4/run_blackparrot_rpc_sim.sh sel4-rpc.nbf run.log
```

For interface changes that need lifecycle correctness rather than a new
performance result, configure with `SEL4_RPC_SMOKE=ON` and run with
`SEL4_RPC_SMOKE=1`. This keeps the same service, authorization guards,
map-triggered revoke, stale-token rejection, rebind, and fallback path, but
uses two measured hardware calls, one fallback call, and one sample per
distribution/cold-cache class. The smoke checker requires those exact reduced
counts and the default checker rejects them; smoke output is never performance
evidence.

To exercise the version-2 failure boundary end to end, additionally configure
and run with `SEL4_RPC_FAULT_INJECTION=ON` and
`SEL4_RPC_FAULT_INJECTION=1`, respectively. This test-only build bypasses the
already-qualified comparison workloads and same-VSpace negative helper, then
injects an illegal instruction from the protected service. Acceptance still
requires the physical-region/permission/runtime guards, one `SERVER_FAULT`
caller unwind, a non-entering retry, kernel consumption of the
token-authenticated fault record during unbind, and a successful normal call
under a fresh generation. The injection macro is not present in ordinary
correctness or performance images.

`BLACKPARROT_SIM`, `ZP_INSTALL_DIR`, and `BSG_TRACE_TIMEOUT_S` override its
model, runtime-library root, and default four-hour guard respectively. The
runner refuses to start while any BlackParrot testbench process is live, even
when it comes from another worktree. An isolated correctness run with distinct
read-only model and image artifacts may opt out with
`BLACKPARROT_ALLOW_CONCURRENT_SIM=1`; do not use that override for host-time
measurements. The guest's simulated cycle counts are unaffected by host
scheduling. The runner records the model and NBF paths and
SHA-256 values before launch. A model override must implement the same
descriptor-control ABI as the packaged OpenSBI: an older model can boot the
entire seL4 image but reject installation with control status `UNSUPPORTED`,
which is artifact-mismatch evidence rather than a kernel binding failure. The
descriptor-v1 directed regressions currently qualify model SHA-256
`5925788e632135b9cc1b705d1c8e5fb3d07be2b77a15c7176bcd5ebecb3456bc`.
