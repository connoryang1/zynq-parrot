This directory records the first isolated Linux scheduler-hook build for target user-data preview. It separates kernel compile and image evidence from simulator or FPGA acceptance, and keeps build-environment failures from being mistaken for RTL or kernel logic results.

# Same-mm Linux hook build

The source baseline is the canonical BlackParrot SDK Linux 6.6 Buildroot work tree, copied byte-for-byte to `/dev/shm/zp-linux-preview-20261024` so experiments cannot alter the canonical checkout. The initial three-object build passed for `kernel/sched/core.o`, `kernel/sys.o`, and `arch/riscv/kernel/process.o`. The first full `vmlinux` invocation failed before link because `CONFIG_INITRAMFS_SOURCE="${BR_BINARIES_DIR}/rootfs.cpio"` expanded an unset `BR_BINARIES_DIR` to `/rootfs.cpio`; the build log reports that missing prerequisite. The guardrail is to provide an explicit isolated `BR_BINARIES_DIR` containing a hash-matched copy of the current Buildroot rootfs, then rerun the full link. No kernel or hardware behavior is inferred from the failed invocation.

The original failed-build log was overwritten by the corrected-build capture; `missing-br-binaries-reproduction.log` reproduces the exact `/rootfs.cpio` prerequisite failure with the otherwise unchanged isolated tree. The rootfs source and isolated copy both hash to `7aeaccb952233bba19f586d0212c448bc4b217212ef868d0d10b47bd83603e27`. The corrected full-build command is:

```sh
env BR_BINARIES_DIR=/dev/shm/zp-linux-preview-images \
  make -C /dev/shm/zp-linux-preview-20261024 ARCH=riscv \
  CROSS_COMPILE=/home/coyang/zynq-parrot/import/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux- \
  -j8 vmlinux
```

The durable source is `linux-tests/patches/bp-same-mm-preview.patch`. A `patch -p1 --dry-run` on the exact canonical Linux source accepted all six files, and Linux `checkpatch.pl` reported zero code errors; its one warning concerns the standalone patch's absent commit description. `linux-tests/scheduler_data_preview.c` provides disabled, exact, and stale registration controls across 48 same-mm futex handoffs. Both static and dynamic RV64 builds pass `-Wall -Wextra -Werror`; the dynamic binary is 24 KiB and names the loader already present in the Buildroot rootfs. The existing `make -C linux-tests check-harness` gate passes all 11 tests after the Makefile registration. These are build facts only: no booted scheduler hint, timing improvement, or cross-mm safety is yet established.

The corrected `vmlinux` link and the incremental `Image` target passed. The linked `__schedule` disassembly contains the exact `csrs sstatus,a5; or zero,a4,1; csrc sstatus,a5` sequence on the SUM-clear path, and the kernel's reserved CSR collision gate passed for `0x800` through `0x807`. The embedded initramfs decompresses byte-for-byte to the isolated rootfs. Exact SHA-256 values are:

| Artifact | SHA-256 |
| --- | --- |
| Linux `vmlinux` | `1da10ce0db3f95ac041b13e1eb7e82072cb3258b04cc860526a0950f2582c8fd` |
| Linux `arch/riscv/boot/Image` | `4cd607007cbf367a047e1ab3485b54bb845b603f3988b1b7115ab6b4e55d58b6` |
| Static scheduler benchmark | `95b465f2319c398baeb1d64bc7f8a4fd6f6158dddbe7fbc32d1a68da5586374c` |
| Dynamic scheduler benchmark | `a1286d8a051b1ac8493e6d46aa0699826d53576942e03be7788254d2e08a9a79` |
| Source patch | `c5b21c0ac6cc11f83b0e89a400c50001e21a92574e06467f3b857b6071fac833` |

The benchmark must still be run with a booted kernel that contains this patch and the bounded-hint RTL. Its `wake`, `entry`, `load`, and `roundtrip` fields are distinct intervals; a faster `load` alone is not a whole-handoff speedup. The current hook is intentionally limited to `prev->mm == next->mm` and a DTLB-hit target address. Page-table generation, pending-hint cancellation, cross-mm translation, and task-footprint learning remain open before a general Linux feature.

`git diff --cached --check` flags unchanged context lines inside the newly tracked `.patch` file as if they were new source whitespace. The guardrail is to run that Git check on the other staged paths, then run the Linux patch checker and `patch -p1 --dry-run` on the patch itself; both latter checks passed for the exact patch recorded above.

## Isolated shell payload

The built kernel was stripped and converted to a flat payload binary, and `linux-tests/gendts_ctxtsw.py` generated a 64 MiB, 8 MHz DTB with `console=hvc0 loglevel=8 rdinit=/bin/sh`. A copy of the canonical OpenSBI build tree in `/dev/shm/zp-opensbi-preview-20261024` rebuilt `fw_payload.elf` using that exact binary and DTB; `opensbi-build.log` records the link. A byte search found one exact copy of each input in the ELF, and the OpenSBI `.text` reserved CSR scan passed. The normal NBF packaging flow used `objcopy -O verilog`, `@8` to `@0` address adjustment, `nbf.py --skip_zeros --config --ncpus 1`, and the 8 MHz timer patch (zero writes because the DTB already has that value).

| Isolated artifact | SHA-256 |
| --- | --- |
| Flat kernel binary | `4cd607007cbf367a047e1ab3485b54bb845b603f3988b1b7115ab6b4e55d58b6` |
| Shell DTB | `ea0bb8f5497d9aa05ecce8eaa14c834e1452958b32ed4d687e41b7ff7c416816` |
| OpenSBI payload | `a73a036a852767762a2fdb822758d49961d55387b77107347657767488cdcae3` |
| Shell NBF | `678e5723a9d799444d7c1d3d8fd26373563e0b470512126ffb1e03d8dcdd4c1d` |

The exact payload and NBF are retained locally at `logs/target-data-preview-linux-hook-20261024/fw_payload-shell.elf` and `linux-preview-shell.nbf`; these large binaries are ignored by Git. The shell rootfs contains the matching dynamic loader and libc, but it does not embed the benchmark, so an actual run still needs to transfer the 24 KiB dynamic executable or rebuild the initramfs.

The raw NBF CSR scanner returned status 1 for seven instruction-shaped data words. A first compound invocation followed it with `sha256sum` and masked that exit status; `raw-nbf-csr-scan.log` is the separate, status-checked reproduction. Six reported addresses map to kernel `.init.data` and one to `.rodata` after accounting for the 2 MiB payload load offset. The executable-section scans of both the linked kernel and OpenSBI passed, so these raw binary matches do not identify executed CSR instructions. The guardrail is to retain the raw scan result and classify every match against the linked ELF section map before calling an image collision-free. No simulator boot or FPGA run has been performed with this payload.

## Automatic-run simulator attempt

An isolated 48-trial rootfs appended the static benchmark and a PID-1 script that runs it and powers off. Its archive round-trip extraction matched both input files, the rebuilt kernel's embedded initramfs decompressed byte-for-byte to that archive, and an OpenSBI payload contained one exact copy of the rebuilt flat kernel and `rdinit=/init` DTB. The NBF hash is `9b0c96e34bcac50a0f081d5967bea42b65c38d53dfeeca058640b0d1fb223201`; this is a build artifact, not runtime evidence.

A fresh traced full-system Verilator model built in `/dev/shm/zp-preview-fullsim-20261024` using BlackParrot `31d6d461b`, static `e_bp_unicore_zynqparrot_prefetch5_cfg`, `BP_DCACHE_PREFETCH_ELS=5`, and `BP_PREFETCH_AXI_BYPASS`. Its native 120,000 ms target-runtime limit was present in the printed run command. During NBF load, the live simulator's file descriptor advanced only to roughly 0.52 MB of the 71 MB image after 2 minutes 39 seconds; the host loader applies DRAM records through simulated GP writes, and `ps.cpp: finished nbf load` never appeared. The target had not started. The run was terminated at that pre-boot stage, its simulator process exited, and its incomplete FST is not retained as waveform evidence. The guardrail is to measure NBF ingestion separately from guest runtime and use a verified direct simulator RAM initialization path before attempting another Linux boot; a native target-runtime limit alone cannot bound time spent in the host loader.

The first one-off RAM-file generator exited before creating output because Python rejects a backslash escape inside an f-string expression. The guardrail is to pad the byte word in a separate statement, then check the generated word count and sample values against the payload binary before rebuilding the simulator.

The first `cosim/v` copy landed under the design's existing `v/v` directory, so the attempted diagnostic patch path did not exist. The guardrail is to name the copied shared source directory explicitly (`cosim_v`) and pass that exact directory as `COSIM_VSRC_DIR` when rebuilding, leaving the design's own `v` sources intact.

The corrected diagnostic reads the exact OpenSBI flat payload into the simulator AXI RAM at time zero and skips only NBF DRAM writes in an isolated copy of the host program; it still applies the NBF's configuration writes. A clean traced rebuild passed, and before unfreeze the ordinary GP/AXI read path returned exact payload words at offsets `0`, `0x16000` (DTB), and `0x200000` (kernel). The runtime NBF hash was `9b0c96e34bcac50a0f081d5967bea42b65c38d53dfeeca058640b0d1fb223201` and the diagnostic simulator executable hash was `31bc30f2dbdbb46a401a1872b98a88c23959d70532dd7e0f21ec833767d08cc3`. `fast-auto-sim-run-command.log` is the closed host transcript; it printed `OpenSBI v1.4` and then exited through the native target limit after 132,124 host milliseconds, with about 6,528 normalized core cycles recorded. There was no Linux banner, benchmark marker, or clean guest completion; this is a host loader and OpenSBI-start result, not kernel scheduler evidence. The simulator child is gone. Its runtime-limited FST is not promoted as waveform evidence.

The automatic-run rootfs (`509b17bbc60cd4e40defd102b2cf14d519c12db0ff748edaf1a39c56a5499fc5`), OpenSBI payload (`a826644b925b99fe97b098af3a996fc82d896d8a80660d010c929be902a809b4`), and NBF are retained locally in this ignored log directory as `rootfs-auto.cpio`, `fw_payload-auto.elf`, and `linux-preview-auto.nbf`. `linux-tests/scheduler_preview_init.sh` is the checked-in source of the appended PID-1 script; `fast-sim-ram-diagnostic.patch` preserves the isolated host/testbench changes and passes `patch -p1 --dry-run` against this checkout. The exact automatic NBF's raw CSR scan reports eight candidate words: seven map to nonexecutable kernel `.init.data` and one to `.rodata`; the rebuilt kernel's executable-section CSR gate passes. That raw scan is a false positive for executed instructions, and its nonzero status remains recorded in `auto-raw-nbf-csr-scan.log`.

## Software boot and scheduler reachability

An isolated QEMU 4.2 package and dependencies were extracted under `/dev/shm/zp-preview-qemu-root`; no host packages were installed. A static copy of the benchmark replaced only the BlackParrot-specific cycle-counter read with `clock_gettime(CLOCK_MONOTONIC)`, so its values are QEMU software nanoseconds. The same PID-1 script ran it from an embedded rootfs. The first patched-kernel boot (`qemu-software-boot.log`, Image SHA-256 `31761b1da01aa82322844f02240d75eedda8d44c5b1dcdc665b78dedd9c70c3d`) completed all 48 mixed off/exact/stale futex handoffs, printed `SCHED_PREVIEW_SOFT PASS`, returned zero from init, and powered down.

For a reachability check, the isolated Linux build temporarily incremented a diagnostic counter when `riscv_bp_preview_next()` emitted a hint and exposed the count through a diagnostic-only `prctl`. Its mixed-mode boot (`qemu-count-boot.log`, Image SHA-256 `931584a4ce1e10e7ca7ee609861dd50eb14ab233b62329c4e9a361b4223450c6`) completed 48 handoffs and reported `SCHED_PREVIEW_ISSUED count=33`. An off-only binary with no registration, embedded in the same diagnostic kernel (`qemu-off-boot.log`, Image SHA-256 `9fbe027a520ec379622930d3170f8b14ed6fa17e5ea1cb32a7d6b3ae0014fd4e`), completed 48 handoffs and reported `count=0`. Both guests printed `PASS`, returned zero from init, and powered down with QEMU exit status zero. The off-only rootfs SHA-256 is `d0d3dc7aa8462ed4abd03265d076225ede5df7ed3f26fdc73ebdef4a341a70b9`. The four diagnostic source diffs are retained locally in this log directory; the build tree was restored byte-for-byte to the accepted source patch after the controls.

The QEMU command used `-machine virt -cpu rv64 -smp 1 -m 128M -nographic -monitor none -serial stdio -bios /dev/shm/zp-preview-qemu-root/usr/lib/riscv64-linux-gnu/opensbi/generic/fw_jump.bin -kernel <Image> -append 'console=ttyS0 rdinit=/init loglevel=7' -no-reboot`. The QEMU binary was `/dev/shm/zp-preview-qemu-root/usr/bin/qemu-system-riscv64`, with the extracted shared-library directories in `LD_LIBRARY_PATH`. QEMU treats the encoded hint as an architectural no-op; these boots validate the Linux software path and say nothing about BlackParrot memory-request acceptance, lead time, cache warming, or speedup.

The first restore command asked Make for both `vmlinux` and the literal `arch/riscv/boot/Image` path in one invocation. It relinked `vmlinux` but reported the path target was already done, leaving the old diagnostic Image in place. The guardrail is to invoke the kernel's `Image` target separately after `vmlinux` and hash the resulting file. That follow-up ran `OBJCOPY arch/riscv/boot/Image` successfully; the restored Image SHA-256 is `465a6c80b61de491a1d665f7ea0f927c11b79697d9a020224c97dbd87214cecd`. A reverse dry-run of the exact six-file patch against the restored source succeeded. This restored Image was not the one used in the QEMU controls above.
