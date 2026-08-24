# BlackParrot Linux FPGA Baseline

This directory contains the first Linux compatibility gate for the hardware
context work. It deliberately tests only ordinary Linux boot and userspace
access to the core-wide physical-cycle CSR. It does not create or switch a
logical context.

## Recovered Linux image

The initial payload was recovered from Jack Humphries's January 2025 checkout:

```text
/home/jhumphri/zynq-parrot/cosim/black-parrot-example/verilator/linux.nbf
```

Recorded properties:

- size: 69,504,241 bytes / 1,878,493 NBF lines
- modification time: 2025-01-25 14:30:00 EST
- NBF SHA-256: `994bd900593ffb0eba6c6bdc0f413b321d755c538ecbe105f6b9f48c17d821d5`
- paired ELF SHA-256: `9fd4838f14959b10af3f4ac43147bb1912e84b3c2d4c345bf4e1a3439847eb69`
- embedded kernel: Linux 6.6.0, Buildroot GCC 13.2.0, OpenSBI payload
- command line: `console=hvc0 loglevel=8 root=/dev/ram0`
- highest observed NBF DRAM write: `0x818eb968`, within the PYNQ-Z2 runner's
  64 MiB allocation

Keep the 69 MiB payload under the ignored `riscv/linux/` artifact directory;
do not commit it to Git.

## Userspace physical-cycle probe

Build the static, libc-free RV64 Linux executable and its console upload
snippet with:

```bash
testing/linux/build_global_cycle_probe.sh
```

The probe uses Linux RISC-V `write` and `exit` syscalls directly, reads CSR
`0xCC0` 1,024 times, and succeeds only if the value never decreases and makes
forward progress. It prints a stable `[BP-LINUX-PASS]` marker on success.

After Linux reaches its BusyBox shell, paste the generated contents of:

```text
riscv/linux/bp_global_cycle_probe.upload.txt
```

BusyBox decodes the ELF into `/tmp`, executes it, and prints `PROBE_EXIT=0` on
success.

## Accepted FPGA identity

Use the routed package from FPGA job `20260823T182132Z-323abe7`:

- package: `logs/fpga/20260823T182132Z-323abe7/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64`
- package SHA-256: `3997df39a9c80116de20f278702e65d649a2b1731819643b2f4f54415e96411d`
- bitstream SHA-256: `803ea2933043d26619e703bcdb793fc2afc7898e18edc23d077000a26455569b`
- top-level build revision: `323abe7`
- BlackParrot revision: `d65c820f586ae03595f5145d95c8f193f8c8cf1e`
- routed timing: WNS `+1.283 ns`, TNS `0`

Stage the package and Linux NBF with `stage_pynq_artifacts.sh`, explicitly
reload the overlay, and run the Linux image with a `control-program` built
without `DRAM_TEST`. Linux is interactive and is not expected to emit the
bare-metal `CORE[0] PASS` marker.
