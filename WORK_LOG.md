# Engineering Work Log

> Purpose: This file is the concise progress ledger for restoring Linux boot on the SRAM-backed context-switch design. Each significant row identifies the exact BlackParrot checkpoint, how many of the 113 feature commits have been classified, and whether work is reproducing, fixing, locally verifying, or FPGA-verifying. Detailed traces, commands, and routine failures live in the linked status documents and retained logs.

## How to use this log

Add only major milestones: confirmed root causes, definitive fixes or reverts, meaningful FPGA/Linux outcomes, material tooling changes, and commits or pushes. Every new row must state the feature-progress count and current phase; keep it to one or two sentences. Keep routine probes, repeated negative results, and fine-grained marker splits in retained transcripts or the detailed status documents.

## Current replay scoreboard

The feature sequence has 113 commits after the Linux-good `7331fbd0958` seed through the SRAM-backed feature tip `8708eff7`. A feature commit counts as verified only after its candidate has passed local gates, routed on the PYNQ-Z2, and either booted through `/init` or produced a reproducible fresh-board non-`/init` result.

| Feature commits verified | Feature commits remaining | Compatibility overlay | Current checkpoint / phase | Next significant proof |
| ---: | ---: | --- | --- | --- |
| 0 / 113 | 113 | Minimal 1 / 7 semantic classified bad | top `380377a3` + BlackParrot `7f41bca9`; **compatibility endpoint diagnosis** | Localize why the mandatory non-colliding CSR migration changes the pre-console firmware path, then make one CE-shaped repair before replaying any feature commit. |

## 2026-09-04 — feature replay restart

- **Compatibility-endpoint reconstruction (0/113):** the exact Linux-good `ce328a77536` seed is being rebuilt in a persistent BlackParrot worktree after temporary replay worktrees were reclaimed. The custom-CSR address migration and unsupported-SATP filter are restored as `7f41bca9` and `384c23c0`; five compatibility fixes remain before any endpoint can be classified.

- **Compatibility overlay complete (0/113):** all seven compatibility semantics now form pushed BlackParrot branch `ce-required-overlay` at `faa584e9`. The phase changes from **making RTL fixes** to **verifying**: no feature commits are yet classified, and the next result must be a clean exact-pair local/FPGA endpoint run.

- **Exact candidate ready (0/113):** pushed top-level branch `ce-overlay-linux-verify` at `70579bfb` pairs the historical Linux-good top revision with overlay `faa584e9`; readiness checks pass and the archived Linux NBF is collision-free at `0x800`--`0x802`. Phase: **local verification**; 113 feature commits remain until this zero-feature endpoint receives a routed `/init` classification.

- **Local model ready (0/113):** the exact compatibility candidate completed a clean traced static-PYNQ Verilator build (322.7 seconds); no guest test has yet classified it, so 113 commits remain and the phase is **local smoke verification** before routed FPGA/Linux work.

- **Local context gate (0/113):** after migrating the two smoke programs to the reserved `0x800`--`0x802` interface (`c12d52f8`), the traced static model passed CSR isolation and the six-switch microbenchmark (warm minimum 12 cycles/switch). The endpoint is now **FPGA verifying**; all 113 feature commits remain unclassified until its routed Linux result.

- **Routed endpoint (0/113):** the committed static PYNQ-Z2 endpoint (`c12d52f8` / `faa584e9`) now routes and packages successfully as `ea8b3fea…8b09` (bitstream `9f8c0c5f…2bd91`), with WNS +6.506 ns, TNS 0, WHS +0.013 ns, 50,428/53,200 LUTs, and 46/140 BRAM tiles. Phase: **Linux board verification**; all 113 feature commits remain unclassified until a fresh serialized archived-Linux run reaches `/init` or establishes a reproducible non-`/init` result.

- **Endpoint Linux result (0/113):** the fresh hash-verified archived-Linux run on that routed endpoint reached its clean 180-second target limit after 150,007,078 retired instructions (IPC 0.133339), without console output or `/init`. This is **compatibility endpoint repair**, not a feature result: all 113 commits remain unclassified and replay is suspended until the zero-feature baseline is repaired.

- **Minimal endpoint repair (0/113):** pushed candidate `380377a3` pairs the Linux-good historical top revision with BlackParrot `7f41bca9`, retaining only the mandatory custom-CSR migration and removing six unproven late compatibility changes. Phase: **local verification**; 113 feature commits remain because only a fresh routed `/init` result can establish this zero-feature baseline.

- **Minimal local migration gate (0/113):** `380377a3` / `7f41bca9` completed a clean traced static build, passes migrated CSR isolation (`CORE PASS`), and the exact archived Linux NBF is collision-free for `0x800`--`0x802`. Its later microbenchmark is nonterminal at this historical depth because it requires a frontend handoff introduced within the feature sequence, so phase advances to **FPGA verifying** on the CSR-only endpoint; all 113 feature commits remain unclassified.

- **Minimal endpoint classified bad (0/113):** routed static PYNQ-Z2 candidate `380377a3` / `7f41bca9` fits (WNS +4.580 ns, WHS +0.022 ns, 50,324 LUTs, 46 BRAM) but its freshly staged exact Linux run reached the clean 180-second limit with 150,006,825 retired instructions at IPC 0.133339 and no console or `/init`. This isolates the current regression to the mandatory CSR-only compatibility change rather than the six removed overlays; 113 feature commits remain unclassified and phase is **compatibility endpoint diagnosis**.

- **Firmware boundary confirmed (0/113):** a fresh 5-second OpenSBI-only prefix on the same CSR-only endpoint matched the full image's 0.133-IPC silent loop (4,173,746 retired instructions), proving the active regression is in M-mode firmware startup before Linux is fetched. The phase remains **compatibility endpoint diagnosis** with all 113 feature commits unclassified.

## 2026-09-02 — current investigation

- **Project baseline and regression:** root `69b939b` with BlackParrot `c39ee12b735` booted the archived Linux image through `/init` and `CORE[0] PASS`; BlackParrot `7331fbd0958` is the first known historical Linux regression. The bisect evidence is in [`LINUX_BOOT_BISECT.md`](LINUX_BOOT_BISECT.md).

- **Context-switch repair direction:** the current repair stack confines frontend fast paths to real context-switch commands and moves custom context CSRs away from ordinary Linux CSR traffic. The branch is at pushed top-level revision `a6c6d5e`; its BlackParrot submodule is `1c42e9f2`. Detailed confidence and remaining uncertainty are in [`LINUX_BOOT_STATUS.md`](LINUX_BOOT_STATUS.md).

- **Local architectural coverage:** clean static-model tests pass for delegated unaligned recovery, SBI timer setup/disarm, M-to-S timer forwarding, the S-mode timer handler, and read-only context-CSR access without a spurious switch. The recurring post-`BSG PASS` Verilator DPI assertion is a known host teardown issue, not a guest failure.

- **Fast local Linux harness:** the static PYNQ-style model now supports a simulation-only DRAM preload for the 1.88-million-record Linux NBF. It was checked against the FPGA-proven toolchain smoke image; correcting sparse-memory initialization also confirmed the OpenSBI boot-lottery AMOSWAP behavior, eliminating that suspected cause.

- **Current local Linux result:** the archived image progresses through reset, relocation, OpenSBI initialization, and its extensive `sbi_hart_init` CSR/PMP probing. A 60-second observation showed continued architectural progress rather than a demonstrated trap or deadlock, so local simulation is useful for localization but is not yet a complete Linux-boot gate.

- **FPGA readiness:** the PYNQ-Z2 was power-cycled and is reachable. The next definitive run will reload an immutable routed checkpoint and execute the exact archived Linux NBF through the guarded serialized board helpers; the result will be recorded here.

- **FPGA checkpoint result:** after a hash-verified reload, the latest available immutable checkpoint (`51bbb0e8`, package SHA-256 `f2f1d5d4…fa099`) reached OpenSBI and Linux through early memory, SMP, timer, and DMA initialization, then stopped after atomic-DMA-pool setup at about 1.34 kernel seconds. The board was power-cycled to clear the privileged runner and is reachable again; the complete `1c42e9f2` stack still needs its own routed package for a definitive current-version run.

- **Linux boot progress:** the complete current repair stack (`1c42e9f2`) now has a hash-verified routed package (`73342c3c…8fc5`, bitstream `8ee250aa…eadb`) with WNS +2.698 ns and zero timing failures. Its fresh FPGA run reached the same atomic-DMA-pool boundary at 1.341 s, then remained silent beyond the boot window; the retained transcript confirms this is the current full-stack result, not an older-checkpoint inference.

- **New reproduction:** a one-shot NBF replacing only the exact `check_unaligned_access_boot_cpu` entry instruction completed with `CORE[0] PASS` after 3.0M instructions on the current FPGA image. This proves the repaired stack reaches the known post-DMA initcall and lets subsequent probes narrow the remaining unaligned-access path without RTL edits or Vivado runs.

- **Reporter validation:** the original A1 table reporter is invalid: its branch had a data-dependency hazard, so even an `x0` control printed the wrong nibble. A compact same-PC reporter now correctly emits `0MeN` and `CORE[0] PASS`; corrected A1/SATP captures must replace the old value before any local reproduction is trusted.

- **Live unaligned-load state:** after the compact reporter control passed, the exact Linux helper reported `3McN` and `8MdN`, each with `CORE[0] PASS`, establishing `a1[3:0]=3` and `satp.MODE=8` (Sv39) at the first failing `c.ld`. The earlier `e` value is retired; the next step is an exact-state traced local reproduction.

- **Linux-shaped trap-emulation gate:** the new state-faithful C.LD handler test passed in both local simulator models. It exercises Linux's instruction re-fetch, bytewise emulation, saved-register update, and SRET, so further progress requires live Linux trap-path evidence rather than more synthetic variants.

- **High virtual-address gate:** a first high-Sv39 fault was a local test bug—the high alias had been added twice to a PC-relative source reference. The corrected full PYNQ-style trace (`MRP`, `CORE PASS`) now covers high kernel-text/vector execution plus Linux's separate `0xfffffffe…` direct-map data alias, Linux-shaped C.LD emulation, and SRET; real page-table topology remains to be captured.

- **Exact-state local discriminator:** `mt_smode_sv39_c_ld_alignment3_test` passes in both minimal and static PYNQ-style traced models with S-mode, Sv39, the same `c.ld`, and three-byte alignment, taking delegated cause 4 and recovering. Those conditions alone therefore do not reproduce Linux's later stop; the remaining state to capture is the real trap-vector/delegation path.

- **Reproduction boundary enforced:** high-Sv39 tests remain evidence only when their setup and boundary agree with live FPGA captures. The passing high-alias gate is retained as an experimental translation/trap-path regression rather than claimed as a complete Linux reproducer.

- **Compatibility-bisect midpoint:** the first `a9ee78ab1ea` routed attempt exposed a real FE/UCE combinational I-cache-refill loop and was stopped before route completion. The minimal acyclic overlay now keeps redirects pending through refill completion; after restoring the midpoint's exact nested BaseJump revision, its clean traced static model passed both the toolchain smoke and Linux-entry CSR/AMO/BSS gate. A fresh routed build is the next Linux-classification step.

- **Definitive historical CSR collision:** the exact archived Linux NBF contains nine instructions using the midpoint's legacy context CSR range (`0x081`--`0x083`). The corrected midpoint route was therefore stopped before implementation completed: that revision cannot receive a meaningful Linux result until its interface is migrated to the reserved `0x800`--`0x802` range.

- **Compatibility fixes carried forward:** the isolated historical overlay now applies both required semantics: I-cache refill is kept acyclic through a context redirect, and all custom context CSRs move from Linux-colliding `0x081`--`0x083` to `0x800`--`0x802`. Its exact-NBF preflight is collision-free and its Linux-entry gate passes; the early historical prefix still lacks the later context frontend handoff, so it is not a feature-acceptance point.

- **Current-package revalidation:** the immutable `1c42e9f2` package and archived Linux NBF were re-staged and hash-verified. Two bounded fresh runs stopped after OpenSBI's delegation report before a Linux banner, unlike older transcripts for the same hashes; a subsequent handoff probe could not run because the PYNQ became unreachable after overlay loading, so this is recorded as a board-state/transport interruption rather than a new RTL regression conclusion.

- **PYNQ readiness correction:** an FPGA-manager `operating` status by itself did not prove the ARM GP0/GP1 control path usable: the next runner read an invalid reset CSR and blocked at its first GP1 timer access. The FPGA loader now records the manager state, and the remaining deployment gate is a bounded PS↔PL control-path check before trusting a Linux or probe result.

- **Linux handoff proved:** after a stable reload, the guarded one-shot NBF replacing physical `0x80200000` completed with `CORE[0] PASS`. OpenSBI therefore reaches its Linux S-mode handoff address on the current bitstream; earlier pre-banner stalls were invalid board-readiness runs, not an `mret` regression.

- **Early-entry probe correction:** the apparent boundary at `0x80201138` was not an instruction boundary—it is the upper half of the 32-bit `addi sp,sp,-306` beginning at `0x80201136`. The probe corrupted that ADDI; the generator now rejects such sites, and a valid probe at `0x8020113a` reaches OpenSBI's Linux handoff path and passes on FPGA after 933,568 retired instructions. This removes the alleged early-entry regression.

- **Early-entry instruction gates:** the exact AMOADD alias/branch sequence passes a clean static traced simulation, and the exact high-address `auipc sp; addi sp,sp,-306` pair passes on the routed FPGA (`CORE[0] PASS`). These gates remain useful regressions, but neither identifies a current Linux blocker.

- **Fresh unmodified Linux classification:** the exact archived Linux NBF (SHA-256 `994bd900…821d5`) reaches the complete OpenSBI handoff on the current routed FPGA and retires 1,727,368 instructions, but has no Linux console or terminal PASS before the bounded runner stops it. Linux is therefore still not end-to-end verified; the remaining failure is downstream of the corrected early-entry probes.

- **Exact M-mode unaligned-trap gate:** the FPGA now passes `mt_smode_sv39_c_ld_mmode_trap_test` (`ABMRP`, `CORE[0] PASS`, 18,079 retired instructions). It exactly matches the live Linux load's S-mode, Sv39, three-byte alignment, and non-delegated load-misalignment route, ruling out a generic M-mode entry/return failure; remaining investigation must preserve the surrounding OpenSBI/Linux handler state.

- **OpenSBI MPRV and high-address gates:** both the exact OpenSBI-style temporary-`mtvec`/MPRV instruction-plus-eight-byte-load sequence (`ABMIBP`) and a high-Sv39 non-delegated C.LD trap (`ABMRP`) pass on the routed FPGA. A 60-second terminal replacement at the candidate Linux C.LD did not reach that PC after 4.24M retired instructions, so it is not yet valid to call that instruction the current live blocker; resume localization from an earlier confirmed current-image milestone.

- **Firmware-boundary correction:** under the clean validated board runner, the full Linux NBF and an OpenSBI-only prefix both reproduce the same 4.17M-retirement, 0.133-IPC loop. Exact FPGA stop probes prove OpenSBI's boot-hart AMOSWAP, relocation, BSS clearing, platform setup, and warm-start entry all complete; the active boundary is now inside `sbi_init`, not the earlier Linux unaligned-access candidate.

- **Probe-tool hardening:** `make_linux_milestone_nbf.py` now distinguishes a genuine 32-bit-instruction upper-half overwrite from a valid compressed instruction following a 32-bit instruction. `make_opensbi_prefix_nbf.py` provides a reusable, hashable firmware-only image for this classification without changing RTL.

- **OpenSBI initializer progress:** guarded FPGA terminal probes show that current `sbi_init`, `sbi_scratch_init`, `sbi_heap_init`, and `sbi_domain_init` are all reached and return successfully on the static `1c42e9f2` image. The reusable 17,156-line OpenSBI prefix reproduces the full-image post-`sbi_scratch_init` result, so subsequent firmware localization no longer reloads the Linux payload.

- **PMP bootstrap correction:** waveform evidence identified OpenSBI's `csrw pmpcfg0` capability probe as an illegal-instruction/debug-path boundary. The RTL now exposes the unimplemented PMP CSRs as legal hardwired-zero WARL registers—truthfully reporting zero PMP entries rather than storing unenforced protection state—and both the clean traced PMP regression and independent toolchain smoke pass locally; routed FPGA/Linux confirmation is pending.

- **Routed PMP checkpoint:** the PMP correction (`02c7f844` / BlackParrot `b77e8a20`) routed on the static PYNQ-Z2 configuration with WNS +1.663 ns, TNS 0, and a verified deployable package (`73134ee2…fb13`); resource use is effectively full at 140/140 BRAM tiles and 96.38% LUTs. A clean 150-second FPGA run of the exact archived Linux NBF retired 125,006,524 instructions but emitted no OpenSBI/Linux console text before its controlled timeout, so the PMP fix is necessary local progress but not a complete boot repair.

- **Board-readiness guard:** a PYNQ power cycle can expose SSH before its own boot service is ready, and loading the overlay in that window produced invalid, unrecoverable probe attempts. The FPGA skill now provides `wait_pynq_ready.sh`, which requires the system `Startup finished` milestone and 90 seconds of uptime before a reload.

- **OpenSBI PMP repair proved on hardware:** three fresh routed-FPGA terminal markers reached `sbi_hart_init`, completed `csrw pmpcfg0`, and reached its zero-PMP fallback. This turns the PMP correction from a local compatibility fix into hardware evidence and narrows the remaining pre-console fault to the following unsupported performance-counter capability probe.

- **OpenSBI HPM root cause and repair:** a fourth fresh FPGA marker proved the first `csrr mhpmcounter3` never returns through OpenSBI's temporary trap vector, exactly identifying the next bootstrap loop. BlackParrot commit `bbb2e072` makes all optional machine HPM counter/event CSRs legal zero-WARL; its clean traced full-model regression and independent FPGA-toolchain smoke pass, and routed fit is in progress from top-level checkpoint `c704100c`.

- **HPM repair proved on hardware:** fresh terminal probes now complete both the first HPM-counter access and OpenSBI's entire HPM capability loop with `CORE[0] PASS`. The next blocker is the immediately following optional-CSR capability block, not the context-switch path or the HPM repair.

- **Optional-CSR repair validated locally:** BlackParrot `3df31a94` exposes the six optional CSRs OpenSBI probes there as legal hardwired-zero WARL registers. Its focused clean traced regression and the independent FPGA-toolchain smoke both pass; a routed static-PYNQ package is in progress for the corresponding physical proof.

- **Optional-CSR repair proved on hardware:** the routed static-PYNQ package for top-level `05b1e786` / BlackParrot `3df31a94` passes the exact OpenSBI capability-block terminal probe (`My`, `CORE PASS`) and the patched `sbi_hart_init` return probe. It fits the board at 51,552/53,200 LUTs, 140/140 BRAM, WNS +3.081 ns, WHS +0.037 ns, TNS/THS 0.

- **Linux boot boundary advanced:** the unchanged archived Linux image now prints the complete OpenSBI v1.4 banner and capability report on the repaired hardware, proving the earlier firmware bootstrap deadlocks are fixed. The same fresh run then made only 992,765 retired instructions in 150 seconds (IPC 0.001) without a Linux banner, establishing a new downstream handoff/kernel-entry stall; it is not yet a `/init` boot.

- **Late OpenSBI localization:** fresh one-shot FPGA probes prove the cold-boot path returns from `sbi_hart_init` (`M6`), completes console/SSE initialization (`M7`), and completes ecall initialization (`M8`). The unmodified-image stall is therefore later in `sbi_init`, before its final `sbi_hart_switch_mode` call; the next probes will split only that interval.

- **Local-reproduction boundary:** a generic non-inlined `jal` → `sd; fence ow,ow` → `ret` gate passes, but an exact-address variant and the existing FPGA-proven high-PC gate both time out in the static PYNQ model. Sparse high-PC execution is therefore not a trustworthy local discriminator; the exact-address experiment was discarded and later handoff diagnosis remains FPGA-marker-driven.

- **OpenSBI late-init localization:** the routed `05b1e786` / `3df31a94` image now passes current-path terminal probes after `sbi_ecall_init` (`M8`), at the late `sbi_init` midpoint (`M9`), and after final PMP configuration (`Ma`). In final HSM completion, the `atomic_cmpxchg` entry marker passes while later `atomic_write` and `sbi_hart_switch_mode` entry markers time out; this confines the live fault before the atomic write, but does not claim the compare-exchange returned.

- **LR/SC gate established:** an exact `lr.d.aq`/`sc.d.aq` compare-exchange test passes in both the static board-style simulator and the routed PYNQ image (old value 2, store-conditional status 0, final value 0). The OpenSBI marker immediately after its own `atomic_cmpxchg` still times out, so the remaining defect is sequence- or operand-specific rather than a general aligned LR/SC implementation failure.

- **Exact OpenSBI call gate:** a new direct-JAL test linked at OpenSBI's live call site (`0x8000e610`) and callee entry (`0x80007a70`) passes in both the static board model and the routed PYNQ image (`CORE PASS`). The live marker reaches the call site but not callee entry, so the remaining fault depends on the preceding OpenSBI/frontend state rather than that PC pair or a generic LR/SC operation.

- **Halfword redirect reproduction:** a traced static-model probe now reproduces the remaining OpenSBI boundary without Linux or FPGA synthesis: a normal JAL redirect to OpenSBI's valid halfword-aligned `c.addi16sp` at `0x8000e5ee` raises illegal-instruction cause 2 at that PC, while the same compressed sequence reached linearly and a JAL entered at word-aligned `0x8000e5f0` both pass. This is a narrow normal-frontend regression, not execution of a custom context-switch opcode; RTL correction and hardware proof remain pending.

- **Cold-line control:** a fresh static-model control initializes the complete `0x8000e5e0` I-cache line and redirects cold directly to OpenSBI's `0x8000e5ee` `c.addi16sp`; it reaches `CORE PASS` and its trace shows `instr=0x7139`. The earlier trap probe's NBF began at e5ee and was therefore not a valid full-line reproduction; the next gate preserves the exact OpenSBI prefix and live state.

- **Halfword theory retired:** the exact archived e5e0--e5ef bytes together with the complete OpenSBI HSM prologue and its call at `0x8000e610` to `0x80007a70` also pass locally. No RTL repair is justified from the old e5ee trap; the remaining FPGA-only stop depends on uncaptured live firmware state, so the next work is state capture at the proven call boundary.

- **Live HSM-state capture:** a trampoline at the physical final-HSM call was first controlled with `x0`, producing exactly `MoX0N`, then captured `a0=0x0000000080044088` with a five-field sanity record `MpA8B2S8P0RCN`; every run ended in `CORE PASS`. This retires the unobservable DRAM dump experiment and gives a 20--30 second, hashable FPGA state-capture loop for the remaining operand/sequence diagnosis.

- **Live HSM atomic-address gate:** the exact `lr.d.aq`/`sc.d.aq` 2→0 compare-exchange at captured address `0x80044088` passes in both the clean traced static model and the routed FPGA (old 2, SC status 0, final 0). The remaining stop is therefore history-sensitive around the real firmware sequence, not an atomic-extension, alignment, or operand-address failure.

- **Current OpenSBI-to-Linux handoff:** terminal probes through the untouched compare-exchange return, comparison-success path, atomic-write return, and real `sbi_hart_switch_mode` entry all pass on FPGA; a final fresh terminal at `0x80200000` also passes. The current image therefore completes OpenSBI and executes `mret` into Linux S-mode, so remaining localization is genuinely in Linux rather than firmware bootstrap.

- **Early-Linux physical bracket:** on the latest static routed image, guarded host markers reach Linux stack setup (`0x8020113c`), its first main-kernel routine (`0x80c05544`), and the returns from its first five real helper calls through `0x80c0590c` (all `CORE PASS`). The next marker at `0x80c059c0` does not reach, reducing the live interval to the preceding 184-byte setup with two explicit `ebreak` assertion paths. The original 720-byte span is therefore a coarse milestone gap, not an assertion that every intervening byte is dynamically executed; current probes bisect the actual call path.
