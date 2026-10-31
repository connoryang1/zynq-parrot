This directory records the first matched FPGA timing experiment for the conditional Linux instruction-replay trigger. It separates valid source-to-peer measurements from overflow samples and from an invalid later packaging attempt so the result can be reproduced without overclaiming a Linux speedup.

# Conditional Linux prefix replay

The selected routed design is top-level `3a08584d` with BlackParrot `b1a065281`; the bitstream SHA-256 is `e1e66020...2338`. Both accepted arms embed the same Linux payload (`173a4fea...f5de`) and differ only in OpenSBI replay enablement. Linux executes `csrw 0x5c0, zero` only inside `if (likely(prev != next))`, after `pick_next_task()`.

The four replay targets are the first four distinct instruction lines demanded after that trigger in a fresh replay-disabled source-to-peer trace. Their addresses and selection policy are retained in `targeted-prefix-results.json`.

## Matched seven-sample batches

Each arm used a fresh power cycle, readiness wait, hash-checked overlay and NBF, one unrecorded source-to-peer warmup, and seven recorded source-to-peer handoffs. The trace program used `--summary-only`, which preserves the recorder header, overflow status, and pass/fail result without printing hundreds of records.
The exact measurement ELF has SHA-256 `14bf2ab9c232d5c71c21a6204c3dfaa6ee42e3e949d63d994168b1a84da1bf4d`.

| Arm | Non-overflow elapsed cycles | Median | Overflow samples |
| --- | --- | ---: | ---: |
| replay disabled | 12,779; 14,707; 12,631; 11,115; 12,672 | 12,672 | 2/7 |
| targeted four-line replay | 18,332; 13,705; 13,162; 11,348; 38,613; 11,110 | 13,433.5 | 1/7 |

The accepted non-overflow median changes by `+761.5` cycles, or `+6.0%`, with replay enabled. Thus the four-line policy does **not** demonstrate an end-to-end speedup. Earlier full traces show that the selected lines disappear from replay-enabled demand-miss records while three of them appear in the corresponding disabled trace, so replay can cover the intended misses; that mechanism-level success is insufficient to reduce this noisy handoff interval.

Primary transcripts and extracts:

- `raw/target4-summary7-local.log`: `3d2bbc8a...05397`;
- `raw/target4-summary7-extract.log`: `0976b3bc...46c2`;
- `raw/disabled-summary7-local.log`: `2db16104...ff3b`;
- `raw/disabled-summary7-extract.log`: `adf80e3d...bb7c`.

## Rejected two-line follow-up

A two-line OpenSBI-only rebuild produced NBF `10d77bbd...ffb4`, but it booted the normal `/init` path rather than the comparator images' direct `/bin/sh` path. The canonical SDK's current DTB/rootfs state therefore did not reproduce the exact accepted payload. No benchmark was run and no two-line performance result is claimed. `raw/target2-invalid-packaging.log` (`f17dac19...3fd9`) retains the cleanly terminated boot; an exact payload/DTB reconstruction is required before retrying this comparison.

The first incremental OpenSBI invocation also selected the host compiler because `CROSS_COMPILE` and the Buildroot toolchain path were omitted. That command failed before producing an artifact; subsequent direct OpenSBI builds must set both explicitly and must still verify the embedded payload and boot arguments before board use.
