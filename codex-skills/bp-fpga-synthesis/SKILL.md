---
name: bp-fpga-synthesis
description: Prepare, launch, monitor, and interpret BlackParrot FPGA builds for zynq-parrot, especially PYNQ-Z2 Vivado synthesis, implementation, utilization, timing, bitstream fit checks, and comparisons between context-switch optimization checkpoints. Use for build-readiness checks, FPGA fit questions, background synthesis, or review-ready hardware validation.
---

# BlackParrot FPGA Synthesis

This file defines the reproducible build and deployment procedure for the
PYNQ-Z2 BlackParrot image. It separates cheap local evidence, expensive routed
implementation, and serialized board acceptance so each result answers a
specific engineering question.

Keep quick iteration separate from slow implementation. Treat a routed bitstream with
acceptable timing as the fit gate; elaboration or synthesis alone is not enough.

## Before Any Build

1. Run `scripts/check_build_ready.sh` from anywhere in the checkout.
2. Record the top-level commit and pinned `import/black-parrot` commit.
3. Require a clean top-level worktree and clean BlackParrot submodule for a comparison build.
4. Run the relevant simulation/correctness gate before spending hours on Vivado.
5. Use the exact configuration that produced the NBF. The deployed PYNQ-Z2
   context-cache image uses the static `CFG=e_bp_unicore_zynqparrot_cfg`,
   which encodes two resident banks and four architectural contexts. Do not
   use the dynamic `e_bp_custom_cfg` path: its macro expansion is broken here
   and silently selects an incompatible four-resident-thread design.

Readiness also rejects a historical dependency mismatch where BlackParrot's
context SRAM requests BaseJump's `ram_style_p`, but the top-level BaseJump
wrapper selected by Vivado predates that parameter. Resolve it with the exact
top-level BaseJump revision from the corresponding BRAM-backed feature
checkpoint; do not remove the RAM-style request merely to make elaboration pass.

If Sourceware returns HTTP 429 during `prep_lite`, run
`scripts/setup_sourceware_mirrors.sh`. It installs checkout-local mirror URLs and shallowly
checks out the exact gitlink commits; it must not advance dependency revisions.

If the cosimulation build cannot find Boost coroutine headers or libraries, run
`scripts/setup_vivado_boost.sh`. It links the Boost 1.72 headers and shared libraries bundled
with Vivado 2024.2 into the ignored `install/` prefix and does not modify the host system.

If readiness reports missing generated OpenTitan PLIC RTL, run
`scripts/setup_opentitan_plic.sh`. It installs the pinned Python dependencies under the ignored
`install/` prefix, applies the legacy patches in numeric order to a temporary source snapshot,
and atomically replaces the generated output without dirtying the OpenTitan submodule.

Use `scripts/run_vivado_2024_2.sh` instead of invoking Vivado directly on this VM. The installed
Vivado copy has a damaged core library, and the wrapper supplies the valid same-release library
from Vitis 2024.2 without modifying either installation. It exposes the replacement through
Vivado's patch-area mechanism, so shell helpers and IP child processes retain their normal loader
state.

Read [references/pynqz2-flow.md](references/pynqz2-flow.md) when preparing dependencies,
deploying to a board, or diagnosing an old command.

Before copying a package to a board, run
`scripts/verify_pynq_package.sh <package> [expected-bit-sha256]`. Treat the reported artifact
stem and SHA as authoritative; do not infer them from an older board Makefile or reuse already
unpacked files.

Before deploying a Linux NBF after adding or changing custom CSRs, reject CSR-address collisions
in the exact image: `scripts/check_nbf_csr_collisions.sh <linux.nbf> <custom-csr> [...]`.
Use an ISA-reserved custom range at the intended privilege level—for the current user-accessible
context interface, `0x800`–`0x802`—rather than a standard CSR address. A collision is a functional
blocker even if the Linux source never names the project extension.

Stage a verified package and its NBFs with
`scripts/stage_pynq_artifacts.sh <package> <ssh-host> [program.nbf ...]`. The helper reads the
overlay filename from the board's dry-run load command, extracts the package, copies BIT/HWH/MAP
together when legacy and current stems differ, and verifies package, bitstream, and NBF hashes.
It deliberately does not invoke sudo or load the overlay.

For unattended overlay reloads, install the fixed-path board helper once with
`sudo scripts/install_pynq_overlay_loader.sh` on the board. Then run
`scripts/load_pynq_overlay.sh <ssh-host>` from the VM after every stage, interrupted run, or power
cycle. The sudo rule grants only `/usr/local/sbin/load-blackparrot-overlay`; never grant
passwordless access to Python, a shell, `make`, or arbitrary overlay paths.

If the PYNQ board stops accepting SSH, use
`PYNQ_POWER_STATE_URL=... scripts/power_cycle_pynq.sh <ssh-host>`. Keep the controller URL in the
environment, never in tracked files or logs. A power cycle restores the board's default overlay.
SSH and the PL manager become available before PYNQ's own boot service is stable, so always run
`scripts/wait_pynq_ready.sh <ssh-host>` after any power cycle and before loading an overlay; it
requires both the `Startup finished` journal milestone and a 90-second uptime by default.
Explicitly reload and verify the intended BlackParrot bitstream before interpreting any run. After
every overlay reload, also require the FPGA manager state to read `operating` before launching
`control-program`; the maintained loader enforces and records this gate.

For an interactive variant of the maintained Linux regression NBF, use
`scripts/make_linux_shell_nbf.py <linux.nbf> <linux-shell.nbf>`. The helper changes only the
embedded bootargs to `rdinit=/bin/sh` and emits aligned 8-byte NBF writes; do not use the legacy
byte or halfword NBF writes for this patch.

For a real interactive Linux console, install the unprivileged serialization helper once with
`scripts/install_pynq_interactive_runner.sh <ssh-host>`, then run
`PYNQ_CONTROL_PROGRAM_SHA256=<reviewed-sha> scripts/run_pynq_interactive.sh <ssh-host> <linux-shell.nbf>`
from a PTY. This retains the same board lock, exact NBF/runner hash checks, fixed checkout path,
bounded target runtime, and persistent transcript as automated runs while allowing typed guest
input. Never fall back to a direct `sudo ./control-program` session merely to gain stdin.

## Iteration Modes

Use the foreground only for quick checks such as readiness, `git diff --check`, compilation,
and targeted simulation. Serialize tests that share the same Verilator directory.

When an isolated or historical candidate predates the maintained `_fpga.nbf`
rules or board CRT sources, do not launch another Vivado build and do not copy
unreviewed infrastructure into the RTL checkpoint. Compile the candidate's
exact test source against the known-reviewed integer board CRT from the
coordination checkout, define `BP_FPGA_PROGRAM`, package it with the candidate's
NBF tool, and record the source, CRT, ELF, and NBF hashes. This is a software
collateral change only; keep its revision identity separate from the committed
RTL revision used by the bitstream.

For a clean trace-enabled Verilator build on this checkout, remove the parent make jobserver
from Verilator's environment and give Verilator the worker count explicitly:
`make -C <verilator-dir> clean CFG=<cfg> TRACE=1`, then
`make -C <verilator-dir> obj_dir/Vbsg_nonsynth_zynq_testbench CFG=<cfg> TRACE=1 VERILATOR='env -u MAKEFLAGS verilator --build-jobs 12'`.
Without `env -u MAKEFLAGS`, Verilator's generated make can inherit closed jobserver descriptors,
warn that the jobserver is unavailable, and silently compile with one worker.

Launch routed FPGA implementation in an isolated background worktree:

```bash
codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh start
```

If the active checkout has unrelated tracked edits, do not weaken the dirty-tree
guard or route those edits accidentally. Create a clean detached source snapshot
at the committed checkpoint, initialize its pinned submodules, expose only the
shared ignored `install/` and `riscv/` directories, then invoke the launcher with
`ZP_REPO_DIR=<clean-snapshot>`,
`ZP_FPGA_SEED_REPO_DIR=<active-checkout-with-submodules>`, and
`ZP_FPGA_LOG_ROOT=<persistent-log-dir>`. The seed checkout supplies exact nested
BlackParrot submodule objects (`external/basejump_stl`, `external/HardFloat`, and
`external/bedrock`) that an upstream remote may no longer advertise. Run the readiness check
against the seed first so a missing nested dependency fails before the background job is created.
The recorded source revision remains immutable while logs stay outside temporary
storage.

The launcher returns immediately and writes the job ID, PID, immutable source revisions,
console log, reports, and artifact under `logs/fpga/<job-id>/`. It uses shared `install/` and
`riscv/` dependencies but a separate source/build tree, so normal edits do not alter the run.

Inspect jobs without blocking:

```bash
codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh list
codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh status <job-id>
```

Do not launch two Vivado implementations concurrently by default; they compete for memory and
make timing comparisons noisy. Do not delete an active job worktree.

## Acceptance Gate

Require all of the following:

- the build command exits zero
- the `.bit`, `.hwh`, and `.map` files exist
- the packed `.tar.xz.b64` artifact exists and is nonempty
- routed timing exists; report WNS and TNS
- utilization exists; report LUT, FF, BRAM, and DSP use and percentages
- no unresolved Vivado `ERROR` or material `CRITICAL WARNING` remains
- the exact top-level and RTL revisions accompany the result

Run `scripts/summarize_vivado.sh <vivado-directory>` to extract the stable report summary.
Compare against a same-board, same-Vivado, same-CFG baseline. Never claim a hardware
improvement from simulation cycles alone or compare a routed result with a synthesis estimate.

## Reporting And Logging

Report configuration, revisions, command, elapsed time, result, WNS/TNS, utilization, warnings,
and artifact path. Append accepted results to the optimization timing ledger; keep failed or
reverted experiments in the experiment log with their failure reason.

Program or copy files to an FPGA only when the user authorizes that external action.

For board validation, record three independent identities: packed-package SHA, extracted
bitstream SHA, and NBF SHA. Reload the overlay after extraction, even when PYNQ reports an overlay
is already present. Confirm the board checkout's Zynq Makefile does not enable `DRAM_TEST` for an
application run; that diagnostic is not an NBF execution gate.

After the overlay reload and NBF upload, run the serialized reusable ladder with
`scripts/run_pynq_validation.sh <ssh-host> [remote-zynq-directory]`. It rejects a `DRAM_TEST`
runner, verifies every local/remote NBF SHA pair, preserves one host log per image, and stops at
the first missing PASS marker. Remote execution uses the separately scoped `control-program *`
sudo rule; confirm it and the fixed-path overlay helper both work with `sudo -n` before starting a
long unattended ladder.

If a Linux image retires instructions but emits no console output, do not begin in the kernel.
First run an OpenSBI-only NBF prefix. If that has the same execution signature, build and run
`mt_amo_swap_return_test_fpga.nbf`; it reproduces OpenSBI's boot-hart lottery with the address and
AMO destination both in `a6`, a plain `amoswap.w` with no acquire/release bits, and the dependent
branch immediately afterward. A different AMO ordering or separate AMO destination is not an
equivalent test because it can exercise a different pipeline path or its stale value can
accidentally match the expected old value. Read the OpenSBI triage section in
`references/pynqz2-flow.md` before changing RTL.

For every silent-Linux FPGA iteration, use the diagnostic bundle in that reference before another
RTL change or synthesis: record the trusted runner/bit/NBF hashes, run the ordered physical
pre-SATP milestone probes, retain the board log in persistent board-home storage (never `/tmp`),
and run the matching traced local privilege/SATP gate. Do not treat a physical NBF marker after
SATP as evidence unless its virtual-to-physical mapping has been established. The current PYNQ-Z2
image has no spare BRAM for an ILA.

When a physical probe localizes a Linux failure to an instruction boundary, capture the live
architectural inputs at that same boundary before creating or interpreting a local reproducer.
Use a guarded terminal NBF probe and fixed-character SBI state reporting (for example, selected
register or CSR nibbles); it must branch on the captured value before its first SBI call, because
the call may clobber caller-saved registers. A simplified local page table, register image, or
trap setup is only a hypothesis until it agrees with this physical capture. After any timed-out,
interrupted, or SBI-reset terminal board run, power-cycle and reload the overlay before the next
program; do not infer behavior from a follow-on PL state.

Before accepting a data-dependent terminal reporter, execute the same-PC reporter with `x0` (or
another known value) and require the expected dynamic character plus `CORE[0] PASS`. Keep the
reporter bounded and dependency-safe with explicit settling between value construction and its
branch; reject any result from a large table, stale register, or post-call register read that has
not passed this control.
