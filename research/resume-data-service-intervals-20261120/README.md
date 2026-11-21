This tool describes accepted D-cache miss/refill service intervals from an already closed, fully audited event stream. It is intended to locate service activity for a later fixed-footprint40-versus200 comparison. It measures neither CPU stalls nor a critical-path fraction, and makes no counterfactual speedup or FPGA projection. Only the CLOSED32KiB/40-tick case was read; the active200 run/log/trace was not inspected.

Each `reference` with `outcome=miss` is paired by physical64-byte line with eight distinct one-hot `fill_beat` masks and its coincident final-beat `fill_complete`. Repeated misses to the same line after completion receive distinct IDs. Duplicate/unmatched/partial fills, inconsistent ways, ambiguous same-line pending misses, backward chronology, invalid addresses/masks, changed clock/global-counter offsets and source-audit count differences fail closed. All references, loads/stores, misses/hits, fill beats/completions, evictions and request-marker counts are checked against the passed upstream audit. Target references must lie in the actual actor's unaligned corpus byte bounds and declared warm/timed phase.

“First response” means the **first accepted D-cache fill beat**, not an AXI R offer, critical-word timestamp or load-ready timestamp. For the first recorded store miss at `0x8008bff0`, the requested64-bit word is6 within line `0x8008bfc0`, while the first fill mask16 denotes word4. First beat therefore cannot be assumed to map to the requested word. The interval starts at accepted miss request, omitting earlier issue/pre-acceptance waiting; its end is accepted full-line completion, which can follow useful data return. Queue/UCE/hierarchy/transport/service timing is not separated. I-side interference, memory-only latency and CPU blocked time cannot be attributed from these events.

Intervals use physical core-global cycles and half-open `[miss, completion)` bounds. The tool verifies a constant `domain_edge-global_cycle` offset separately for D-cache and BE events; observed offsets are1241/1242, consistent with the upstream opposite-edge clock sampling. Timed-ring unions clip **all** pending intervals at both boundaries, including potential carry-in/out, rather than selecting only misses accepted inside the window. Full latency distributions for accepted-in-window misses remain distinct from clipped occupancy. Individual-duration sums, union lengths, multiplicity excess, cycles with at least two pending intervals and maximum depth are reported separately. None is labeled or divided into a CPU stall/critical fraction.

The closed40 result pairs exactly **6,508 misses,6,508 complete refills and52,064 accepted beats**. The full stream has61,885 normal cached references:55,377 hits and6,508 misses, with28,089 loads and33,796 stores. All5,996 upstream eviction records are retained in the count checks.

| Scope | Misses | First accepted beat: median (min–max) | Full completion: median (min–max) | Pending-to-first union | Pending-to-complete union |
|---|---:|---:|---:|---:|---:|
| Entire program |6,508|61 (9–120)|69 (16–128)|466,715|514,110|
| Timed ring, clipped |1,711|61 (9–77)|69 (16–85)|103,799|116,711|
| Timed target misses |1,680|61 (61–77)|69 (68–85)|102,524|115,193|

The actual timed bounds are `[1,274,357,1,705,489)`, with printed complete-ring interval431,132 cycles. Latency columns are full differences for misses accepted in the selected scope; timed union columns are clipped to the window. Actual pending depth peaks at1; overlap, carry-in and carry-out counts are zero in this trace. Their handling is nevertheless tested with overlapping, touching, zero-length and boundary-crossing synthetic intervals. The timed-target subset remains separate from the31 other timed misses. The pending-cycle totals above are service occupancy descriptions, **not** cycles that an optimization would save.

Thirteen synthetic tests pass: rotated beat order, distinct/repeated line pairing, duplicate/unmatched/incomplete fills, way/mask/address/clock/count errors, target subset, two clock domains, overlap/multiplicity, carry-in/out clipping, exact boundaries and a zero-miss negative control. Distinct-line overlaps in synthetic tests exercise bookkeeping only; the validated actual D path has one outstanding normal miss. The initial test file had a syntax typo, corrected before any input analysis; no model or target ran.

Reproduction command for the retained closed40 inputs (new output directory required):

```sh
python3 -B research/resume-data-service-intervals-20261120/analyze.py --events research/resume-data-reuse-20261120/compact-thirtytwo-kib/dcache-audit/events.jsonl --guest research/resume-data-reuse-20261120/compact-thirtytwo-kib/guest-observations.json --audit-report research/resume-data-reuse-20261120/compact-thirtytwo-kib/dcache-audit/analysis.json --output research/resume-data-service-intervals-20261120/closed40
```

`closed40/{manifest.json,summary.json,misses.jsonl}` retain input/source hashes, descriptive summaries and every matched interval. `preparation.json` binds source/tests and frozen input provenance. For200, root may use the same tool only after whole execution and the upstream full tag/reference audit have closed successfully, keeping the footprint and exact program fixed. No200 service result is included here.
