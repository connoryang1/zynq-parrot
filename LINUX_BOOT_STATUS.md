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
| 4 | OpenSBI initializes machine CSRs, timer/interrupt delegation, PMP, and its trap path. | **Pre-existing:** working; the AMOSWAP return test also passes on FPGA. |
| 5 | OpenSBI executes `mret`, transferring to the Linux kernel in supervisor mode (S-mode). | **Pre-existing:** working; the exact 2-thread/4-context simulator M-to-S smoke passes. |
| 6 | Linux performs early CPU, page-table, and trap initialization. | **Fixed here:** the context-switch frontend changes had interfered with normal fetch/refill paths; the scoped frontend/I-cache repairs are recorded by `c4654ec2` through `8ccfbd5`. |
| 7 | Linux runs its first delegated unaligned-load check (`check_unaligned_access_boot_cpu`). | **Fixed here, FPGA validation pending:** a stale synchronous-fault packet could be consumed twice while the frontend redirect drained, overwriting `sepc` with the trap-vector PC. |
| 8 | Linux mounts/uses the bundled initramfs and executes `/init`. | **Pre-existing baseline:** known to work and prints `Hello from rootFS`; **remaining:** prove it with the repaired image. |

## Repairs made during this work

| Repair | Why it was needed | Evidence / status |
| --- | --- | --- |
| Scope fast frontend behavior to actual context-switch commands | Normal instructions must not take a context-switch redirect path. | `c4654ec2` and follow-up frontend fixes; Linux progressed beyond the earlier silent OpenSBI/early-fetch failure. |
| Preserve normal I-cache refill/replay behavior | A context redirect must not abort or bypass an unrelated Linux refill. | `c9227ef2`, `c6c0c1d0`, `332f47a7`, and checkpoints through `8ccfbd5`. |
| Move context CSRs out of Linux's normal CSR use | Linux/OpenSBI must not accidentally access a context-switch CSR. | `80bd201a` / top-level `305a462`; targeted collision tests added. |
| Keep NBF, simulator, and bitstream dimensions identical | The deployed PYNQ configuration must retain two resident banks and four architectural contexts. | `3d2eb55`, `8c690a1`, `5c8ecd5`, `2654fac`; the static `e_bp_unicore_zynqparrot_cfg` encodes those dimensions directly. |
| Avoid the broken custom-configuration macro path | The custom aviary helper tests the literal macro parameter name rather than expanding it, silently falling back to BlackParrot's four-resident-thread default. | **Fixed in procedure:** do not use `e_bp_custom_cfg` for PYNQ. The canceled 2026-09-02 custom build synthesized at 70,752/53,200 LUTs (133%); the replacement static-config routed build is running. |
| Consume each synchronous fault once while its redirect drains | The same fault packet could remain visible after its trap redirect began, causing a second exception update to overwrite the correct EPC with the trap-vector PC. | Local clean-model gates pass: delegated S-mode misaligned-load recovery, M-mode unaligned-load recovery, M-to-S handoff, context-switch stage smoke, and a Linux-entry CSR/AMO/high-DRAM/text-stack proxy. Routed FPGA/Linux validation remains. |

## Remaining steps to `/init`

| Step | Required result |
| --- | --- |
| 1 | Commit the locally verified RTL and targeted tests as a checkpoint. |
| 2 | Run a routed PYNQ-Z2 Vivado build with `CFG=e_bp_unicore_zynqparrot_cfg`; its static package explicitly defines 2 resident banks and 4 contexts. Check fit, timing, and package integrity. |
| 3 | Load that package on the PYNQ-Z2 and rerun the exact trap test on hardware. |
| 4 | Boot the unchanged Linux NBF and require the rootfs banner plus `Run /init as init process` (the default image then powers off and reports PASS). |

## Notes

- A default Linux image is non-interactive: its `/init` runs the bundled test
  scripts and powers off.  Reaching `/init` is therefore visible in the host
  log even without a shell.
- A future Linux-resident context-switch C demo comes **after** this baseline
  boot is restored; it must use the same static 2-resident/4-context
  configuration.
