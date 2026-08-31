---
name: bp-fpga-synthesis
description: Prepare, launch, monitor, and interpret BlackParrot FPGA builds for zynq-parrot, especially PYNQ-Z2 Vivado synthesis, implementation, utilization, timing, bitstream fit checks, and comparisons between context-switch optimization checkpoints. Use for build-readiness checks, FPGA fit questions, background synthesis, or review-ready hardware validation.
---

# BlackParrot FPGA Synthesis

Keep quick iteration separate from slow implementation. Treat a routed bitstream with
acceptable timing as the fit gate; elaboration or synthesis alone is not enough.

## Before Any Build

1. Run `scripts/check_build_ready.sh` from anywhere in the checkout.
2. Record the top-level commit and pinned `import/black-parrot` commit.
3. Require a clean top-level worktree and clean BlackParrot submodule for a comparison build.
4. Run the relevant simulation/correctness gate before spending hours on Vivado.
5. Use `CFG=e_bp_unicore_zynqparrot_cfg` unless the branch defines and documents another enum.

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
environment, never in tracked files or logs. A power cycle restores the board's default overlay;
explicitly reload and verify the intended BlackParrot bitstream before interpreting any run.

For an interactive variant of the maintained Linux regression NBF, use
`scripts/make_linux_shell_nbf.py <linux.nbf> <linux-shell.nbf>`. The helper changes only the
embedded bootargs to `rdinit=/bin/sh` and emits aligned 8-byte NBF writes; do not use the legacy
byte or halfword NBF writes for this patch.

## Iteration Modes

Use the foreground only for quick checks such as readiness, `git diff --check`, compilation,
and targeted simulation. Serialize tests that share the same Verilator directory.

Launch routed FPGA implementation in an isolated background worktree:

```bash
codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh start
```

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
