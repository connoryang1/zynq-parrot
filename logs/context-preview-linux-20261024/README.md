This directory records the first physical Linux run of the application-controlled target-data preview oracle. It retains a line-ending-normalized board transcript, independent audit, and all 32 measured rows for the first-use result; the later phase run corrected this run's total endpoint from one-way handoff to source-to-source round trip.

# Physical Linux preview oracle, 2026-10-24

The run used the routed ten-context bitstream SHA-256 `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`, non-debug Linux shell NBF SHA-256 `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`, and guest ELF SHA-256 `eb48c980c0a4926a4b15df180e08d2c9d015d79fa8cd16f82d04a576091cb6df`. The committed, line-ending-normalized `board.log` SHA-256 is `984eaa429cd16ef6cae531b70462c544fbbaa8e83da1d1657fe9879e1eb8c18a`; the original terminal byte stream has SHA-256 `c63fc8155d316d1e536a4b6b63e365b23733a181b556b632ac3ca6456f8056e5` and remains local as `board.raw.log`. Run `python3 audit_run.py` from any directory to recheck the committed rows, guest hash printed in the board transcript, clean exit, host markers, and remote runner status.

| Mode | Preview | Median peer four-load cycles | Median source-to-source round-trip cycles |
| --- | --- | ---: | ---: |
| 0 | direct | 200.5 | 31,151 |
| 1 | empty | 139 | 36,319.5 |
| 2 | correct | 7 | 49,586.5 |
| 3 | stale | 180.5 | 51,586 |

The peer load interval is the narrow, positive mechanism result: seven of eight correct-hint trials took seven cycles. The total ends after the source wakes again, so it includes a return handoff and cannot establish target startup latency. The phase-instrumented follow-up in `logs/context-preview-linux-phases-20261024/` measures peer entry and completion explicitly. The preview helper belongs to the source process, so this is an oracle handoff across real Linux scheduling rather than a Linux scheduler or per-task hardware-context feature.

## Setup and validation incidents

- The legacy `linux-shell.nbf` begins with a debug-interrupt pulse; the previously confirmed boot-control study in `logs/linux-memory46-boot-control-20261006/` explains the silent OpenSBI boot. Two attempts with that image never reached the application. The accepted run used the hash-checked non-debug NBF above, and an NBF's initial commands must be inspected before treating a silent boot as an RTL result.
- The first dynamic ELF carried a 40 KiB initialized eviction array and its shell transfer stalled after roughly 600 commands. The cause of the stall remains unknown. Moving the array to BSS, touching each page before measurement, and stripping the ELF reduced transfer to 332 commands; the accepted run verified the guest ELF hash before execution.
- The initial local runner recorded failure at the terminal marker because it required `CORE[0] PASS`, while this host emitted `INFO:    CORE PASS`. The complete raw transcript has 32 rows, `CONTEXT_PREVIEW PASS`, exit zero, clean poweroff, `CORE PASS`, `BSG PASS`, and remote `RUNNER_EXIT=0`. `audit_run.py` verifies those conditions and writes `validated-status.json`; `run_board.py` now accepts either host marker spelling. The original `board-status.json` remains as evidence of the harness mismatch, not an application failure.
