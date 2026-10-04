# Translated resident relaunch fix

This directory records the minimized reproduction, cycle-level root cause, RTL correction, and simulation qualification for a repeated Sv39 resident-context failure. Large FST traces and binaries remain local; their hashes make each retained run identifiable.

## Symptom and reduction

The original six-epoch translated prefetch lifecycle stalled after its first successful epoch. A corrected error reporter showed that epoch 2 resumed the right PCs but used stale register values. Reducing the workload to two epochs, zero eviction lines, and one prefetch/load per context preserved the failure:

| RTL | Epochs | Operations/context/epoch | Result | Retired instructions |
|---|---:|---:|---|---:|
| predictor enabled, before fix (`3c8c16aca`) | 2 | 256 | FAIL | 65,048 |
| prediction off, before fix (`d1186c793`) | 2 | 1 | FAIL | 60,965 |

The one-operation failure completed epoch 1, then reported peer mismatch `1`, source sum `2`, and peer sum `0`. The expected source and peer values were `1` and `2`, respectively. Bare U-mode and one-shot Sv39 controls passed, proving that repeated translated relaunch was the missing trigger; cache eviction pressure and loop depth were unnecessary.

## Cycle-level cause

On the first switch to the peer, the frontend was ready in the token-creation cycle. It accepted the explicit context redirect and changed its metadata thread tag to physical bank 1 before the switch committed.

On the failing second launch, the traced sequence was:

| Relative cycle | Event |
|---:|---|
| 0 | Backend creates resident switch token for virtual context 1 / physical bank 1; frontend is not ready. |
| 1 | Backend records the pending target; no frontend redirect has been sent. |
| 2 | Switch commits and clears the pending token. |
| 3 | Architectural current context changes to virtual/physical `1/1`. |
| 4 | Commit fallback sends a state-reset redirect to target PC `0x1000`, but `redirect_thread_id_v` remains zero. |

The scheduler's first-target override tagged PC `0x1000` as thread 1. Starting at PC `0x1004`, frontend metadata still tagged every peer instruction as thread 0. The peer setup therefore wrote `a0`, `a2`, `t5`, and the address registers into bank 0. When source context 0 resumed, it observed the peer base `0x40004000` and accumulated the peer value `2`. Both logical and physical current-context registers had switched correctly; the corruption came from frontend instruction metadata selecting the wrong register bank.

Translation exposed the timing window because translated fetch/refill activity temporarily made the frontend unavailable. The failure was independent of conditional branch prediction.

## Fix

The backend already places the target hardware-thread ID in the commit-time state-reset command. BlackParrot commit `332ada47b` makes the frontend consume that field for state-reset commands and marks those commands as explicit thread-ID changes, just as it already does for the speculative context-redirect path.

## Validation

All runs used clean trace-enabled builds.

| Configuration | Result | Retired instructions |
|---|---|---:|
| Prediction off, 2 epochs, 1 operation, no eviction | PASS | 51,750 |
| Predictor enabled, 2 epochs, 256 operations, no eviction | PASS | 59,910 |
| Predictor enabled, original 6 epochs, 256 operations, 1,024-line eviction sweep | PASS | 101,124 |
| Predictor enabled, independent 128-turn register/load/bitmap target-bypass stress | PASS | 34,737 |

The medium predictor-enabled run is an exact A/B against the pre-fix 65,048-instruction failure. The full run restores the original translated cache/DTLB pressure, and the independent bypass test checks ordinary resident switching on the two-resident/four-logical topology.

Harness validation passed all 15 `check_run` unit tests and compiled the complete maintained test-program set. The unit suite must be invoked from `testing/`; an initial repository-root invocation failed during Python import discovery and ran no tests.

The clean trace-enabled switch-overhead control also exactly preserves the
previous accepted result: 5.13 cycles per resident switch, 9.26 cycles per
nonresident switch, and 4.13 incremental cycles for a nonresident handoff.
This shows that tagging the commit-time fallback does not add latency to the
ordinary fast redirect path. The guest and host both passed before the known
post-finish DPI teardown assertion; the maintained checker classified the run
as valid. Exact artifact hashes are in `switch-cost-control/SHA256SUMS`.

Routed job `20261004T152200Z-510b853e` is building the two-resident/ten-logical
`e_bp_unicore_zynqparrot_prefetch10_cfg` image containing `332ada47b`. The exact
formerly failing and stable Linux workload placements remain the physical
acceptance test. Until they pass, this fix is proven for the simulation failure
but is only a candidate explanation for the intermittent FPGA lifecycle failure.
