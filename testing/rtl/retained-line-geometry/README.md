This directory extends functional coverage of the frozen shared retained-full-line store near the FPGA capacity search boundary, and measures its own-lane interface service cost. It changes only test geometry: ordinary L1 I/D geometry and production RTL remain unchanged. Actual routed resource use and application benefit require separate evidence.

The backend is pinned to SHA256 `06dfafa133e612f214ea3cb5c5755505602984ed47ff6dac1a1af06afc4d7a4e`. Each configured slot stores a complete 64-byte payload. Slots can duplicate ordinary L1 content; physical slot count does not guarantee additional unique live capacity. The existing conservative same-set invalidation and epoch-wrap sweep remain unchanged, including their collateral capacity losses. The test uses two-bit epochs to exercise wrap without changing payload width; production defaults to eight bits.

`retained_line_geometry_wrapper.sv` and `driver.cpp` derive from the closed generic tests at top checkpoint `e8856516f2fb30b967a0cbaa2fc83d46efdc9b9f`; `derivation.json` records the exact before/after source hashes. Their geometry-dependent fixtures now use `RETAINED_SETS`, while every payload remains eight 64-bit words. Physical addresses are a deterministic enumeration of every configured slot, not a workload address table or tuning experiment.

The runner covers these **new** configurations, sequentially, with clean TRACE/FST models under both inverted clocks and genuinely different lane periods:

| Retained sets | Actual lines I/D | Reason |
|---:|---:|---|
| 64 | 1344/1344, 1408/1408 | Missing points beyond the existing 1024/1280/1320/1536 gates |
| 256 | 1280/1280, 1320/1320, 1344/1344, 1408/1408, 1536/1536 | Same payload capacity, shorter serial tag scans; includes partial final ways |
| 256 | 0/0 | Disabled ports preserve exact response/terminal ownership |
| 256 | 259/517 | Unequal partitions and partial final ways, plus coherence and wrap |

Every nonzero slot is inserted, then queried at a nonzero within-line byte offset with all 512 output bits checked. Additional fixtures exercise full physical tags above bit31, no-replace refusal, replacement/refresh, disjoint independent-port writes, same-set collateral invalidation, pending and stalled response revocation, partial insertion cancellation, final-word invalidation, clear during owned operations, and epoch wrap. Every accepted lookup produces exactly one consumed response and every accepted insertion exactly one terminal pulse. Zero-capacity behavior and unequal partitions are separately checked.

Previously closed sets64 capacities1280/1320/1536 are reused through their existing FSTs and source-bound manifests; no redundant models are built. Existing sets64 zero/unequal-partial gates remain in `../retained-line-store/evidence/`. A reused trace must match its recorded SHA and source snapshots and have a completed unit log. The new parser independently checks all capacity-prefix addresses, accepted insert payloads, hit outcomes and full response payloads, plus total handshake ownership counts against the closed manifest. It requires successful converter EOF.

`service.py` samples selected signals **before each actual rising edge of the corresponding lane clock**. Service is the difference in own-lane edge numbers between accepted request and accepted response, or between accepted insertion and the edge observing its terminal pulse. Response ready is asserted throughout the capacity prefix; later cancellation/backpressure tests are excluded from the service histograms. These costs include the endpoint handshake edge. They are not first-combinational-valid time, ordinary cache hit latency, CPU cycles, application execution time, memory response latency, synthesized frequency, or a performance prediction. Histograms retain all slot positions; the single full-set miss fixture selects set0 and is labeled accordingly.

Run host tests without building a model:

```sh
python3 -m unittest discover -s testing/rtl/retained-line-geometry -p 'test_*.py' -v
```

The child agent cannot see the root's host RAM worktree. The parent executes this new-directory-only, bounded command, with at least512MiB RAM and48MiB durable headroom:

```sh
python3 testing/rtl/retained-line-geometry/run.py \
  --work /dev/shm/zp-retained-geometry-boundary-20261121 \
  --archive /home/coyang/zynq-parrot-linux-capacity/testing/rtl/retained-line-geometry/evidence/boundary-01
```

`--case 256:1280:1280` admits a single first gate if desired. Objects and executable remain in RAM; source snapshots, logs, original closed FSTs, SHA-bound manifests, and independent service reports are small durable evidence. Build timeout300s, run timeout120s per clock mode, audit timeout240s; file-size cap64MiB per process output. Existing output directories are rejected rather than retried or overwritten. No RTL elaboration result is accepted merely because a prior executable exists.

The initial reused-trace analysis failed because the system Python3.8 does not support dictionary union. This affected analysis only and was corrected to a dictionary copy/update; no model or backend ran or changed for that failure. `evidence/reuse64-1280/attempt.json` preserves it. The subsequent reused1280 audit passed both clock modes. All nine new models then passed both clock modes in the parent host-RAM execution; no model was executed by the child. The closed results below supersede the earlier preparation-only status.


All nine new models and their18 traced runs passed; the six reused traces also passed independent service audits. Across12 geometries/24 closed clock runs, every one of56,656 capacity-prefix slot reads returned the expected full64B payload. The new cases include zero/zero and unequal259/517 slots at sets256. `evidence/closed-comparison.json` retains every service histogram and binds all manifests, source snapshots, raw FST hashes, complete logs, converter EOF status, and post-audit receipts. Raw FSTs remain locally retained and ignored by Git; their hashes and sizes are committed. No cleanup was performed by this agent.

Observed own-lane cycles are identical for both lanes and both clock arrangements. Each hit column gives min/median/max across **every slot**; insertion covers every initial full-line capture. Miss is the single full-set0 fixture after replacement; the initial empty-set fixture has the same count. It is not an average workload miss.

| Lines per side | Payload bytes per side | Sets64 hit | Sets256 hit | Sets64 miss | Sets256 miss | Sets64 insertion | Sets256 insertion |
|---:|---:|---:|---:|---:|---:|---:|---:|
|1280|81920|12/31/50|12/16/20|41|11|50/50/50|20/20/20|
|1320|84480|12/32/52|12/16/22|43|13|50/52/52|20/20/22|
|1344|86016|12/32/52|12/16/22|43|13|52/52/52|20/20/22|
|1408|90112|12/33/54|12/16/22|45|13|54/54/54|20/22/22|
|1536|98304|12/35/58|12/17/22|49|13|58/58/58|22/22/22|

These measurements expose the frozen backend's serial per-way tag scan. Sets256 reduces maximum ways at the same full-line payload count, while increasing per-set epoch/replacement metadata. This functional tradeoff still needs synthesis and routing to price resource and timing costs. Retained indexing and collision behavior also change, so these histograms do not establish an application optimum. Coarse same-set invalidation can remove additional retained lines and an epoch wrap still sweeps the partition.

Reproduce the **read-only** hash review and table without running any model:

```sh
python3 testing/rtl/retained-line-geometry/summarize.py
```

Fourteen host tests passed before the model sequence. No additional tests, RTL edits, model reruns, synthesis, or board activity were performed for this closed-result review.
