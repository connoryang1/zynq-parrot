# Linux boot status

This is the living, plain-language status record for booting Linux on the
PYNQ-Z2 BlackParrot image.  Update it whenever a boot-stage result changes.
The payload is a single NBF image: it loads OpenSBI in M-mode, which starts
the Linux kernel in S-mode; Linux then starts the root filesystem's `/init`.

Status labels: **pre-existing** means it was known to work before this
context-switch work; **fixed here** names a repair authored during this work;
**current** means not yet proved on the repaired FPGA image.

## Boot path and status

| Step | What happens | Status |
| --- | --- | --- |
| 1 | The ARM host resets the PYNQ programmable logic and loads the BlackParrot bitstream. | **Pre-existing:** working. |
| 2 | The host allocates/zeros 64 MiB of board DRAM and loads the Linux NBF into it. | **Pre-existing:** working. |
| 3 | The host releases BlackParrot reset; its boot ROM enters the NBF-provided OpenSBI firmware in machine mode (M-mode). | **Pre-existing:** working. |
| 4 | OpenSBI initializes machine CSRs, timer/interrupt delegation, PMP, and its trap path. | **Pre-existing:** working. On the current routed FPGA image, M-mode synchronous traps, timer traps, AMOSWAP, and AMOADD all pass. |
| 5 | OpenSBI executes `mret`, transferring to the Linux kernel in supervisor mode (S-mode). | **Pre-existing:** working; the exact 2-thread/4-context simulator M-to-S smoke passes. |
| 6 | Linux performs early CPU, page-table, and trap initialization. | **Fixed here / FPGA verified:** the scoped frontend/I-cache repairs let the current image pass these stages, enable Sv39, initialize interrupts/RCU, and reach the early DMA allocator. |
| 7 | Linux allocates its two 128 KiB atomic DMA pools and continues device/kernel initialization. | **Current blocker:** the unchanged Linux image prints both successful pool-allocation messages, then makes no further console progress. The stop is after kernel time 1.34 s; it is not yet attributed to one RTL line. |
| 8 | Linux mounts/uses the bundled initramfs and executes `/init`. | **Pre-existing baseline:** known to work and prints `Hello from rootFS`; **remaining:** prove it with the repaired image after step 7 is fixed. |

## Repairs made during this work

| Repair | Why it was needed | Evidence / status |
| --- | --- | --- |
| Scope fast frontend behavior to actual context-switch commands | Normal instructions must not take a context-switch redirect path. | `c4654ec2` and follow-up frontend fixes; Linux progressed beyond the earlier silent OpenSBI/early-fetch failure. |
| Preserve normal I-cache refill/replay behavior | A context redirect must not abort or bypass an unrelated Linux refill. | `c9227ef2`, `c6c0c1d0`, `332f47a7`, and checkpoints through `8ccfbd5`. |
| Move context CSRs out of Linux's normal CSR use | Linux/OpenSBI must not accidentally access a context-switch CSR. | `80bd201a` / top-level `305a462`; targeted collision tests added. |
| Keep NBF, simulator, and bitstream dimensions identical | The deployed PYNQ configuration must retain two resident banks and four architectural contexts. | `3d2eb55`, `8c690a1`, `5c8ecd5`, `2654fac`; the static `e_bp_unicore_zynqparrot_cfg` encodes those dimensions directly. |
| Avoid the broken custom-configuration macro path | The custom aviary helper tests the literal macro parameter name rather than expanding it, silently falling back to BlackParrot's four-resident-thread default. | **Fixed in procedure:** do not use `e_bp_custom_cfg` for PYNQ. The canceled 2026-09-02 custom build synthesized at 70,752/53,200 LUTs (133%); the replacement static-config routed build is running. |
| Consume each synchronous fault once while its redirect drains | The same fault packet could remain visible after its trap redirect began, causing a second exception update to overwrite the correct EPC with the trap-vector PC. | The current 19-line CSR/scheduler delta passes the routed-FPGA M-mode ECALL trap test. It remains under review for nested synchronous-fault cases, but is not the leading explanation for the current post-DMA Linux stop. |

## Remaining steps to `/init`

| Step | Required result |
| --- | --- |
| 1 | Localize the post-DMA stall with translation-aware software markers or an equally narrow architectural test; do not infer a source location from a post-SATP physical patch alone. |
| 2 | Continue the parallel RTL audit of the 40-file context-switch range, prioritizing globally active CSR, redirect, exception, atomic, and return paths over context-switch-only logic. |
| 3 | Make one isolated RTL correction only after a reproduction identifies it; rerun the focused FPGA gate, then a fresh-overlay unchanged Linux boot. |
| 4 | Require the rootfs banner plus `Run /init as init process` (the default image then powers off and reports PASS), then add and run the Linux-resident context-switch C demonstration. |

## Notes

- A default Linux image is non-interactive: its `/init` runs the bundled test
  scripts and powers off.  Reaching `/init` is therefore visible in the host
  log even without a shell.
- A future Linux-resident context-switch C demo comes **after** this baseline
  boot is restored; it must use the same static 2-resident/4-context
  configuration.
