# Conditional-prediction isolation experiment

This directory records a controlled experiment that disables conditional predicted-taken decisions while preserving unconditional-jump prediction, architectural branch resolution, explicit context redirects, and BTB/BHT reads and training. Its purpose is to determine whether speculative conditional redirects are necessary for the placement-sensitive FPGA handoff failure.

## Simulation gate

BlackParrot commit `d1186c793` passed the two-resident/four-logical-context `mt_ctxtsw_target_bypass_stress_test` after a clean trace-enabled Verilator rebuild. It retired the same 34,737 instructions as the predictor-enabled control and completed every register, loaded-target, and bitmap-target phase.

Disabling conditional prediction increased the six reported cycles-per-operation values, as expected because loop-closing conditional branches now resolve in the backend instead of redirecting speculatively:

| Phase / context | Predictor enabled | Conditional prediction off | Increase |
|---|---:|---:|---:|
| register / 1 | 7.75 | 12.08 | 55.9% |
| register / 2 | 12.31 | 15.69 | 27.5% |
| loaded / 1 | 12.31 | 16.16 | 31.3% |
| loaded / 2 | 16.06 | 19.95 | 24.2% |
| bitmap / 1 | 13.10 | 17.46 | 33.3% |
| bitmap / 2 | 17.05 | 21.44 | 25.7% |

Across the six phases, the summed cycles-per-operation figures rose 30.8%.
The absolute increment is much steadier than the percentages: 3.38--4.39 cycles per operation, averaging 4.03. The Linux demand workload has one loop-closing conditional branch per request, so a rough pre-run sanity projection is about 644,919 cycles, or 78.73 cycles/request, compared with the stable predictor-enabled median of 611,878 cycles and 74.69 cycles/request. This 5.4% projection is not a measurement; it separates the branch-resolution penalty from the memory-dominated request time and provides a check on the eventual physical result.

## Waveform confirmation

`analyze_prediction_decisions.py` checks the combinational BTB decision on every sampled core cycle in paired predictor-enabled and prediction-disabled traces. The enabled control had 15,533 valid conditional predicted-taken candidates and drove `btb_taken` for all of them, in addition to 2,534 unconditional jump hits. The diagnostic trace encountered 5,927 such conditional candidates and suppressed every one, while all 3,279 unconditional jump hits still drove `btb_taken`. There were zero decision-equation mismatches across 385,960 enabled and 397,726 diagnostic cycles after predictor initialization.

The simulation establishes architectural viability and gives a cost bound for the diagnostic image. Predictor reads, metadata, and training remain active, so this experiment isolates only use of the conditional direction for speculative frontend redirection.

## Routed implementation

Job `20261004T094435Z-984a2727` built the correct two-resident, ten-logical-context endpoint at top-level commit `984a2727` and BlackParrot commit `d1186c793`. The package SHA-256 is `3e023f0dd0c6bbd18154d1328221d33b44a980c40fc7ac12e229709207bee622`; its bitstream SHA-256 is `f89badd0db6b789f33c2358df9134817478395be9020e142f27a4cef3d01e73a`.

The image passes routing and all DRCs with WNS `+1.900 ns`, TNS `0`, WHS `+0.023 ns`, and THS `0`. It uses 50,710 placed LUTs, 28,385 registers, 83.5 BRAM tiles, and 11 DSPs. Relative to the predictor-enabled control, this is 20 fewer LUTs, identical registers/BRAM/DSP, 0.372 ns more setup slack, and 0.007 ns less but still positive hold slack. The diagnostic therefore has effectively identical physical size and comfortably meets the same clock.

## Physical result

Both exact Linux placements hang in their first resident-demand warmup with zero completed samples:

| ELF | Loop PCs | Retired instructions | MTIME delta | Reported IPC |
|---|---|---:|---:|---:|
| formerly failing `90411570...` | `0x11e80` / `0x11ec0` | 593,360,848 | 210,910,019 | 0.351667 |
| formerly stable `e62165fa...` | `0x11f00` / `0x11f40` | 591,441,047 | 210,910,450 | 0.350529 |

Each run used a fresh board boot, the exact diagnostic bitstream, 4,096 requests per worker, a 300-second target watchdog, and a verified Linux NBF. The MTIME deltas differ by only 431 counts (0.0002%), and retired instructions differ by 0.32%, showing that both placements enter nearly the same continuing execution state rather than a global core or DDR deadlock.

This result rules out speculative conditional predicted-taken redirection as a necessary trigger for a hang, but it does **not** isolate the original placement-sensitive failure.

## Superseding simulation result

Later repeated-handoff simulation reproduced the failure with conditional prediction both enabled and disabled. The required boundary was a resident Sv39 relaunch whose speculative frontend context redirect was not accepted before the switch committed. The commit-time state-reset fallback carried the target PC, privilege, translation state, ASID, and hardware-thread ID in its operand payload, but the frontend did not mark that fallback as a thread-ID change. It therefore fetched the correct target PC with the previous physical register-bank tag.

BlackParrot commit `332ada47b` fixes that fallback tag and passes minimized, exact A/B, full-pressure, and independent switching regressions. The prediction-disabled FPGA failures are now confounded by this pre-existing bug and no longer establish that extra resolved-branch redirects caused the hang. A routed build with the fallback fix is the next physical discriminator. Detailed evidence is under `logs/translated-resident-relaunch-fix-20261004/`.
