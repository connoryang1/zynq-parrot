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

For the first, faster FPGA proof, do not rebuild Linux.  Build the tiny
no-libc C ELF and paste its generated command into an interactive Linux shell:

```sh
make -C linux-tests emit-tiny-transfer \
  BP_LINUX_CC=/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc
```

The command writes the tiny ELF to `/tmp`, marks it executable, runs it, and
prints the program's real `CONTEXT_SWITCH_EXIT=<status>` after the handoff
marker.  This is still a normal Linux U-mode program; it simply avoids needing
a compiler or persistent storage on the board.

The expected console marker is:

```text
[BP-LINUX-CTXTSW] PASS: tiny user-mode handoff
```
