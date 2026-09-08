This directory builds Linux demonstrations of BlackParrot's user context-switch
interface and independent-request benchmark comparisons. The context-switch
acceptance image runs a tiny static program as PID 1 so the result is independent
of BusyBox startup and filesystem tools.

# Linux Context-Switch Smoke Test

The program runs in Linux U-mode in context 0, writes the naked return
trampoline address to context 2 using CSR `0x801`, and invokes CSR `0x800` to
perform `0 -> 2 -> 0`.  Context 2 writes a shared magic value and its observed
logical context ID before returning.  It also observes and overwrites an
`s11` value seeded through CSR `0x802`, while context 0 verifies its distinct
live `s11` value was restored, so neither a no-op nor a redirect-only design
can produce PASS.  With the static two-resident/four-logical configuration, both
directions are nonresident transitions through the hardware context backing
store.  This proves an explicit SRAM-backed handoff from ordinary Linux C,
but does not claim context 2 is an independently scheduled Linux process.

Build it only with the matching BlackParrot Linux toolchain after the Linux
boot image is known-good.  The archive on this VM currently provides one at
`/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc`;
pass it explicitly rather than assuming a host package is compatible:

```sh
make -C linux-tests app \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc
```

Each application target recompiles its small ELF so compiler or option changes
cannot reuse stale executables. Compiler diagnostics go to stderr, keeping
redirected transfer commands usable even when the ELF is rebuilt. Run
`make -C linux-tests check-harness` for isolated host checks of compiler/flag
changes, failed builds, and transfer integrity; no cross toolchain is required.

To create the definitive, reproducible PID-1 boot image, run:

```sh
make -C linux-tests tiny-init-linux-image \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc
```

This deliberately recreates the SDK work tree and embedded initramfs, installs
the no-libc ELF as `/ctxtsw_user_tiny`, changes only the DTS bootargs to select
that ELF as `rdinit`, and produces
`linux-tests/out/linux-ctxtsw-tiny-init.nbf`.  The build first verifies the
baseline Linux NBF has no collisions with custom CSRs `0x800`--`0x804`; the
demo image itself intentionally uses `0x800`--`0x802`.  Before packaging, it
also requires the exact PID-1 bootargs and byte-compares the current tiny ELF
against the executable copy inside the initramfs.  It then verifies the
decompiled DTB, the kernel's compressed initramfs input, and the final OpenSBI
payload identity/freshness before creating the NBF.  A successful program
prints PASS and invokes Linux's poweroff syscall, which should end the board
run in `CORE[0] PASS`.

The target also materializes `opensbi-platform/blackparrot` into the pinned
OpenSBI source tree.  The SDK selects this platform but does not track those
four files, so keeping the known-working copy here makes a clean image build
independent of another user's home directory.

If that full build finishes the kernel but stops later because of a packaging
or host-tool problem, `tiny-init-linux-image-resume` continues from the
prepared work tree. It re-stages the current tiny ELF before rebuilding the
rootfs, kernel payload, and NBF, so an application edit cannot silently reuse
an older embedded executable. It is a recovery target, not a substitute for
the clean acceptance build.

The older `linux-image` target remains available for a libc/BusyBox integration
test, but it is not the acceptance path because rcS and sysctl have shown
unrelated intermittent failures on the baseline overlay.

## Run a separate executable from the Linux shell

This path transfers the program into an already-running guest; it does not
embed the test in Linux or rebuild the kernel. The shell variant uses Linux
`exit(0)` after PASS instead of the PID-1 variant's poweroff syscall.

On the VM, prepare the shell image and transfer commands:

```sh
make -s -C linux-tests emit-shell-transfer \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  > linux-tests/out/ctxtsw_user_shell.transfer
sha256sum linux-tests/out/ctxtsw_user_shell
python3 codex-skills/bp-fpga-synthesis/scripts/make_linux_shell_nbf.py \
  riscv/linux/linux-6.6-jhumphri-20250125.nbf linux-tests/out/linux-shell.nbf
scp linux-tests/out/linux-shell.nbf linux-tests/out/ctxtsw_user_shell.transfer \
  xilinx@192.168.4.35:~/zynq-parrot/cosim/black-parrot-example/zynq/
```

On the board's ARM Linux shell, with the accepted context-switch overlay and
reviewed `control-program` already staged:

```sh
cd ~/zynq-parrot/cosim/black-parrot-example/zynq
cat ctxtsw_user_shell.transfer
```

Copy the printed commands for later, then boot the RISC-V guest:

```sh
make -o control-program load_bitstream run \
  BOARDNAME=pynqz2 VIVADO_VERSION=2024.2 VIVADO_MODE=batch \
  NBF_FILE=linux-shell.nbf
```

`-o control-program` preserves the reviewed host executable; the old board
Makefile must not rebuild it with different DRAM settings. These are manual
terminal instructions: ensure no other board run is active. Automated agents
must use the serialized interactive runner from the FPGA skill instead.

At the guest's `~ #` prompt, paste the transfer commands in small groups
(about five lines), waiting for them to finish. They create the executable in
`/tmp` using `echo`, `base64`, and `chmod`, but do not run it. Check
`sha256sum /tmp/ctxtsw_user_shell` against the VM's hash before continuing:

```sh
/tmp/ctxtsw_user_shell
echo CONTEXT_SWITCH_EXIT=$?
uname -m
```

Require the program-specific marker, exit status zero, and a usable shell:

```text
[BP-LINUX-CTXTSW] PASS: tiny user-mode handoff
CONTEXT_SWITCH_EXIT=0
riscv64
```

Finish with `poweroff -f` inside the guest, which should return to the ARM
shell through `CORE[0] PASS`. Use the test **once per fresh overlay/Linux boot**:
Linux does not reclaim context 2's saved CSR state when this process exits.
This demonstrates a shell-launched cooperative handoff, not general process
lifecycle management or independently scheduled Linux hardware threads.

The September 7, 2026 board run verified the transferred ELF hash, handoff,
exit status, subsequent shell command, and clean poweroff on RTL `6c97bcc0a`;
evidence is in `logs/linux-shell-demo-20260907/`. The initial here-document
transfer crashed BusyBox before the test ran; the short-command method above
passed, but that result does not establish the earlier crash's root cause.

## Linux switch-spacing benchmark

`ctxtsw_user_benchmark.c` measures resident `0↔1` and nonresident `0↔2`
handoffs in one shell-launched Linux process. Each mode uses seven samples of
256 switches with core-wide CSR `0xCC0`, after untimed warm-ups. A separate
untimed handoff finishes the peer's loop, checks its identity and seeded
register, and executes `getpid` from the target; the source verifies its own
restored register and the returned process ID. Console output and syscalls are
outside the measurement; interrupts remain enabled.

The combined benchmark requires the resident-initialization and fetch/replay
ownership fixes in RTL `aad56bd92`, now integrated into `master`. Use the
resident-fix bitstream identified in [the checkout guide](../CURRENT_CHECKOUT.md#fpga-acceptance-identities);
the earlier `6c97bcc0a` bitstream does not qualify the resident case.

Prepare its transfer file on the VM:

```sh
make -s -C linux-tests emit-benchmark-transfer \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  > linux-tests/out/ctxtsw_user_benchmark.transfer
sha256sum linux-tests/out/ctxtsw_user_benchmark
```

Use the shell workflow above with this transfer file instead of the smoke
test's file. After checking the guest executable's checksum, run
`/tmp/ctxtsw_user_benchmark`, immediately followed by `echo BENCH_EXIT=$?`.
Require the benchmark-specific PASS and exit zero. Do not run the smoke and
benchmark executables in the same guest boot: the extra context state is not
reclaimed between processes.

On September 8, 2026, the combined benchmark passed on the exact resident-fix
image. The first warm-up exercises first-seed initialization and performs all
correctness checks; subsequent trials also check reseeding. Resident raw
256-switch samples were `1311 1307 1307 1307 1307 1307 1307`, with median
5.10546875 and maximum 5.12109375 cycles/switch. Nonresident samples were
`2857 2853 2853 2853 2853 2853 2853`, with median 11.14453125 and maximum
11.16015625. The median difference is 6.0390625 cycles/switch.
The guest ELF checksum, resident/final PASS markers, `BENCH_EXIT=0`, subsequent
`uname -m`, and `poweroff -f` through `CORE[0] PASS` all passed; the runner exited
zero. Exact artifacts, a serialized acceptance driver, and both closed
transcripts are retained in `logs/linux-resident-shell-20260908/`.

The earlier nonresident-only version on FPGA RTL `6c97bcc0a` measured raw totals
`2856 2852 2852 2852 2852 2852 2852` cycles: median 11.140625 and maximum
11.15625 cycles/switch. The program's `x100` display truncates to integers.
All checks, shell return, and clean poweroff passed; evidence is in
`logs/linux-shell-benchmark-20260907/`.

These are amortized loop costs including calls, counter reads, loop control,
and possible Linux interference—not isolated hardware redirect latency or
a speedup against the Linux scheduler. The earlier bare-metal 11.12 result
uses a different binary and is contextual, not an identical regression gate.
The combined version uses a matched indirect call for both rings; its totals
are not an identical-binary regression comparison with that earlier version.

## Independent random-request comparisons

`request_benchmark.c` implements the baseline and batching comparisons from the
[`context-switches` proposal](https://github.com/connoryang1/context-switches):

- `linux-threads-demand`: `n` persistent POSIX threads pinned to one Linux CPU.
  Each worker consumes one random data load per request, with no prefetch and
  no voluntary yield between requests. Linux schedules the workers normally.
- `batched-prefetch-load`: one thread issues `n` prefetches, one for each
  worker's current request, then consumes those `n` loads. This is the batching
  reference; batching independent requests in an application may be impractical.

On BlackParrot, `--hardware --workers 2` additionally enables two matched modes
on the accepted two-resident/four-logical configuration:

- `resident-prefetch-yield-load`: each hardware context computes its own request
  address, issues `prefetch.r`, yields to its peer, then consumes its load when resumed.
- `resident-demand-handoff`: the same address/yield/load sequence, without the
  hint. This measures the handoff schedule's cost without prefetching.

The hardware source and peer are leaf assembly with no padding computation.
Both resident modes time the final drain handoff, so the last response from each context
has completed before timing ends. Peer count, context identity, and both
checksums must pass. Register seeding is untimed; the final NPC seed is inside
the wall-clock interval and before the physical-cycle interval. These modes are cooperative
contexts inside one Linux thread, not two independently scheduled Linux tasks;
the pthread mode remains the actual Linux scheduler baseline.

All enabled modes execute identical per-worker request streams and demand-load counts.
Every response contributes to a per-worker checksum verified against the
address-derived expected value after every run, including warm-up. Each next
request's index depends on its worker's previous response through a runtime-zero
mask; this prevents speculative overlap of later requests within a baseline
worker. Data values occupy the first eight bytes of separate 64-byte lines.
Xorshift32 generates precomputed indices using worker seed
`0x9e3779b9 ^ (worker + 1)`; generation and data initialization are untimed.

Create and validate a host executable:

```sh
make -C linux-tests request-benchmark-host check-request-benchmark
linux-tests/out/request_benchmark_host --workers 2 --requests 4096 --samples 5
linux-tests/out/request_benchmark_host --workers 10 --requests 4096 --samples 5
```

Two workers match the accepted hardware's resident capacity; ten workers match
the original proposal. Compare modes within the same invocation and report
their worker count. The host executable uses an explicit x86 `prefetcht0`
instruction. Its timings describe that host and are not BlackParrot results.
Unsupported architectures fail at compilation instead of silently omitting
prefetches.

Build the static BlackParrot Linux executable with the matching SDK:

```sh
make -C linux-tests request-benchmark \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc
make -s -C linux-tests emit-request-transfer \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  > linux-tests/out/request_benchmark.transfer
sha256sum linux-tests/out/request_benchmark
```

The default BlackParrot backend is `blackparrot-zicbop-prefetch-r-l2`.
Both C batching and resident assembly use [`bp_prefetch.h`](../software/include/bp_prefetch.h),
which emits the standard Zicbop read hint (`ori zero, base, 1`). On the implemented
noncoherent writeback path, a permitted cacheable DRAM address with a usable
DTLB hit can issue a best-effort L2-warming request. Missing translations are
dropped without page walks or architectural faults. L1 hits and unavailable
request capacity can also drop hints. Two UCE slots track accepted hints;
two separate L2 banks can overlap misses, while a single bank still serializes
them. A batching width of ten does not create ten hardware slots. The compiler
memory barrier is not a hardware fence or an issuance guarantee.

This executable uses libc and pthreads, so it is much larger than the existing
no-libc shell demos. The transfer file is optional and follows the same
short-command shell transfer and checksum-validation procedure above; transferring
it over the guest console can be slow. For the accepted shell image, use the
compact dynamically linked variant instead:

```sh
make -s -C linux-tests emit-request-dynamic-transfer \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  > linux-tests/out/request_benchmark_dynamic.transfer
sha256sum linux-tests/out/request_benchmark_dynamic
```

`request-benchmark-dynamic` builds the same source with the same optimization,
ISA, ABI, topology, and pthread flags, removing `-static` and adding `-no-pie`.
The static `request-benchmark` target remains available. The dynamic executable
requires `/lib/ld-linux-riscv64-lp64d.so.1` plus `libc.so.6`. Check the exact ELF's
loader and symbol-version requirements with the matching SDK `readelf -l` and
`readelf --version-info` before transfer. The earlier discarded-load executable's
33 versioned imports were checked against libraries extracted from
`riscv/linux/linux-6.6-jhumphri-20250125.nbf`; its compatibility evidence is in
`logs/independent-requests-20260908/linux-dynamic-build/`. That historical check
does not identify a newly built ELF or substitute for its guest execution.

The ordinary discarded-load control remains available under separate names:

```sh
make -C linux-tests request-benchmark-load-ahead request-benchmark-load-ahead-dynamic \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc
make -s -C linux-tests emit-request-load-ahead-dynamic-transfer \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  > linux-tests/out/request_benchmark_load_ahead_dynamic.transfer
sha256sum linux-tests/out/request_benchmark_load_ahead_dynamic
```

These variants print backend `blackparrot-faulting-lbu-x0`, with
`batched-load-ahead-load` and `resident-load-ahead-yield-load` mode names.
Their `lbu x0` operations are ordinary faulting loads and retain the historical
single-demand-miss behavior. They use the same request streams, control modes,
context protocol, and timing as the hint variants. The static transfer target
is `emit-request-load-ahead-transfer`. Keep their ELF and result identities
separate from actual prefetch hints; the host build rejects this RV64 control
instead of silently substituting x86 prefetches.

Use the transferred executable's own name in the guest commands below:
`/tmp/request_benchmark_dynamic` for the dynamic variant or
`/tmp/request_benchmark` for the static variant. Once transferred and its hash checked,
run `/tmp/request_benchmark --workers 2 --hardware`, followed immediately by
`echo REQUEST_EXIT=$?`; require `[REQUEST-BENCH] PASS` and exit zero. Repeat with
`--workers 10` without `--hardware` for the original baseline and batching width.
The prefetch experiment requires an overlay containing the implemented hint
path and its L2-controller changes; the earlier resident-fix overlay alone does
not implement hints. The hardware option requires
**one hardware-enabled invocation per fresh overlay/Linux boot**. Linux does
not reclaim the extra context when the process exits. Do not run another
context-switch demo in the same boot. Without the option, the program allocates
only ordinary Linux threads and can be repeated normally. Host hardware mode
and hardware runs with a worker count other than two fail instead of being
silently skipped.

The earlier discarded-load candidate completed its first resident mode but
hung on its second resident mode. Changing the helper preserves the resident
seeding and handoff protocol; it does not resolve or diagnose that failure.
The retained `WARMUP_BEGIN` and `WARMUP_PASS` markers localize untimed failures.
The hint executable is a candidate for a fresh Linux acceptance run on the new
overlay. Cross compilation, host checks, and bare-metal prefetch tests do not
establish that this complete Linux comparison passes or improves performance.

The defaults are two workers, 4,096 requests per worker, a 2 MiB data working
set, and five measured samples. Use `--help` for validated bounds and an explicit
`--cpu` selection; the default is the first CPU allowed by the process affinity
mask. The program fails if it cannot verify singleton CPU affinity. Choose a
working set larger than the cache under study. Before each mode it scans a
separate buffer twice the data size to displace cached lines; this is not a
cache flush, and random requests can revisit lines. Do not infer a miss rate
without cache or trace measurements. The first trial warms and checks all
enabled modes without printing timing rows; subsequent trials rotate their execution order.
The displacement scan can also evict data translations. Random hints can
therefore drop on DTLB misses even when the corresponding demand later succeeds.
Do not add translation-priming loads to only one mode or infer accepted hint
counts from the number of executed hint instructions.

Output retains each sample's raw `CLOCK_MONOTONIC` nanoseconds, request count,
checksum, backend, and configuration. BlackParrot also reports core-wide
physical-cycle CSR `0xCC0` for every mode, including the Linux threads. The
cycle interval nests inside the wall-clock interval and excludes the
`clock_gettime` calls; both intervals include the complete request operation.
For resident modes the wall-clock interval additionally includes the final
NPC seed, keeping deliberate syscalls outside the seed-to-handoff sequence.
Linux interrupts and scheduling remain enabled. The program does not use
virtualized `rdcycle` for these measurements. Allocation, page initialization, index
generation, thread creation/join, cache displacement, checksum checks, and
printing are outside timing. The threaded interval includes releasing the
worker pool, normal Linux scheduling, and recording completion by the last
worker; it does not force a kernel switch per request. These fixed costs can
dominate tiny runs, so increase request count when evaluating throughput. The
batched interval covers the single-thread request loop. Hardware intervals
include the source loop and final peer completion handoff. These intervals are not
isolated context-switch latency measurements. The batched loop is compiler-generated
C while hardware loops are leaf assembly, so their bookkeeping costs differ;
compare complete implementations rather than attributing the entire difference
to switching or cache behavior. Bare-metal results from a
different request stream or cache state are not a matched speedup comparison.
