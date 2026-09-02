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
| 7 | Linux allocates its two 128 KiB atomic DMA pools and continues device/kernel initialization. | **Fixed as a false boundary:** `initcall_debug` proves `dma_atomic_pool_init` returns 0 and many later initcalls complete. |
| 8 | Linux's RISC-V unaligned-access capability probe runs. | **Current blocker / FPGA verified:** `check_unaligned_access_boot_cpu` prints its initcall entry but never its return. Linux 6.6’s exact routine first busy-waits for `jiffies` to change; however, the corrected full-model machine-timer test executes the boot-ROM-equivalent `dret` and passes MTIP → handler → `mret`, and the delegated S-mode misaligned-load test also passes. Reproduce the Linux-specific state/sequence or bisect from a current integrated Linux-good revision before changing RTL. |
| 9 | Linux mounts/uses the bundled initramfs and executes `/init`. | **Pre-existing baseline:** known to work and prints `Hello from rootFS`; **remaining:** prove it with the repaired image after step 8 is fixed. |

## Repairs made during this work

| Repair | Why it was needed | Evidence / status |
| --- | --- | --- |
| Scope fast frontend behavior to actual context-switch commands | Normal instructions must not take a context-switch redirect path. | `c4654ec2` and follow-up frontend fixes; Linux progressed beyond the earlier silent OpenSBI/early-fetch failure. |
| Preserve normal I-cache refill/replay behavior | A context redirect must not abort or bypass an unrelated Linux refill. | `c9227ef2`, `c6c0c1d0`, `332f47a7`, and checkpoints through `8ccfbd5`. |
| Move context CSRs out of Linux's normal CSR use | Linux/OpenSBI must not accidentally access a context-switch CSR. | `80bd201a` / top-level `305a462`; targeted collision tests added. |
| Keep NBF, simulator, and bitstream dimensions identical | The deployed PYNQ configuration must retain two resident banks and four architectural contexts. | `3d2eb55`, `8c690a1`, `5c8ecd5`, `2654fac`; the static `e_bp_unicore_zynqparrot_cfg` encodes those dimensions directly. |
| Avoid the broken custom-configuration macro path | The custom aviary helper tests the literal macro parameter name rather than expanding it, silently falling back to BlackParrot's four-resident-thread default. | **Fixed in procedure:** do not use `e_bp_custom_cfg` for PYNQ. The canceled 2026-09-02 custom build synthesized at 70,752/53,200 LUTs (133%); the replacement static-config routed build is running. |
| Consume each synchronous fault once while its redirect drains | The same fault packet could remain visible after its trap redirect began, causing a second exception update to overwrite the correct EPC with the trap-vector PC. | The current 19-line CSR/scheduler delta passes the routed-FPGA M-mode ECALL trap test. It remains under review for nested synchronous-fault cases, but is not the leading explanation for the current post-DMA Linux stop. |

## Evidence status of late repair commits

The late repair commits are a **candidate compatibility stack**, not a proven
set of independent Linux fixes.  Keep this distinction when selecting the
next bisect checkpoint: a general smoke test is a regression guard, not proof
that it exercises the originally suspected Linux sequence.

| Commit | Suspected surface | Exact pre-fix reproducer? | Current evidence | Confidence |
| --- | --- | --- | --- | --- |
| `332f47a7` | I-cache refill arbitration | No | Routed package built; no revision-attributable Linux trial. | speculative |
| `b5ef69f0` | Normal FE resume request | No | Routed package built; no revision-attributable Linux trial. | speculative |
| `78837f53` | DTLB-fill FE replay | No captured replay | Build attempts only; no retained package/Linux trial. | speculative |
| `453185ec` | Context seed CSR image | No | Context/smoke gates only, not a seed-image failure. | speculative |
| `51bbb0e8` | Unsupported SATP-mode write | Yes | The SATP-mode-filter and S-mode Sv39 gates pass locally and on FPGA. | directly supported |
| `c51f2001` | Repeated stale synchronous fault | Partial trace observation | M-mode ECALL trap passes; nested/repeated-fault sequence is still untested. | partial |
| `1c42e9f2` | Stale `mret` ordering | No exact reproducer | Related privilege/timer gates pass; no Linux boot after this exact revision. | speculative |

The repair-stack bisection must therefore retain only candidates that pass the
local privilege/CSR/context-switch gate set **and** demonstrate a fresh FPGA
Linux boot.  Do not infer either result from a different revision's package,
board transcript, or generic smoke test.

## Repair-stack FPGA bisection

Use `tools/run_linux_repair_checkpoint.sh <checkpoint>` for the immutable
routed checkpoints `19aa`, `332`, `b5ef`, `453`, and `51bb`.  The helper
refuses to stage any package while a `control-program` runner is active,
records both package and NBF hashes, reloads the scoped overlay, and retains a
per-checkpoint transcript.  It accepts only `Run /init as init process` plus
`CORE[0] PASS` as a Linux-boot pass.  The current `1c42e9f2` package is
supplied explicitly through `LINUX_REPAIR_CURRENT_PACKAGE` until it is
promoted into `logs/fpga/`.

This answers a precise first question: which prefix of the late repair stack
is compatible with the **already complete** SRAM-backed context-switch RTL.
It is not a valid binary search of the earlier 125 feature commits, because
the late repair patch conflicts with those older code shapes.  A later
feature-history search must backport the repair *semantics* at each selected
checkpoint and record each manual resolution as a separate experiment.

## Remaining steps to `/init`

| Step | Required result |
| --- | --- |
| 1 | Compare the two proven `7331fbd0` FE constraints with the current integrated RTL and establish the latest Linux-good/current-bad range. |
| 2 | Reproduce the next Linux-specific state/sequence within that range, then make one isolated RTL correction only after its local gate fails. |
| 3 | Make one isolated RTL correction only after the misaligned-access reproduction identifies it; rerun the focused FPGA gate, then a fresh-overlay unchanged Linux boot. |
| 4 | Require the rootfs banner plus `Run /init as init process` (the default image then powers off and reports PASS), then add and run the Linux-resident context-switch C demonstration. |

## Notes

- A default Linux image is non-interactive: its `/init` runs the bundled test
  scripts and powers off.  Reaching `/init` is therefore visible in the host
  log even without a shell.
- A future Linux-resident context-switch C demo comes **after** this baseline
  boot is restored; it must use the same static 2-resident/4-context
  configuration.

## Verification and workflow lessons

Record each item here when it changes how evidence must be gathered.  A
suspected RTL cause stays labelled *suspected* until a focused reproduction
rules out the alternatives.

| Symptom / mistake | Evidence | Guardrail now required |
| --- | --- | --- |
| Two board `control-program` runs could overlap after an SSH timeout or delayed launch. | They share PL DRAM, host GP ports, terminal state, and `run.log`; either run can make the other’s result meaningless. | Use `run_pynq_serial.sh` only. It takes a board-side atomic lock, rejects a pre-existing direct runner, and retains a per-run transcript/status. |
| A direct full-system simulator `make run` could execute a previous `prog.nbf` after a new test source compiled. | The full simulator’s program collateral is not reliably keyed by `PROG`; an apparent rerun initially reproduced the old test. | Use `make -C testing run-full-<test> TRACE=1`, which refreshes `prog.riscv`, `prog.mem`, and `prog.nbf` before the run. |
| Forwarding `NUM_THREADS`/`NUM_CONTEXTS` through the generic test harness selected the broken dynamic `e_bp_custom_cfg` rather than the deployable static PYNQ configuration. | The attempted build expanded to an incompatible four-resident-thread design. | The full-system helper fixes `CFG=e_bp_unicore_zynqparrot_cfg`; do not pass dynamic dimensions to it. |
| The lightweight simulator cannot validate CLINT timer behavior. | It has no `bp_me_clint_slice`, so `mtime`/MTIP tests can hang without proving an RTL failure. | Use the static full Zynq model for timer, privilege, SATP, and Linux-adjacent tests. |
| A new C diagnostic is not automatically buildable merely because its source exists in `testing/`. | `run-full-mt_mstatus_mie_write_test` initially had no generated SDK target. | Register every test in `EXPERIMENTAL_TESTS` (or the appropriate maintained list) before invoking the generic test rule. |
| A waveform was interpreted after a later full-model test had run. | The full simulator reuses and overwrites `cosim/black-parrot-example/verilator/dump.fst`; the observed S-mode trap state belonged to the later misaligned-load test, not the earlier timer test. | After every traced failure, archive/copy the FST under a test-specific name and decode it before launching any other simulator test. Never infer a result from an unlabelled shared `dump.fst`. |
| Focused MTIP test initially reported pending timer state without handler entry. | Its NBF remained in debug mode; `mgie` deliberately masks interrupts there even after MSTATUS.MIE reads back set. After adding the boot-ROM-equivalent `dret`, `mt_timer_trap_naked_test` passes MTIP → handler → `mret` in the traced static full model. | Every focused interrupt test must execute the same `dret` handoff as the boot ROM before enabling interrupts. Do not use the original debug-mode failure as Linux evidence. |
