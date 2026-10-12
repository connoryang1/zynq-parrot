This directory records the decisive physical bubble-placement matrix for the
ten-stream corruption and the matched two-stream performance cost. Every run
used the same hash-pinned 20 MHz bitstream and a fresh overlay load.

# Physical bubble matrix

| Run | Exact image behavior | Cycles |
|---|---|---:|
| original k10, repetition A | fail | — |
| compressed-branch encoding control k10 | fail | — |
| post-switch executed bubble k10, repetition A | pass | 72,038 |
| original k10, repetition B | fail | — |
| pre-switch executed bubble k10 | pass | 71,992 |
| body executed bubble k10 | fail | — |
| post-switch executed bubble k10, repetition B | pass | 72,033 |
| original k2 | pass | 19,262 |
| compressed-branch encoding control k2 | pass | 19,262 |
| post-switch executed bubble k2 | pass | 20,540 |

The original failure repeats, and moving the compressed jump without executing
the NOP does not change behavior. An executed cycle immediately before or after
the context switch repairs the failure, while the same cycle earlier in the
loop does not. The result therefore identifies a zero-gap switch-boundary race,
not compressed encoding or general loop-period sensitivity; it does not yet
identify the corrupting internal signal.

The physical k2 cost exactly matches the simulator projection: the bubble adds
1,278 cycles for 1,278 nonfinal handoffs, or 6.64%. Hardware remains 2.925x
faster than the 60,077-cycle demand baseline, versus 3.119x without the bubble.
`results.json` records identities, classifications, cycles, and transcript
hashes. `SHA256SUMS` verifies the ten raw board transcripts.
