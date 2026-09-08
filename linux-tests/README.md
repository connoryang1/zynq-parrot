This directory builds a Linux-resident proof of BlackParrot's user
context-switch interface.  Its acceptance image runs a tiny static program as
PID 1 so the result is independent of BusyBox startup and filesystem tools.

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
ownership fixes under verification on `fix/linux-resident-csr-init`. Do not
use the previously accepted `6c97bcc0a` bitstream for the resident case; FPGA
acceptance of the combined test is still pending.

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
