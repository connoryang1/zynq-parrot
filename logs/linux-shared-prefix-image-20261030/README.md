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
