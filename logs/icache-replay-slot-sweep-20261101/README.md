This directory preserves the focused simulation evidence used to bound how much a larger detached I-cache replay table can improve a 16-line burst. It is a UCE-only mechanism experiment and does not measure a Linux, full-core, or FPGA speedup.

# I-cache replay slot sweep

## Scope

The driver submits 16 distinct full-line replay requests to the production UCE through the side-buffer interface. It supplies ordered fixed-latency memory replies with four 128-bit beats per 512-bit line, holds the memory request path ready, and issues no architectural demand requests. The wrapper alone parameterizes the UCE replay table from four through eight entries; production RTL is unchanged.

The cycle count begins with the first accepted replay request and ends only after all 16 requests have issued, all four beats of every reply have completed, the replay table is empty, and UCE credits are empty. Every run also requires the observed maximum valid-entry count to equal the configured slot count.

## Results

| Fixed first-reply latency | 4 slots | 5 slots | 6 slots | 7 slots | 8 slots | 4-to-8 reduction |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 40 cycles | 233 | 233 | 191 | 191 | 149 | 84 |
| 80 cycles | 393 | 393 | 311 | 311 | 229 | 164 |
| 120 cycles | 553 | 553 | 431 | 431 | 309 | 244 |
| 160 cycles | 713 | 713 | 551 | 551 | 389 | 324 |
| 200 cycles | 873 | 873 | 671 | 671 | 469 | 404 |

All 25 parameter/latency combinations pass. The retained machine-readable output is `slot-latency-sweep.txt`; the latency-200 build commands, acceptance logs, dependency hashes, and artifact hashes are retained separately for each elaborated slot count.

The established detached-replay regression also passes after parameterizing the wrapper:

```text
python3 testing/rtl/run_uce_icache_replay.py \
  --side-buffer --out /tmp/zp-uce-icache-directed-a829
[UCE-ICACHE-REPLAY] PASS: detached retirement and resident same-line demand progress verified
```

## Interpretation

Completion is quantized into request waves: four and five slots are identical, six and seven are identical, and eight slots remove another wave. At the 40--80-cycle latency range most relevant to the short physical refill estimates, expanding from four to eight slots can save only 84--164 cycles for the entire 16-line burst in this deliberately favorable model. That is useful capacity headroom, but it is smaller than the 325-cycle FPGA wake-to-load gain already measured from moving the trigger earlier, and the synthetic result does not establish that the three residual FPGA demand misses are slot-limited.

Capacity expansion is therefore not the immediate implementation priority. The same-image selection-time control and an independent early-wakeup replication remain the decisive physical experiments; only evidence that residual misses are both useful and capacity-late would justify routing a larger table.

## Harness correction

The first burst-driver version began presenting replay traffic during the ten-cycle post-reset settling interval. Four slots could fill before the driver's initialization assertion, causing a false `UCE initialization failed`, while larger tables appeared to pass because they still had a free entry. An explicit `active` gate now holds traffic off until after initialization. All pre-fix results were discarded, every slot count was rebuilt with the corrected driver, and the full 25-point runtime sweep was repeated.

## Limits

This experiment excludes the controller table, resident queries, cache contention, architectural demand traffic, Linux, the core, and the FPGA. Replies are ordered, bandwidth is unconstrained except for the UCE response interface, and no cache retention or useful consumption is modeled. The cycle reductions are an optimistic UCE service bound, not an additive prediction for the Linux benchmark.

## Reproduction

Build one elaboration with:

```text
python3 testing/rtl/run_uce_icache_replay_burst.py \
  --out /tmp/zp-uce-burst-slots4-latency200 \
  --prefetch-slots 4 --response-latency 200
```

Repeat with `--prefetch-slots` 5 through 8. The built executable accepts the configured slot count and a runtime latency, which produced the retained 40, 80, 120, 160, and 200-cycle sweep without changing the elaborated design.
