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

Selected-signal FST decoding confirms that the exact failing mechanism, rather
than an incidental timing change, was repaired:

| Trace | Workload fallback time | Thread-tag valid | Selected physical thread |
|---|---:|---:|---:|
| Prediction off, minimal, before fix | 34,108,925,000 | 0 | 1 carried but ignored |
| Prediction off, minimal, after fix | 34,108,925,000 | 1 | 1 |
| Predictor enabled, 256 operations, before fix | 34,249,275,000 | 0 | 0 |
| Predictor enabled, 256 operations, after fix | 34,249,275,000 | 1 | 1 |

The event times are identical within each A/B pair. The fixed reduced run has
one workload state-reset fallback and tags it correctly; the larger full-pressure
run passes but takes no workload fallback after boot, so it is broad regression
coverage rather than direct coverage of this path.

Harness validation passed all 15 `check_run` unit tests and compiled the complete maintained test-program set. The unit suite must be invoked from `testing/`; an initial repository-root invocation failed during Python import discovery and ran no tests.

The clean trace-enabled switch-overhead control also exactly preserves the
previous accepted result: 5.13 cycles per resident switch, 9.26 cycles per
nonresident switch, and 4.13 incremental cycles for a nonresident handoff.
This shows that tagging the commit-time fallback does not add latency to the
ordinary fast redirect path. The guest and host both passed before the known
post-finish DPI teardown assertion; the maintained checker classified the run
as valid. Exact artifact hashes are in `switch-cost-control/SHA256SUMS`.

## Physical FPGA acceptance

Routed job `20261004T152200Z-510b853e` built the two-resident/ten-logical
`e_bp_unicore_zynqparrot_prefetch10_cfg` image containing `332ada47b`. Full
timing signoff passes at WNS/TNS `+1.462/0 ns` and WHS/THS `+0.022/0 ns`.
The design uses 50,700 LUTs, 28,385 registers, 83.5 BRAM tiles, and 11 DSPs.
The verified package and bitstream SHA-256 values are
`9a3e4b8e9bacfa2a323633759246d513519b2e438c563abc219c7350b6472237`
and `2ab6ec08860d07fe627ef079090a76c0604e1d6b40d4003fa9f5dd3a1fc8488b`.

Fresh-boot physical runs used the exact Linux NBF and ELF identities recorded
under `fpga/`. The `0x11e80`/`0x11ec0` placement that previously hung in its
first warmup now passes warmup, all 128 samples, native request exit zero,
`CORE[0] PASS`, and runner exit zero. Its median is 611,716 cycles for 8,192
requests, or 74.672 cycles/request. The independently booted stable
`0x11f00`/`0x11f40` control also passes 128/128 at a 611,074.5-cycle median,
or 74.594 cycles/request. The formerly failing placement is only 0.105% slower
by difference of medians, while the control is 0.131% faster than its prior
611,878-cycle median. Thus the state-reset thread-tag correction resolves the
physical lifecycle failure without a measurable switch-path or workload-level
performance regression. Exact distributions and log hashes are preserved in
`fpga/board-analysis.json`.
