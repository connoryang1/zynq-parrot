# Engineering Work Log

> Purpose: This is the chronological record of the BlackParrot context-switch and Linux-on-FPGA investigation. It records what was attempted, what the evidence showed, and which outcomes are confirmed. A reader can reconstruct progress without knowing the prior conversation, while detailed commands, waveform evidence, and boot-stage analysis remain in the linked status documents.

## How to use this log

Append an entry before beginning the next material step after a reproduction attempt, a confirmed or rejected fix, an FPGA/Linux run, an infrastructure event, or a commit. Say whether the result is confirmed or only a hypothesis, and include a command, revision, or retained log path when that is useful.

## 2026-09-02 — current investigation

- **Documentation checkpoint:** created this work log and added an `AGENTS.md` rule requiring a self-contained entry for each material reproduction, fix, board run, infrastructure event, and commit. The same policy now requires every Markdown file that we create or edit to begin with a plain-language purpose statement.

- **Confirmed historical baseline:** root revision `69b939b` with BlackParrot revision `c39ee12b735` booted the archived Linux 6.6 image through `/init`, ran root-file-system checks, powered off cleanly, and reported `CORE[0] PASS`. This proves that the original SRAM-backed context-switch implementation can coexist with this Linux workload.

- **Confirmed historical regression:** BlackParrot revision `7331fbd0958` completed OpenSBI output but stalled during the transfer to Linux supervisor mode, before the Linux banner. The detailed FPGA bisect is recorded in [`LINUX_BOOT_BISECT.md`](LINUX_BOOT_BISECT.md).

- **Confirmed frontend constraint:** reverting either the global frontend command-queue bypass or the frontend PC-generator thread-selector reset alone did not restore Linux, while reverting both at root revision `2a1f883` / BlackParrot `ce328a77536` did boot through `/init`. Normal instructions must therefore not take either fast context-switch frontend behavior outside an actual context-switch command.

- **Confirmed repair direction:** the current repair stack scopes the fast frontend behavior to context-switch commands and moves custom context CSRs away from Linux’s ordinary CSR space. Earlier FPGA runs progressed from the old silent/OpenSBI handoff failure into Linux initialization; the repair history and confidence levels are in [`LINUX_BOOT_STATUS.md`](LINUX_BOOT_STATUS.md).

- **Confirmed local regression coverage:** `mt_smode_jiffies_unaligned_probe_test` passed from a clean full-model run with `TRACE=1`, covering M-to-S handoff, delegated unaligned recovery, an S-to-M call, timer forwarding, an S-mode timer handler, and repeated unaligned copies. Its two earlier failures were corrected test setup defects—an already-pending timer before `mret`, and a wrong CLINT address—not RTL failures.

- **Confirmed current FPGA boundary:** the current Linux image reaches the RISC-V `check_unaligned_access_boot_cpu` initcall and emits its entry trace, but the matching return trace has not appeared. The retained board transcript is `~/bp-logs/linux-initcall-debug-20260902T152155Z-2641227.log`; this is a localized symptom, not yet a confirmed root cause.

- **Corrected diagnostic mistake:** an older physical marker was placed at `0x80203198`, which is a late reporting tail in `check_unaligned_access`, not the `check_unaligned_access_boot_cpu` entry at `0x8020319e`. Guarded SBI-console probes were generated for the exact entry, unaligned-copy, and timer-wait boundaries before changing more RTL.

- **Infrastructure recovery:** the FPGA board was power-cycled by the user after a stale `control-program` Linux runner remained active for several hours. At `2026-09-02T20:56:18Z`, SSH was reachable, the board reported `IDLE`, and uptime was four minutes; the intended overlay must be explicitly reloaded before the next run.

- **Workflow checkpoint:** the scoped root-owned overlay loader and serialized PYNQ runner are the approved unattended board mechanisms. Board executions remain serialized because `control-program`, deployment paths, and retained logs are shared resources.

- **Commit checkpoint:** top-level branch `linux-boot-triage` is at pushed revision `a6c6d5e` (`tools: add guarded Linux repair checkpoint runner`), and its BlackParrot submodule is at `1c42e9f2`. These revisions are the starting point for the next exact Linux-boundary probe.
