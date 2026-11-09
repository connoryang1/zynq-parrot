---
name: bp-background-verification
description: Launch, inspect, and interpret isolated asynchronous BlackParrot simulation ladders without touching the active checkout's simulator, program, log, or waveform artifacts. Use for long or layered verification that must continue independently while foreground development proceeds; do not use it for Vivado or live-board work.
---

This skill runs committed BlackParrot checkpoints through a low-priority verification lane that is physically separate from foreground iteration. It keeps the active checkout responsive and its shared simulator artifacts untouched while retaining trace-backed evidence for each selected gate.

# Background Verification

## Required launcher

Use [`scripts/background_verification.sh`](scripts/background_verification.sh). Do not replace it with an ad-hoc background `make`, `nohup`, or parallel invocation in the canonical checkout.

The launcher:

- accepts only a clean, committed top-level and pinned submodule state;
- checks out that immutable revision in persistent detached worktrees outside the repository;
- gives 2/4 and 2/10 trace configurations separate simulator directories;
- uses isolated `riscv/`, `prog.*`, logs, and FST files;
- serializes every simulator run inside the background lane;
- runs under low CPU and I/O priority with two Verilator build jobs by default;
- arms a 20-minute per-test simulator watchdog by default so a hung target cannot consume a lane indefinitely;
- reuses an existing model only when its hardware/configuration fingerprint matches;
- never invokes Vivado, programs a board, or waits in the foreground.

## Layers

Choose the smallest layer that answers the question:

- `smoke`: protected-RPC hardware test at 2 resident / 4 logical contexts.
- `targeted`: `smoke` plus raw RPC transport, resident switch, machine-trap, CSR-isolation, and translated resident handoff gates at 2/4.
- `exact`: protected and raw RPC tests in the exact 2/10 logical-context topology.
- `full`: harness checks, `targeted`, then `exact`.

Start a job and return immediately:

```bash
codex-skills/bp-background-verification/scripts/background_verification.sh start targeted
```

Inspect it without attaching to or delaying the foreground flow:

```bash
codex-skills/bp-background-verification/scripts/background_verification.sh list
codex-skills/bp-background-verification/scripts/background_verification.sh status <job-id>
codex-skills/bp-background-verification/scripts/background_verification.sh tail <job-id> 80
```

Use `plan <layer>` to inspect the selected commands without launching anything.

## Safety and interpretation

- Never launch from uncommitted work. Make a checkpoint commit first so continued editing cannot change the running evidence.
- Do not run more than one background ladder at once. The launcher enforces this even though its 2/4 and 2/10 artifacts are distinct.
- Foreground tests may continue in the canonical checkout because the background lane has disjoint write sets. Expect some residual host resource use, but background jobs inherit `nice 15`, idle I/O priority, and the configured build-job cap.
- Adjust `ZP_BG_VERIFY_BUILD_JOBS`, `ZP_BG_VERIFY_MIN_FREE_KB`, or `ZP_BG_VERIFY_TIMEOUT_S` only when the host or test requires it; keep the defaults for ordinary use.
- Treat a completed layer as evidence only for its named tests and exact recorded revision/configuration.
- Do not promote `smoke` or `targeted` to exact-topology evidence. Use `exact` before a final ten-context checkpoint.
- Do not add FPGA implementation to this ladder. At a final RTL milestone, use `bp-fpga-synthesis` separately and explicitly.
- Do not poll repeatedly. Report the job ID and artifact directory, continue useful foreground work, and check status at a natural checkpoint or when the user asks.

## Reporting

When launching, report the job ID, layer, immutable revision, and log path. When interpreting completion, report each test's verdict, the first failing gate if any, and the scope of what passed; link the retained `summary.txt`, per-test logs, and revision manifest.
