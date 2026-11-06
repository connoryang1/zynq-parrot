This directory records the zero-data isolation for the tagged wakeup instruction-follow path. The diagnostic keeps the same accepted tagged command and hardware-generated instruction trigger as joint replay, while configuring an empty data slot so no detached data request can launch.

# Joint follow-only diagnostic

## Question and decision gate

The routed joint instruction/data result lost the approximately 3.8k-cycle
instruction-only wake-to-first-load gain even though the hardware-follow trigger
is generated only a few controller cycles after the tagged wake command. This
diagnostic retains the 32-line target demand footprint but programs
`lines_per_base=0` into the tagged slot. An enabled arm must therefore report one
accepted trigger, zero admitted or resident-filtered data entries, and zero
drops.

- Recovery toward the instruction-only result localizes suppression to detached
  data traffic after launch.
- A result resembling ordinary joint replay instead localizes the problem to
  the hardware-follow trigger path or its timing.

This is an isolation experiment, not a proposed user ABI: the zero-entry
configuration exists only to distinguish those mechanisms.

## Exact source and artifacts

- Top-level source base: `e0662a13f51cee05777cae6d9bf20b84b5ce1c87`
- Accepted routed RTL: BlackParrot
  `20ac3b31df6c67b78e0362089699cae7c2df5c9f`
- Routed bitstream SHA-256:
  `1caf54e7e1adb2eec7ac7a0eb32b3827d3c9c364cbb76dfed45eb77648d4949f`
- Linux `vmlinux` SHA-256:
  `9e5babb359ac56e944a3334f7688b324101f030800d9effd5d77041c0d23647d`
- OpenSBI payload ELF / `linux.riscv` SHA-256:
  `0d8025b580152cf4aef27b2266febeccf3b47d143b5909dcf68bb42ca0073e1c`
- Patched shell NBF SHA-256:
  `27dda0a79e21444ac86b33993400610838a27d5c0502fc97a555e4ac66dd0b9f`
- Dynamic benchmark SHA-256:
  `66f3fcfc636a9fdfe56322674f698606afad971c39097d71adf26f14a8a3ca5e`
- Validated transfer SHA-256:
  `56f85754bc0acfb01e4e1306ef8e5500e625e3cce33d4f7afbe9e300326bcefa`

The immutable runtime artifacts are under
`/home/coyang/fpga-artifacts/context-resume/follow-only-diagnostic-20261106/`.
The shell transform changes one boot-argument string through five aligned
writes and retains the accepted 8 MHz timer configuration.

## Pre-board validation

- `git diff --check` passes.
- `python3 -m unittest discover -s linux-tests -p 'test_*.py'` passes all
  189 tests.
- The RV64 dynamic benchmark compiles with the prepared Buildroot GCC 13.2.0
  toolchain.
- The linked `__do_sys_prctl` disassembly proves that an empty base table plus
  zero `lines_per_base` reaches the `0x9c2` configuration write; a nonzero line
  count with no base still returns an error.
- The Linux executable scan is collision-free for reserved CSRs `0x800` through
  `0x807`.
- The OpenSBI `.text` scan is collision-free for `0x5c0`, `0x800` through
  `0x807`, and `0x9c0` through `0x9c3`.
- The Linux scan finds seven reviewed `0x9c1`--`0x9c3` sites: release-idle read,
  configuration-idle read, configuration write, status read, table-entry write,
  wake trigger, and scheduler follow trigger. These are intentional.
- The serialized runner validates the transfer framing before deployment.

## Workflow guardrails

The first focused unit-test command named two nonexistent modules; the actual
45 focused tests passed, but the loader errors invalidate that aggregate
invocation. The corrected full discovery run above is authoritative.

The default cross-compiler name was absent, so the first benchmark compilation
failed closed before producing a candidate; the exact Buildroot compiler path
was then used. The first image attempt also lacked an explicitly supplied
baseline NBF, and a later packaging attempt lacked Buildroot's `strip` in
`PATH`; neither failed attempt produced an accepted image. The successful build
uses the verified baseline
`994bd900...21d5` and prepends the complete Buildroot host-tool directory.

An initial CSR-audit retry assumed the nonexistent
`riscv64-buildroot-linux-gnu-objdump` name and an unmaterialized OpenSBI build
path. It failed closed. The authoritative scans use the existing
`riscv64-linux-objdump` symlink and immutable copied ELFs. Scanning every
executable segment of `fw_payload.elf` also traverses the embedded Linux payload
and initramfs; OpenSBI's own `.text` plus the separate Linux `vmlinux` scan are
the scoped collision gates.

## Board result

Pending. A valid run must use the exact routed package and NBF above, complete
512 phase-balanced skewed/futex trials, observe 256 accepted enabled triggers,
observe zero admitted, filtered, and dropped entries, and finish with guest,
kernel, core, and host PASS markers. A terminal or interrupted run requires a
hard board recovery before any retry.
