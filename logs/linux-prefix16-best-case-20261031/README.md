This directory preserves the physical FPGA evidence for the larger instruction-prefix and best-case-table investigation. It separates accepted 50-sample timing batches from runs rejected before measurement, and it records the exact image identities needed to reproduce either result.

# Linux instruction-prefix best-case sweep

## Fixed identities

- Routed top-level commit: `3a08584d`; BlackParrot commit: `b1a065281`.
- FPGA package SHA-256: `5694f58f2e9d352ca2f25e1a2fdebbc1bb1e3d9caed8f646794cea69041b4999`.
- Bitstream SHA-256: `e1e66020ef2cf1a286077229ecd8a62d8ef56ca68bd3497afe0dfc91a7492338`.
- Linux `vmlinux.bin` SHA-256: `98a0edc35455d5d2446a3e3e7efbe8d7fa8fb4499e16c22700169a126390acb8` (kernel build `#8`).
- Device tree SHA-256: `bfa8247ae703bc96d4c8f6f14b4ca13b6553de05388dba26ba5881fb5593606f`.
- Benchmark ELF SHA-256: `332d4e9c54660586234fd6eef2b464973e4aa7f76d5c13c4f49fc8c648eeb6a7`.
- Replay-disabled shell NBF SHA-256: `eee6fa9ff26307f7b8f0edf3cf3e2718f2a6ad2a073a11fa87aa6c27235fe716`.

Every accepted arm used a fresh overlay load, one unrecorded warmup, 50
`--window to-peer --summary-only` samples, and a clean guest poweroff followed
by `CORE PASS` and `BSG PASS`. Recorder overflow was not used to filter timing
endpoints because it is correlated with long intervals.

## Accepted timing results

The two disabled and two old 16-line batches in `results.json` remain the
matched replicated comparison. Their pooled medians are 18,007 cycles disabled
and 15,661.5 cycles for the old 16-line table, a 2,345.5-cycle (13.0%) favorable
point estimate. The pooled 95% bootstrap interval is `[-21,576.5, +1,401.5]`
cycles, so it does not establish an end-to-end speedup.

`prefix8-summary50.log` is an accepted additional size point. Its median is
17,539.5 cycles (2.6% below the pooled disabled median), with a 95% interval of
`[-19,571, +18,922]` cycles and only 61.6% of resamples favoring replay.

`prefix14-tail-summary50.log` tests a table restricted to the 14 privileged
lines observed after the actual scheduler trigger in exact kernel-#8 traces.
It completes cleanly but has a 19,578.5-cycle median, 8.7% above disabled; its
95% interval is `[-19,206, +20,115]` cycles. Causal reachability and eliminated
misses therefore do not produce a measurable handoff gain in this workload.

`analyze_sweep.py` regenerates `sweep_results.json` from the accepted numbered
samples and the earlier matched result. The raw timing logs include one extra
unrecorded warmup header; the analyzer admits only records explicitly labeled
`SAMPLE=1` through `SAMPLE=50`.

## Rejected correctness runs

- The first 32-line image booted the exact kernel but failed to execute
  `/bin/sh` and `/sbin/init` with error `-80`, then panicked. Its embedded Linux
  payload was byte-identical to the working 8-line image.
- A fresh-board 32-line retry reached the shell but stopped returning prompts
  during the benchmark ELF transfer. It was interrupted and power-cycled; no
  timing sample was recorded.
- The 12-line arm stopped returning prompts after 69 transfer commands and hit
  the native 360-second target-runtime limit (`BSG FAIL`).
- The 20-line arm transferred and hash-verified the ELF, completed four timing
  samples, then issued an errant write to physical `0x17bea8`. Its later runner
  `BSG PASS` is not an acceptance marker because the explicit errant-write
  error terminated the guest before sample 5.

These outcomes are not a monotonic count threshold: 8, 14, and two earlier
16-line batches completed, while 12, 20, and both 32-line attempts failed in
different ways. They demonstrate that the current replay mechanism is not yet
safe enough for additional performance tuning.

## Exact-image trace and trigger audit

`kernel8-disabled-traces.log` is a clean replay-disabled capture from the exact
kernel and benchmark above. It contains a complete full trace on attempt 2 and
complete source-to-peer and peer-to-source traces on attempt 1, followed by a
clean poweroff and terminal PASS markers.

The original trace model used kernel build `#7`; kernel build `#8` retains the
same relevant physical layout. Symbolization must account for the kernel's
`0x80200000` physical load address: for example physical `0x8023d480` maps to
virtual `sched_ttwu_pending`, not to the symbol at virtual offset `0x23d480`.

The Linux patch writes CSR `0x5c0` inside `__schedule` only after the next task
has been selected. Most of the old table's early wakeup and scheduler-selection
lines are therefore demanded before the hint can help. The 14-line tail table
covers the measured post-trigger privileged misses in both directions, but its
negative timing result closes further address/count tuning at this trigger.

## Architectural follow-up

The UCE suppresses duplicate detached requests only while their request slots
remain live. After the final response beat, the slot is released but the
completed line remains in the 16-entry frontend replay buffer. Every later
context switch therefore refetches and refreshes already-resident advisory
lines, temporarily making each refreshed entry incomplete and generating
unnecessary memory traffic.

The next implementation should expose completed-buffer residency to the replay
admission policy, or otherwise define a safe refresh/epoch protocol, and add
counters for resident drops, refreshes, completed hits, and demand delay. A
focused repeated-trigger test must prove stable execution and `fence.i`
invalidation before another Linux timing claim.

## Workflow guardrail

The first attempt to build 8- and 32-line firmware reused one OpenSBI output
directory. `make clean` deleted the seeded DTB, and a non-fail-fast loop
continued into missing-artifact errors; the later successful build logs
supersede those failed transcripts. All accepted firmware variants use
distinct output directories seeded with the exact DTB and fail before
packaging if `fw_payload.elf` is absent.
