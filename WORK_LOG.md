# Engineering Work Log

> Purpose: This is the chronological record of the BlackParrot context-switch and Linux-on-FPGA investigation. It records what was attempted, what the evidence showed, and which outcomes are confirmed. A reader can reconstruct progress without knowing the prior conversation, while detailed commands, waveform evidence, and boot-stage analysis remain in the linked status documents.

## How to use this log

Append an entry before beginning the next material step after a reproduction attempt, a confirmed or rejected fix, an FPGA/Linux run, an infrastructure event, or a commit. Say whether the result is confirmed or only a hypothesis, and include a command, revision, or retained log path when that is useful.

## 2026-09-02 — current investigation

- **Documentation checkpoint:** created this work log and added an `AGENTS.md` rule requiring a self-contained entry for each material reproduction, fix, board run, infrastructure event, and commit. The same policy now requires every Markdown file that we create or edit to begin with a plain-language purpose statement.

- **Commit checkpoint:** committed the logging policy and initial history as top-level revision `d0aaeb1` (`docs: add chronological engineering work log`). This commit is documentation-only and does not alter RTL, NBF content, or the deployed FPGA overlay.

- **Confirmed historical baseline:** root revision `69b939b` with BlackParrot revision `c39ee12b735` booted the archived Linux 6.6 image through `/init`, ran root-file-system checks, powered off cleanly, and reported `CORE[0] PASS`. This proves that the original SRAM-backed context-switch implementation can coexist with this Linux workload.

- **Confirmed historical regression:** BlackParrot revision `7331fbd0958` completed OpenSBI output but stalled during the transfer to Linux supervisor mode, before the Linux banner. The detailed FPGA bisect is recorded in [`LINUX_BOOT_BISECT.md`](LINUX_BOOT_BISECT.md).

- **Confirmed frontend constraint:** reverting either the global frontend command-queue bypass or the frontend PC-generator thread-selector reset alone did not restore Linux, while reverting both at root revision `2a1f883` / BlackParrot `ce328a77536` did boot through `/init`. Normal instructions must therefore not take either fast context-switch frontend behavior outside an actual context-switch command.

- **Confirmed repair direction:** the current repair stack scopes the fast frontend behavior to context-switch commands and moves custom context CSRs away from Linux’s ordinary CSR space. Earlier FPGA runs progressed from the old silent/OpenSBI handoff failure into Linux initialization; the repair history and confidence levels are in [`LINUX_BOOT_STATUS.md`](LINUX_BOOT_STATUS.md).

- **Confirmed local regression coverage:** `mt_smode_jiffies_unaligned_probe_test` passed from a clean full-model run with `TRACE=1`, covering M-to-S handoff, delegated unaligned recovery, an S-to-M call, timer forwarding, an S-mode timer handler, and repeated unaligned copies. Its two earlier failures were corrected test setup defects—an already-pending timer before `mret`, and a wrong CLINT address—not RTL failures.

- **Confirmed SBI timer coverage:** the new `mt_smode_sbi_time_jiffies_test` completed its S-mode SBI `TIME set_timer` call, MTIP-to-STIP forwarding, S-mode timer handler, and SBI disarm path in the full static model (`SWT`, `CORE PASS`, `BSG PASS`). Verilator emitted the project’s pre-existing DPI teardown assertion after `BSG PASS`; the same post-success assertion appears in earlier passing full-model logs and does not invalidate the architectural result.

- **Confirmed current FPGA boundary:** the current Linux image reaches the RISC-V `check_unaligned_access_boot_cpu` initcall and emits its entry trace, but the matching return trace has not appeared. The retained board transcript is `~/bp-logs/linux-initcall-debug-20260902T152155Z-2641227.log`; this is a localized symptom, not yet a confirmed root cause.

- **Corrected diagnostic mistake:** an older physical marker was placed at `0x80203198`, which is a late reporting tail in `check_unaligned_access`, not the `check_unaligned_access_boot_cpu` entry at `0x8020319e`. Guarded SBI-console probes were generated for the exact entry, unaligned-copy, and timer-wait boundaries before changing more RTL.

- **Inconclusive FPGA reproduction:** the guarded entry probe for physical address `0x8020319e` ran with matching local/remote SHA-256 `8ecc5f…5515`, completed OpenSBI, and exited `RUNNER_EXIT=0` in about 0.53 seconds, but did not print its expected `M1` marker. Because an SBI reset can also cause a clean host completion and the marker transport is not yet independently validated, this run does not establish whether the Linux initcall entry executed.

- **Rejected validation attempt:** a normal host-marker probe at the known Linux S-mode entry `0x80200000` was correctly rejected before deployment because the source NBF has an unmapped header gap immediately after its first instruction. The patch tool required a fully backed replacement window, so no unsafe partial NBF write was created or run.

- **Failed control reproduction:** a two-instruction host-finish probe at the same known S-mode entry was generated with source-word guard `0x106f5a4d` and deployed as `linux-known-s-entry-minimal.nbf`, but it remained silent after `start()` instead of finishing immediately. This means the control does not yet validate the intended NBF-patching assumption, so it cannot be used to interpret the unaligned-initcall probe.

- **Infrastructure recovery:** invoked `/home/coyang/power_cycle.sh` after the silent control probe left `control-program` active. By `2026-09-02T21:10:21Z`, SSH was reachable again and the board reported `IDLE`; any future deployment must reload and verify the intended overlay after this reset.

- **Commit checkpoint:** this log update records the completed board recovery, local SBI-timer pass, and the two inconclusive NBF-probe outcomes as a documentation-only checkpoint. It does not change RTL, synthesized artifacts, or the FPGA’s configured overlay.

- **Infrastructure recovery:** the FPGA board was power-cycled by the user after a stale `control-program` Linux runner remained active for several hours. At `2026-09-02T20:56:18Z`, SSH was reachable, the board reported `IDLE`, and uptime was four minutes; the intended overlay must be explicitly reloaded before the next run.

- **FPGA deployment recovery:** after the power cycle, the scoped overlay loader successfully programmed the intended BlackParrot image and reported `OVERLAY_LOAD_OK=1` and `REMOTE_OVERLAY_LOAD_OK=1`. The loaded bitstream SHA-256 is `b9855bcad5d9443ef53fe553ba9b1b1b804c744702dd94becd172c70b3a9a741`.

- **Workflow checkpoint:** the scoped root-owned overlay loader and serialized PYNQ runner are the approved unattended board mechanisms. Board executions remain serialized because `control-program`, deployment paths, and retained logs are shared resources.

- **Commit checkpoint:** top-level branch `linux-boot-triage` is at pushed revision `a6c6d5e` (`tools: add guarded Linux repair checkpoint runner`), and its BlackParrot submodule is at `1c42e9f2`. These revisions are the starting point for the next exact Linux-boundary probe.
