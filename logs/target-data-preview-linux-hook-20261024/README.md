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
