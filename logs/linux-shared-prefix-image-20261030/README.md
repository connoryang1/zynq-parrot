# Linux shared-prefix image checkpoint

The canonical SDK image now contains both software endpoints of the shared
instruction replay interface.

- Linux `vmlinux` disassembly places `csrw 0x5c0, zero` at
  `0xffffffff808132c2` in `__schedule()`, before scheduler state selection.
- The raw `vmlinux.bin` contains exactly one `73 10 00 5c` launch encoding, at
  file offset `0x8132c2`.
- OpenSBI `platform_early_init` loops from `bp_icache_prefix` to its end,
  writes each indexed address with `csrw 0x7c1,a4`, and finally writes
  `(1 << 63) | 197` with `csrw 0x7c2,a5`.
- Re-running `stage-linux-prefix-trigger` reports the patch already applied.

Artifact SHA-256 values:

```text
1cea1d5310e188912c87cbb306c87ad0b29c21a9dec1530b9edaa481adeb850f  vmlinux
9f20d67c904c2feee60bf08d0d11b87507a989f3506d943baf652974a0551b2b  vmlinux-stripped
329c20a53166463c98e76aa01b08c6b8ad7cf11d5bad998a7245efaa5a474393  vmlinux.bin
9853a5e4f3bd7cf0414c567f78330d921b07d4b54603048917a5f45a94c7f6af  fw_payload.elf
```

These large generated images remain in the canonical SDK work tree and are
not copied here. The committed 197-line table was trained on the prior kernel
image. This checkpoint therefore proves binary integration, not performance;
the patched kernel must be traced with replay disabled and the table regenerated
before an enabled/disabled comparison with a byte-identical kernel.

The first forced disabled rebuild caught a build-control defect:
`platform-cppflags-y` affected linker-script preprocessing but not the C
compilation of `platform.c`. The switch now uses `platform-cflags-y`. The
corrected disabled payload has SHA-256
`a29cc6b86e7e5983e45ef2df753bb6f89d986aa44be550077b455d48203583a8`;
its `platform_early_init` contains no `0x7c1` writes and writes `(1 << 63)` to
`0x7c2`, configuring zero entries while clearing counters.

## Final replay-disabled image and simulator boot

The final resume build invalidates the generated DTS and DTB before invoking
the SDK, preventing a 64-MiB image from silently reusing an older 46-MiB DTB.
Its stable hashes are:

```text
c5b7c01a94bdfce558fe5606cc5ffbabff55b2f770b8bc575500df34a6decc99  ctxtsw_user_tiny
257f91d7c21c1e543ac56613a9c5a22a0a7d315d221c70e56d634e40b0f7f95b  vmlinux
bde7b74470c3c809b725c55f5b3bad3539f452930439e6821725d6e244a3ac2b  vmlinux.bin
e14d78f17f500c97b627d953fd18f5eef33e85b8b5fc8eb8c02ae766f7b902bb  blackparrot.dtb
2dceb08e7fb7af1f47e54ebc3f50de1c90e00dcd5c9620f78d388f65e00c6b76  fw_payload.elf / linux.riscv
f17554cc3d04b2ac4dcccb46b705f99ab59bb07e3ed8a366917f381c6d545cd6  linux-ctxtsw-tiny-init.nbf
```

The original simulator result was invalid: its host unconditionally raised the
debug interrupt, so the apparent retirement count came from a debug-mode loop
near `0x80000300`. After direct M-mode entry, OpenSBI still waited because the
sparse `--skip_zeros` NBF left its cold-boot lottery word randomized. The host
now supports `BSG_SKIP_DEBUG_ENTRY=1`, zeroes the simulated 128-MiB DRAM window,
and directly initializes guest DRAM writes in the actual RTL AXI RAM. The
1,878,595 direct writes take about 1.12 seconds; NBF configuration operations
remain serialized through the modeled interface. The historical bare-metal
path remains the default and its replay test still reaches guest and host PASS.

Run with `make -C linux-tests simulate-tiny-init`. In the accepted 600-second
replay-disabled run, OpenSBI printed its complete platform/domain/HART report,
selected `0x80200000` in S mode with DTB argument `0x82200000`, and the core
retired 920,381 instructions. The final state was privilege 1 with frontend PC
`0x810f0f90` and backend NPC `0x810f11f2`; after applying the kernel's
`0x80200000` physical load offset these map to `__pi_fdt_ro_probe_` and
`__pi_fdt_offset_ptr`. Thus the exact image reaches Linux early FDT parsing.
The bounded run does not claim console initialization, PID-1 completion, trace
capture, or any replay performance result.
