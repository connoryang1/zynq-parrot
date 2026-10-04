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

The simulation establishes architectural viability and gives a cost bound for the diagnostic image. The decisive result remains the routed ten-context image running the exact formerly failing and passing Linux ELFs. If the failing placement becomes stable, conditional predicted-taken behavior remains implicated; if it still fails, speculative conditional direction is not necessary, although predictor metadata and training remain active and would require a separate isolation if later evidence points there.
