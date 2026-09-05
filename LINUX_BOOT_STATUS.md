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
| 4 | OpenSBI initializes machine CSRs, timer/interrupt delegation, PMP, and its trap path. | **Fixed here:** PMP, absent HPM, and the six later optional capability CSRs are legal hardwired-zero WARL registers, so OpenSBI reports no unsupported capability without entering temporary-`mtvec` fault handling. **Physical proof:** the routed image passes `sbi_ecall_init` (`M8`), the late `sbi_init` midpoint (`M9`), and final PMP configuration (`Ma`). **Current proof:** the final-HSM path reaches the `atomic_cmpxchg` return, the expected-state branch, the subsequent `atomic_write` return, and the real `sbi_hart_switch_mode` entry, all through untouched firmware followed by a terminal `CORE PASS`. The original static e5ee trap probe was invalid because its NBF began at the target halfword: both a cold complete-line redirect and the exact archived line plus full HSM call prefix pass locally. |
| 5 | OpenSBI executes `mret`, transferring to the Linux kernel in supervisor mode (S-mode). | **Fixed/proved here:** a fresh, hash-verified current-image terminal at Linux physical entry `0x80200000` reaches `CORE PASS` after the complete untouched OpenSBI path. |
| 6 | Linux performs early CPU, page-table, and trap initialization. | **Current physical bracket:** guarded markers on the `05b1e786` routed image reach the first main-kernel routine (`0x80c05544`, `Me`) and return from its first five real helper calls (`0x80c05598`, `Mg`; `0x80c05610`, `Mh`; `0x80c05884`, `Mi`; `0x80c0590c`, `Mk`). The marker immediately before the next call (`0x80c059c0`) does not reach, confining the live path to its preceding 184-byte setup, including two explicit `ebreak` assertion paths. Thus the old 720-byte span is only a coarse landmark gap—not 720 bytes of proven dynamic execution—and the active pre-`satp` path is now being split at those assertions. |
| 7 | Linux allocates its two 128 KiB atomic DMA pools and continues device/kernel initialization. | **Fixed as a false boundary:** `initcall_debug` proves `dma_atomic_pool_init` returns 0 and many later initcalls complete. |
| 8 | Linux's RISC-V unaligned-access capability probe runs. | **Current physical bracket:** with the matched bounded legacy runner, a guarded terminal at `check_unaligned_access_boot_cpu` entry (`0x8020319e`) reaches `CORE[0] PASS` after 3,029,117 retired instructions, while its guarded return site (`0x802031ac`) reaches a clean 15-second target limit after 63,852,157 retired instructions. The active failure is therefore inside this initcall. Earlier three-byte-unaligned C.LD and trap-path gates remain useful but do not yet identify its exact dynamic boundary. |
| 9 | Linux mounts/uses the bundled initramfs and executes `/init`. | **Pre-existing baseline:** known to work and prints `Hello from rootFS`; **remaining:** prove it with the repaired image after step 8 is fixed. |

## Compatibility-endpoint preflight (2026-09-04)

The historical Linux-good seed is now paired with the seven compatibility
repairs at top-level `c12d52f8` and BlackParrot `faa584e9`; the archived Linux
NBF does not use custom CSRs `0x800`--`0x802`.  A clean traced static PYNQ
model built successfully, and its migrated CSR-isolation and six-switch
microbenchmark guests reached `CORE PASS` (12-cycle warm minimum). Their
terminal text includes reproducible non-ASCII prefixes after a switch, so this
is a console-path anomaly rather than a claimed full architectural proof; the
routed FPGA/Linux run remains the endpoint classification gate.

The static PYNQ-Z2 implementation has now routed successfully as job
`20260904T152933Z-c12d52f8`: WNS +6.506 ns, TNS 0, WHS +0.013 ns, 50,428/53,200
LUTs, and 46/140 BRAM tiles.  The hash-verified deployable package is
`ea8b3feafc76d35474ac3ed3fcc1dde83ac438c9e8caa017d2c670f73ac8b09`; the
extracted bitstream hash is `9f8c0c5f8f7a8d0ff61229deff843cf5f17e57cc68e5802679111fa319a2bd91`.
This proves fit and timing only—the next and still-required result is a fresh
serialized board run of the unchanged archived Linux NBF through `/init`.

The first fresh run used the verified package/bit/NBF identities above and
cleanly reached its 180-second target limit after 150,007,078 retired
instructions (IPC 0.133339), without an OpenSBI/Linux console line or `/init`.
It is valid evidence that this reconstructed zero-feature endpoint is still
incompatible with Linux; it is not evidence against any one of the 113 later
SRAM-context feature commits. The replay is paused while this endpoint is
localized and repaired.

### Board-runner incident (2026-09-04)

The initial detached serialized runner disappeared before it created a board
log or completion status, leaving only its lock directory; no `control-program`
process was present. Cause is not yet confirmed, so it is recorded as a
board-session infrastructure failure rather than RTL evidence. The board was
power-cycled, PYNQ readiness was re-established, the overlay was reloaded and
hash-checked, and the retained foreground transcript above was used for the
valid Linux result; do not infer a test result from a missing-status launch.

The historical collateral only defines the default `prog.nbf` target. A
named-NBF invocation therefore fails before simulation; generate the selected
program with `make -B prog.nbf PROG=<name>` and then run it serially. This
prevents a stale program image from being mistaken for the selected smoke.

### Minimal-overlay local gate (2026-09-04)

The clean traced static model for top-level `380377a3` / BlackParrot `7f41bca9`
passes the migrated CSR-isolation guest (`CORE PASS`), proving that the
non-colliding `0x800`--`0x802` interface still creates and resumes an isolated
second context. The later `mt_ctxtsw_microbench` reaches all three initial
switch measurements but does not finish on this zero-feature historical
implementation; it relies on frontend handoff mechanics introduced later in
the 113-commit replay interval and is not evidence that the CSR-only overlay
is defective.

The candidate lacks the newer native target-runtime argument in `ps.cpp`, so
the nonterminal local run was stopped explicitly and its child simulator was
verified absent before continuing. Do not reuse that trace or treat a
host-side interruption as a performance or Linux result. Historical candidate
wrappers should gain the bounded target-runtime control before any future
expected-stall diagnostic; normal candidate gates remain serialized.

### Minimal-overlay FPGA classification (2026-09-04)

The CSR-only candidate was routed as job `20260904T163508Z-380377a3` with
top-level `380377a3` and BlackParrot `7f41bca9`. It fits the static PYNQ-Z2
configuration: WNS +4.580 ns, TNS 0, WHS +0.022 ns, THS 0, 50,324/53,200
LUTs, 20,018 registers, 46/140 BRAM tiles, and 11 DSPs. The verified package
SHA-256 is `7463ea1a524c700cde18f9f1aa3a6bc0fa2d0ae4a9e16009be3b47a750473997`,
the extracted bitstream SHA-256 is
`4d756d075667cd15a8d51d1b86796ba8e3683dbd040dcf19ddb7f2fc0f93afbf`, and the
unchanged Linux NBF is `994bd900593ffb0eba6c6bdc0f413b321d755c538ecbe105f6b9f48c17d821d5`.

After a readiness-gated reload, the exact NBF loaded completely and a single
foreground retained run reached its clean 180,001 ms target limit after
150,006,825 retired instructions at IPC 0.133339, with no OpenSBI/Linux
console output or `/init`. This is a valid fresh-board negative result for
the CSR-only migration, not a result for any of the 113 feature commits. The
board was power-cycled immediately afterward; wait for readiness and reload
before any follow-up probe.

### CSR-only OpenSBI classification (2026-09-04)

An OpenSBI-only prefix of the same Linux image retained all configuration
records and 17,142 firmware writes below `0x80200000` while omitting 1,861,337
Linux-payload writes. On the freshly reloaded CSR-only candidate it reached a
clean 5,000 ms target limit at 4,173,746 retired instructions and IPC 0.133536
with no console output. This matches the full-image 0.133339-IPC signature and
proves the active minimal-endpoint failure is inside M-mode OpenSBI startup,
not the Linux payload or `/init`; the board was power-cycled after the bounded
probe.

A fresh, hash-verified terminal probe replacing the Linux handoff instruction
at physical `0x80200000` with marker `M1` also reached its clean 15,000 ms
limit with no marker after 12,506,848 retired instructions (IPC 0.133402).
This independently proves that the CSR-only candidate stalls before OpenSBI's
`mret` to Linux, so future localization stays within the OpenSBI prefix. The
board was power-cycled immediately after this bounded result.

An attempted control using the archived threaded runner (`76db…`) is
inconclusive: on this candidate overlay its initial reset CSR read was the
invalid value `-1207959552` and it never reached NBF configuration. The board
was immediately power-cycled and the candidate runner will be restored; this
is a host/bitstream protocol mismatch, not evidence for or against the CSR
migration.

### Exact historical-baseline control (2026-09-04)

The exact historical top-level/RTL pair previously recorded as Linux-good was
rebuilt without the CSR migration: top `2a1f88347681e3ccc77d3eb3665ca23b6b8ae6c8`
with BlackParrot `ce328a77536764187cd5174c44289fee05383ae8`. It routed and
packaged as `0d7073d7f78a34bddb45b78036523c84bae974a1bc46f16bf774aa457a7beae3`
(bitstream `32060f933c2120d227b961b7c642955d399a9f270335912f3fdedc0496d59d7f`),
meeting timing with WNS +5.104 ns, TNS 0, WHS +0.037 ns, 50,662/53,200 LUTs,
and 46/140 BRAM tiles. The same Linux NBF
`994bd900593ffb0eba6c6bdc0f413b321d755c538ecbe105f6b9f48c17d821d5` was staged
atomically, the normal reviewed board runner was SHA-pinned to
`fd2f0291a9021c19f3ebd2d825d22a7dfe9d22ae33fbbeae3fde4a800d26bd2b`, and the
overlay was confirmed operating before launch.

Despite that exact source control, the retained 180,000-ms run was silent
after `bsg_zynq_pl: start()` and stopped at 150,005,765 retired instructions,
IPC 0.133339, without an OpenSBI/Linux console line or `/init`. It is nearly
identical to the CSR-only candidate's 150,006,825-retirement result. Therefore
the candidate failure cannot be attributed to the CSR address migration: the
currently rebuilt historical pair is not reproducing its older Linux-success
transcript under the present host/board deployment environment. The board was
power-cycled immediately after this valid bounded run; do not run another
overlay/test until the PYNQ readiness gate passes.

The old runner (`76db…`) includes the compiled `Zero-ing DRAM` path, whereas
the ordinary current runner (`fd2f…`) does not. To eliminate that material
workflow difference, a current-source runner was rebuilt with every duplicate
definition forced to `FREE_DRAM=1 ZERO_DRAM=1` (runner
`00fb07f60d1473da8a42ec96f61ece8ff24c54ad2dd732b6d076ad29c7221f60`) and
verified to contain the zeroing string. On a fresh reload of the exact same
baseline bitstream, it zeroed all 64 MiB and completed NBF loading, but still
reached the controlled 180-second limit with 150,004,374 retired instructions
at IPC 0.133338 and no console or `/init`. DRAM clearing is therefore
necessary historical-flow parity but not sufficient to restore the old boot.
The ordinary reviewed runner was hash-verified and restored before the required
post-timeout board power cycle.

### Preserved pre-feature artifact control (2026-09-04)

The board retains the original `bp_unicore-linux-baseline.tar.xz.b64` package
(SHA-256 `c211216c16e936b12c81a2f96c8e033ebfeb810c083c8fd3f7c3cda93e1c9a93`)
and its matched historical runner `76db506ed632b3e68eb3201fe010b2d06e5161a2cfbe1823b71a2fbb50513be8`.
The extracted historical bitstream is `d45f7e3e73b88a3eab2573415f3ff9ea050877e1246eebd5b145de5ea851cd5a`.
After an atomic runner selection and readiness-gated overlay load, that exact
pair booted the same Linux NBF through kernel initialization and `/init`, ran
the bundled rootfs CPU/memory tests, powered down, and produced `CORE[0] PASS`.
The terminal measurements were 321,255,862 retired instructions, IPC 0.512492,
and 100.297 seconds wall time.

This proves that the physical board, image, DRAM initialization, and historical
host protocol are functional. It is an archived **pre-feature** artifact
control, not a replacement for the missing saved artifact of the later
`2a1f8834` / `ce328a77` compatibility seed; the newly rebuilt seed still
silently fails with either current-runner DRAM policy. Do not use this success
to absolve the current rebuild or to attribute its failure to the CSR migration.

### Reproducible pre-feature source control (2026-09-04)

The recovered pre-feature source pair, top `4015d0f21db0dd78922cb1419e4034b810c0f1ed`
and BlackParrot `08edfb479c7b5d55d665a63464785044c6b4cd35`, was rebuilt with its
recursive historical submodules and generated PLIC collateral. It routed and
packaged as `93b3a3ce50b90aadb36026ab6c115740dcfcefaf082be16c49324365e9d50d42`
(bitstream `16c4e22994141f9bf04d8668ae95e831f031b2c32460f92c99da1735e00cd03d`),
with WNS 0.000 ns, TNS 0, WHS +0.021 ns, 39,310 LUTs, and 49.5 BRAM tiles.

The current board runner is a newer pybind/PYNQ polling implementation and is
not protocol-compatible with this historical design. A safe legacy runner was
therefore rebuilt from the matched source without `DRAM_TEST`, using
`FREE_DRAM=1 ZERO_DRAM=1` (SHA-256
`b774f71d2ca5c8b92fdc1acae04f87d3e006f0c7e3207b4c904f7b0f5f85674f`). On a
fresh overlay load, the exact archived Linux NBF booted through OpenSBI, Linux,
and `Run /init as init process`, completed the bundled rootfs tests and
poweroff, then returned `CORE[0] PASS` at 321,577,541 retired instructions and
IPC 0.525264. This confirms the prior source-rebuild silent loop was a
host-runner protocol mismatch, not a demonstrated RTL regression.

### Current full-stack classification with the matched runner (2026-09-04)

The source-matched runner also classified the routed full context-switch stack,
so this conclusion is not extrapolated from the historical control. The exact
BlackParrot `1c42e9f2` package
`73342c3cd4adfa0084a0b8cf37d022710280d5a3eddd5a47337b12a57ce98fc5`
(bitstream `8ee250aa172c03bffe52f29cf4ac5ad916a48f8ad9b3e6aeccbb3db029d6eadb`)
was staged, re-extracted, and loaded with the archived Linux NBF (SHA-256
`994bd900593ffb0eba6c6bdc0f413b321d755c538ecbe105f6b9f48c17d821d5`). The
NBF collision scan passed for CSRs `0x800`--`0x802` and the pinned legacy
runner was `b774f71d2ca5c8b92fdc1acae04f87d3e006f0c7e3207b4c904f7b0f5f85674f`.

This run reached normal OpenSBI handoff and Linux output through both atomic
DMA-pool lines (`1.331154` and `1.342125` kernel seconds), but its transcript
then remained unchanged for more than two wall-clock minutes while the target
continued to run. It did not reach `/init` or `CORE[0] PASS`. Therefore the
legacy runner mismatch explains the recovered pre-feature false regression but
does **not** explain the current full-stack post-DMA Linux stall. The board was
power-cycled after the observed stall; the retained board transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260904T195409Z-289907.log`.

## Repairs made during this work

| Repair | Why it was needed | Evidence / status |
| --- | --- | --- |
| Scope fast frontend behavior to actual context-switch commands | Normal instructions must not take a context-switch redirect path. | `c4654ec2` and follow-up frontend fixes; Linux progressed beyond the earlier silent OpenSBI/early-fetch failure. |
| Preserve normal I-cache refill/replay behavior | A context redirect must not abort or bypass an unrelated Linux refill. | `c9227ef2`, `c6c0c1d0`, `332f47a7`, and checkpoints through `8ccfbd5`. |
| Move context CSRs out of Linux's normal CSR use | Linux/OpenSBI must not accidentally access a context-switch CSR. | `80bd201a` / top-level `305a462`; targeted collision tests added. |
| Keep NBF, simulator, and bitstream dimensions identical | The deployed PYNQ configuration must retain two resident banks and four architectural contexts. | `3d2eb55`, `8c690a1`, `5c8ecd5`, `2654fac`; the static `e_bp_unicore_zynqparrot_cfg` encodes those dimensions directly. |
| Avoid the broken custom-configuration macro path | The custom aviary helper tests the literal macro parameter name rather than expanding it, silently falling back to BlackParrot's four-resident-thread default. | **Fixed in procedure:** do not use `e_bp_custom_cfg` for PYNQ. The canceled 2026-09-02 custom build synthesized at 70,752/53,200 LUTs (133%); the replacement static-config routed build is running. |
| Consume each synchronous fault once while its redirect drains | The same fault packet could remain visible after its trap redirect began, causing a second exception update to overwrite the correct EPC with the trap-vector PC. | The current 19-line CSR/scheduler delta passes the routed-FPGA M-mode ECALL trap test. It remains under review for nested synchronous-fault cases, but is not the leading explanation for the current post-DMA Linux stop. |
| Report unsupported PMP CSRs as legal zero-valued WARL registers | OpenSBI probes PMP during `sbi_hart_init`; trapping on an absent PMP CSR diverts into the debug path before normal firmware handling. | **Fixed locally and routed.** A clean traced regression verifies nonzero writes to `pmpcfg0` and `pmpaddr0` are accepted and read back as zero, and an independent full-system smoke still passes. The fresh 150-second FPGA Linux run made forward architectural progress but did not reach console output, so it does not yet prove complete OpenSBI recovery. |

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

## Linux unaligned-access reproducer (2026-09-02)

`mt_smode_jiffies_unaligned_probe_test` is a durable static-full-model
regression for the relevant privilege and timer sequence.  It passed after a
clean rebuild with `TRACE=1` on the production RTL (no temporary `$display`
instrumentation): `QRMABECD`, `CORE PASS`.

Two early versions of this test **must not** be treated as RTL failures:

- enabling `mie.MTIE` while reset-time `mtimecmp` was zero delivered a real
  M-mode timer interrupt before the intended M→S handoff, correctly changing
  the return privilege to M;
- the test's temporary timer handler mistakenly loaded `0x304` (the MIE CSR
  address) rather than CLINT `mtime` at `0x0030bff8`, causing its own
  misaligned-load trap.

The corrected test masks `mtimecmp` before enabling MTIE and uses the CLINT
addresses. It does **not** prove the separate FPGA Linux initcall has been
fixed; it rules out this joined architectural sequence as the explanation.

## Exact Linux unaligned-initcall probes (2026-09-02)

The actual Linux 6.6 routine is now available from the matching `vmlinux`:
`check_unaligned_access_boot_cpu` enters at linked `0xffffffff8000319e`,
calls `check_unaligned_access`, performs an initial unaligned word copy, waits
for `jiffies`, then measures unaligned word and byte copies before returning.
The current FPGA transcript proves entry: it prints `calling
check_unaligned_access_boot_cpu+0x0/0x18 @ 1` and no matching return.

`tools/make_linux_unaligned_probe_set.sh <linux.nbf> <outdir>` generates
nine guarded probes at the physical payload addresses `0x8020xxxx` for the
entry, each copy boundary, both jiffies waits, and the initcall return.  It
uses SBI console plus SBI system-reset, not the physical host-MMIO window, so
the marker remains usable after Linux has enabled SATP.  This corrects an
earlier mistake: the old "entry" patch at `0x80203198` was actually in the
late result-reporting tail of `check_unaligned_access`, not at the initcall
entry.  No result from that older patch may be used to localize the stall.

A first high-Sv39 candidate was rejected because it applied the high alias a
second time to a PC-relative symbol, selecting the wrong top-level page-table
entry.  The corrected high-alias gate now passes; it remains a bounded
translation/trap-path gate, not a substitute for Linux's real page tables.

Each terminal SBI probe exits its host runner cleanly, but the following
experiment must still start from a power-cycled board and a freshly reloaded
scoped overlay.  The serial runner lock must be clear first; a follow-on run
without this recovery has been observed to retire zero instructions or stall
before OpenSBI and is not valid evidence.

The repair-stack bisection must therefore retain only candidates that pass the
local privilege/CSR/context-switch gate set **and** demonstrate a fresh FPGA
Linux boot.  Do not infer either result from a different revision's package,
board transcript, or generic smoke test.

## Local repair-screen boundary (2026-09-02)

All results below use isolated historical RTL worktrees, the static
two-resident/four-context configuration, `TRACE=1`, and freshly regenerated
NBF collateral through `make -C testing run-full-<test>`.

| RTL checkpoint | Linux-entry proxy | SATP-mode filter | Interpretation |
| --- | --- | --- | --- |
| `19aa50ad` | pass | fail: Sv48/Sv57 writes persisted | The completed original feature stack is not clean against the direct SATP regression, even though it passes the early Linux proxy. |
| `453185ec` | pass | fail: Sv48/Sv57 writes persisted | The earlier FE/DTLB/CSR-seed repairs do not implement the SATP restriction. |
| `51bbb0e8` | pass | pass | Earliest checkpoint proven clean by the current two-test local matrix. |

The Linux-entry proxy and the SATP filter are complementary.  The former
exercises M-to-S entry, SIE/SIP manipulation, high-DRAM AMO, BSS-like memory,
and a high-address fetch; the latter directly checks a failing unsupported-SATP
write.  Neither is a full-Linux equivalent, and neither validates the later
stale synchronous-fault repairs.  Do not call `51bbb0e8` Linux-boot proven
until a fresh FPGA Linux run reaches `/init`.

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
| The first bounded DRAM-state-dump runner launches exited before starting `control-program`. | One positional child argument shifted the image into the directory slot (`cd: opensbi-hsm-call-dump.nbf: Not a directory`); later, an empty optional argument caused `foreground=$7` to fail under `set -u`. Retained empty logs proved neither trial touched the target. | The runner encodes all optional remote arguments with an explicit `-` sentinel and offers foreground mode for short probes; long runs retain the `setsid --wait` detached path. |
| DRAM state-dump experiments reached OpenSBI and passed but always read zero words, including a written sentinel through both GP1 and direct CMA reads. | Earlier attempts also used wrong `lui()` operands, but the corrected low OpenSBI scratch address still produced no observable data. Therefore no captured value is trustworthy. | Retire the DRAM-dump path for now. Validate the isolated host-character reporter first with a known `x0=0` control probe before attempting any live-register capture. |
| The new host-character state reporter might itself have fabricated or lost dynamic values. | At the exact final-HSM call PC, its isolated trampoline printed the expected known-value control `MoX0N` and then the five live low nibbles `MpA8B2S8P0RCN`; both ended in `CORE PASS`. | Treat this transport as the valid capture mechanism. Use bounded nibble batches and retain the transcript; do not interpret previous DRAM zero dumps as register state. |
| A subsequent state-dump launch failed before loading its NBF with `allocate_dram(): Assertion 'virtual_ptr != NULL' failed`. | The PYNQ CMA allocator had no usable contiguous 64 MiB block; the retained transcript ended before `beginning config`, so it says nothing about OpenSBI or RTL. | Power-cycle the board, wait for the full PYNQ-ready gate, then reload the verified overlay before any follow-up run; do not retry allocation in the same PL/host state. |
| A direct full-system simulator `make run` could execute a previous `prog.nbf` after a new test source compiled. | The full simulator’s program collateral is not reliably keyed by `PROG`; an apparent rerun initially reproduced the old test. | Use `make -C testing run-full-<test> TRACE=1`, which refreshes `prog.riscv`, `prog.mem`, and `prog.nbf` before the run. |
| Fresh candidate builds used Verilator's single-job default and hid a broken implicit build target behind an already-existing model. | A clean historical worktree could not construct `obj_dir/V...`; an interrupted serial model build took minutes. | Use the concrete `obj_dir/V$(TB_MODULE)` rule and default `--build-jobs $(nproc)` in isolated candidate worktrees. Keep runtime tests serialized. |
| Forwarding `NUM_THREADS`/`NUM_CONTEXTS` through the generic test harness selected the broken dynamic `e_bp_custom_cfg` rather than the deployable static PYNQ configuration. | The attempted build expanded to an incompatible four-resident-thread design. | The full-system helper fixes `CFG=e_bp_unicore_zynqparrot_cfg`; do not pass dynamic dimensions to it. |
| The lightweight simulator cannot validate CLINT timer behavior. | It has no `bp_me_clint_slice`, so `mtime`/MTIP tests can hang without proving an RTL failure. | Use the static full Zynq model for timer, privilege, SATP, and Linux-adjacent tests. |
| A new C diagnostic is not automatically buildable merely because its source exists in `testing/`. | `run-full-mt_mstatus_mie_write_test` initially had no generated SDK target. | Register every test in `EXPERIMENTAL_TESTS` (or the appropriate maintained list) before invoking the generic test rule. |
| A waveform was interpreted after a later full-model test had run. | The full simulator reuses and overwrites `cosim/black-parrot-example/verilator/dump.fst`; the observed S-mode trap state belonged to the later misaligned-load test, not the earlier timer test. | After every traced failure, archive/copy the FST under a test-specific name and decode it before launching any other simulator test. Never infer a result from an unlabelled shared `dump.fst`. |
| An injected NBF state reporter produced a plausible A1 nibble without proving the reporter itself was correct. | The large table's branch consumed a not-yet-settled value; even an `x0` control printed `e`, and later padding changed the NBF enough to overwrite unrelated code. | Use a compact arithmetic reporter only; validate it at the exact PC with `x0` and require expected output plus `CORE[0] PASS` before recording a live state value. |
| A local C.LD test matched only the instruction, alignment, privilege, and SATP mode. | `mt_smode_sv39_c_ld_alignment3_test` passes in both the minimal and static PYNQ-style traced models with Sv39 and `a1[3:0]=3`, taking delegated cause 4 and recovering; its full-model waveform is `logs/waveforms/mt_smode_sv39_c_ld_alignment3_test-static-full-20260902.fst` (SHA-256 `58354e68…b5ae9`). | Treat this as a negative discriminator: capture the actual Linux trap-vector/delegation path before changing RTL; do not call the local test an exact reproduction merely because the load boundary matches. |
| The first exact-state local test skipped the faulting C.LD, while Linux emulates it in S-mode. | `mt_smode_sv39_linux_c_ld_emulation_test` reproduces Linux's C.LD instruction re-fetch, eight Sv39 byte loads from `stval`, saved-`a4` update, `sepc += 2`, and `sret`; it passes in both the traced minimal and static PYNQ-style models (`MRP`, `CORE PASS`). | This is the final synthetic gate for this boundary. If Linux still stops here, instrument the actual Linux vector/handler state rather than adding another approximation or changing RTL speculatively. |
| A first high-kernel-alias analogue used a simplified 1 GiB Sv39 leaf, unlike Linux's real multi-level kernel mapping. | Its initial load page fault was a test bug: a high alias was added twice to a PC-relative `source_words` reference, producing canonical VA `0xfffffffe80005dc3`. The corrected `mt_smode_sv39_linux_c_ld_emulation_highva_test` passes the traced static PYNQ-style model (`MRP`, `CORE PASS`) with high kernel-text `sepc`/`stvec` and the configured `0xfffffffe…` direct-map data alias. | Keep it experimental: it now proves both relevant high address classes, C.LD emulation, and SRET, but capture real Linux `sepc`/`stvec` state before treating it as an exact Linux reproducer. |
| A host-side `timeout` killed its parent test make but left the child simulator in the same process group running, producing an incomplete FST. | The unbounded minimal high-VA run had to be signaled manually and its FST could not be opened. | For expected-hang diagnostics, set the simulator's native `TARGET_RUNTIME_MS` and verify no runner process remains before launching another test; archive only the cleanly closed trace. |
| The historical CSR-only endpoint's context microbenchmark did not terminate after completing its three warm measurements. | The clean `380377a3` / `7f41bca9` model passes CSR isolation, but this zero-feature implementation predates the frontend handoff that the later benchmark needs; it also lacks the native target-runtime control. | Treat CSR isolation as the migration gate at this depth. Do not run a nonterminal benchmark until that feature dependency exists; add bounded runtime support to an isolated historical wrapper first and verify no simulator child remains after any stop. |
| `FULL_SIM_RUNTIME_MS=1` did not bound an exploratory Sv39 run on midpoint 51. | The historical `Makefile.design` always emits only `+c_args=prog.nbf`, and its `ps.cpp` accepts no runtime argument; the run was interrupted, all children were verified absent, and its trace is invalid. | Inspect the candidate's runner interface before requesting a native limit. Do not run an expected-stall diagnostic on historical collateral until bounded-runtime support is applied and rebuilt separately from RTL. |
| A detached serialized Linux launch vanished before creating its status, even though its board lock remained. | The retained log was empty and no `control-program` process existed, so the target had not begun; a foreground launch immediately afterward started the target and produced the valid retained 180-second result. | On this PYNQ image, use the serial helper's foreground mode for long Linux boots unless detached-run persistence has been revalidated; reclaim only its dead lock after confirming no direct runner exists. |
| A foreground bounded run executed correctly but `run_pynq_serial.sh` reported a launch failure after the target stopped. | The remote foreground process returns the target's expected nonzero timeout status; the helper previously rejected that status before reading its already-written `RUNNER_STARTED_PID` and retained completion transcript. | Once a valid atomic start line exists, the helper now polls and returns the retained target status; only a nonzero remote result without a start line is a launch failure. |
| A first CE Linux-entry terminal probe was launched without a target-owned runtime limit. | It loaded and ran but did not terminate during a short observation, so the board was power-cycled before any new run; its missing marker is not used as RTL evidence. | Every expected-stall or terminal-probe run must pass `PYNQ_CONTROL_PROGRAM_TIMEOUT_MS` through the serial helper; never use a host-side observation window as a target result. |
| Focused MTIP test initially reported pending timer state without handler entry. | Its NBF remained in debug mode; `mgie` deliberately masks interrupts there even after MSTATUS.MIE reads back set. After adding the boot-ROM-equivalent `dret`, `mt_timer_trap_naked_test` passes MTIP → handler → `mret` in the traced static full model. | Every focused interrupt test must execute the same `dret` handoff as the boot ROM before enabling interrupts. Do not use the original debug-mode failure as Linux evidence. |
| A fresh isolated replay worktree could not initialize `import/black-parrot`. | Its recorded submodule URL is an intentional local source snapshot, but Git's default security policy rejected the `file` transport before any candidate RTL was checked out; after that override, the historical pinned BaseJump commit was no longer advertised by its upstream remote. | Initialize with the scoped `protocol.file.allow=always` override, then seed the exact nested BaseJump object from an existing local checkout rather than advancing it; keep both workarounds local to the immutable replay snapshot. |
| The modern context-CSR migration did not cherry-pick onto the `ce328a77536` Linux-good seed. | All eight conflicts are only the old context-CSR constants and port names: the historical implementation predates later context-state restructuring, so a textual cherry-pick would falsely import unrelated later RTL. | Resolve this overlay semantically as a verified `0x081`--`0x083` to `0x800`--`0x802` interface migration, record the resulting candidate commit, and retain the exact-NBF collision scan as the acceptance check. |
| The disposable historical BlackParrot clone rejected its first overlay checkpoint commit. | It has no local `user.name` or `user.email`, unlike the primary developer checkout; the Git rejection occurred before any commit was created. | Set the existing project identity only in the isolated candidate repository before its first replay commit, never by changing a global Git identity. |
| A replay command named an invalid full revision, and a later gitlink update repeated the same manual-abbreviation mistake. | The first Git command failed before touching its candidate; the later index accepted a nonexistent object, but an immediate `ls-tree`/submodule comparison exposed it before verification and the unverified branch was amended to the exact `git rev-parse` result. | Never type or manually extend a full object ID: capture it directly from `git rev-parse`, compare `ls-tree` with the materialized submodule, and require a clean top-level status before building or pushing. |
| The isolated `ce328a77536` candidate's first full-model gate had no executable model. | `make -C testing run-full-mt_amo_swap_return_test` stopped at `No rule to make target 'obj_dir/Vbsg_nonsynth_zynq_testbench'`; it did not run guest code or reuse a stale candidate executable. | In a fresh replay worktree, build the concrete full-model executable explicitly before the first `run-full-*` gate, then keep all candidate runtime gates serialized. |
| The historical full-model Makefile also lacks a resolvable explicit executable rule. | Both the generic `run-full-*` target and `make obj_dir/Vbsg_nonsynth_zynq_testbench` fail before Verilator starts, despite a `%/V$(TB_MODULE)` pattern in the file. | Do not mistake this make-resolution failure for RTL evidence; use a repaired, isolated build wrapper or a routed FPGA build for this historical candidate, and keep any wrapper correction out of the functional overlay. |
| A replay top-level tree taken from current `05b1e786` is not source-list compatible with BlackParrot `ce328a77536`. | After repairing its Make target, the fresh model stopped before Verilator because the current collateral requires `bp_be_context_mem.sv`, a later file absent from the CE tree. | Build the CE compatibility overlay from its historically paired top-level revision `2a1f883`, not from current host tooling; retain newer checks only as external read-only helpers. |
| A session rollover removed the disposable `/tmp/zp-ce-required-*` replay worktrees while retaining their Git worktree metadata. | The candidate path and in-progress model were gone at restart, but top-level commits `8ca0c424` and `cc1310a3` remain addressable. | Keep replay source worktrees outside `/tmp` (or push them before a long build), and prune only stale worktree metadata before recreating a candidate. |
| The reconstructed CSR-address replay used a shell-wide replacement rather than the required patch workflow. | The committed diff is the intended nine `0x081`--`0x083` address substitutions in the isolated `bp_be_csr.sv`, but its editing mechanism was not auditable through `apply_patch`. | Do not repeat the shortcut: retain this reviewed commit as-is, and use `apply_patch` for every subsequent source or documentation edit. |
| A noninteractive replay `cherry-pick --continue` invoked an unavailable terminal editor. | The resolved stale-`mret` change was staged, but Git stopped before committing and made no RTL decision. | Set `GIT_EDITOR=true` only for the continuation of a reviewed conflict resolution; never leave an interactive editor invocation in an unattended command. |
| A historical candidate invoked its own relative `codex-skills` path, which does not exist in that old checkout. | The CSR-collision scan failed before reading the NBF; rerunning the same scan through the primary checkout's absolute skill-script path passed. | Run reusable workflow tools from `/home/coyang/zynq-parrot/codex-skills`, while passing historical candidate paths as explicit inputs. |
| The first repaired-midpoint model attempts began before its exact top-level submodules were materialized. | Make reported missing targets before Verilator started; after initializing `import/basejump_stl` and `import/black-parrot-subsystems` at their pinned revisions, the clean 12-worker traced build and Linux-entry gate both passed. | Initialize and verify all exact top-level and nested submodules before interpreting any historical build failure as RTL evidence. |
| A standalone BlackParrot replay path was mistaken for a separately initialized nested BaseJump repository. | Running a nested checkout from that placeholder changed the standalone BlackParrot worktree itself to BaseJump content; all candidate source was already committed, and restoring branch `linux-feature-repaired-midpoint-98` recovered it without loss. | Never manipulate `external/basejump_stl` directly in a standalone replay clone; materialize and verify the real nested submodule through its paired top-level historical checkout. |
| Repaired commit 101's first Vivado run failed during elaboration before testing the RTL. | BlackParrot's pinned BaseJump wrapper accepted `ram_style_p`, but the historical top-level still supplied an older duplicate `bsg_mem_1r1w_sync`; Vivado reported that named parameter as nonexistent. | Verify both top-level and nested memory-wrapper signatures before synthesis; candidate `b7133b51` aligns the top BaseJump gitlink to `6cd7d830`, and replacement job `20260905T061726Z-b7133b51` is the valid run. |
| A historical candidate build found an initialized but empty `import/black-parrot-subsystems` checkout. | An earlier multi-submodule update aborted when the candidate BlackParrot object was unavailable from its remote, leaving the sibling worktree populated as deletions; the failure was setup damage, not RTL evidence. | Before each historical build, require a clean submodule status and test for its required source files; repair an incomplete checkout with a forced exact-gitlink submodule update before compiling. |
| Shared `install` and `riscv` links were briefly created inside a candidate's BlackParrot submodule instead of its top-level checkout. | The setup command used the nested repository as its working directory; both untracked links were detected immediately, removed explicitly, and recreated at the top level before any build. | Use absolute destination paths for shared candidate links and verify both top-level and submodule status before starting a gate. |
| Repaired commit 77 initially had no resolvable Verilator model target. | Make's implicit-rule search reached the missing nested `external/HardFloat/source/compareRecFN.v`; the separately initialized top-level `import/HardFloat` was not the path consumed by BlackParrot. No compiler or simulator ran before the failure. | Materialize and verify both BlackParrot nested gitlinks, `external/basejump_stl` and `external/HardFloat`, before every historical candidate build. |
| A commit-53 smoke command unexpectedly began regenerating the whole model and was interrupted. | The executable had been built while the submodule temporarily pointed at a provisional UCE fix, then the source was restored to commit 53; Make correctly detected the revision mismatch, so no smoke guest ran. The incomplete objects were cleaned immediately. | Never reuse a model across a submodule revision change, even for a one-line experiment; keep each revision in its own worktree or perform a clean rebuild before runtime validation. |
| Candidate 77's first background route failed before Vivado started. | The source seed had exact nested BaseJump and HardFloat checkouts but not its pinned `external/bedrock`; the launcher rejected the incomplete seed before synthesis. | The shared readiness check now verifies all three nested gitlinks before launch: BaseJump, HardFloat, and BedRock. |
| Commit 61's first local run unexpectedly printed Hello World. | The lower-level Make flow regenerated `prog.nbf` from stale `prog.riscv`, changing its SHA-256 before simulation; the mismatch was detected before any gate result was recorded. | Pin and verify the intended NBF after collateral generation, then invoke the already-built simulator directly so Make cannot replace the guest between the hash gate and execution. |
