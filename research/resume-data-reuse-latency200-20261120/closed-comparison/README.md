This comparison measures controlled memory first-response sensitivity of a complete, checked hardware-context ring at one fixed 32KiB private lookup corpus per logical context. It compares two closed full-burst Verilator runs, not Linux execution or FPGA performance, and does not evaluate an implemented prefetch optimization.

Both runs use the exact ELF `f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd` and patched NBF `18dbba12d432e6cfde94e7a16887d52f4e6edf0114b21a4fd227c0fbe4bc103d`. Corpus bases, actual byte bounds, checksums, 16 independently verified requests per actor, stack bases and request metadata match. There are four logical contexts on two resident slots, eight warm and eight timed rounds, 32 timed requests/handoffs, a fixed 256KiB heap and normal 32KiB L1-D (64 sets × eight ways × 64 bytes). Both models use FFC source `ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57`, capture off, one L2 bank and the same full-burst transport. The physical reference has two L2 banks. The controlled first-response setting changes from 40 to 200 model ticks; transfer scheduling and the other configured settings remain fixed. Native wall guards of 1800/2400 seconds permit completion and are not measured performance.

| Complete audited metric | 40 ticks | 200 ticks |
|---|---:|---:|
| Complete timed ring, core-global cycles |431,132|705,445|
| Timed normal references / hits / misses |6,003 / 4,292 / 1,711|6,003 / 4,292 / 1,711|
| Timed target loads / hits / misses |5,266 / 3,586 / 1,680|5,266 / 3,586 / 1,680|
| Entire-program misses / full refills / beats |6,508 / 6,508 / 52,064|6,508 / 6,508 / 52,064|
| Actual valid L1 replacements |5,996|5,996|
| Timed accepted-miss → first accepted D-fill beat, median |61|221|
| Timed accepted-miss → full D-fill completion, median |69|229|
| Timed clipped pending-to-first-beat union |103,799|378,046|
| Timed clipped pending-to-completion union |116,711|390,958|

All 105 required signals, all initialized tags and subsequent tag reads, hits, accepted references, refills and all 64 request boundaries pass the frozen full-access audit. Converter EOF is clean in both cases. The complete custom checks, CORE and BSG PASS signatures are present; the archived checker admits only the known post-PASS GPIO shutdown signature despite simulator exit -6. The runner itself exits zero. The timed accepted-reference semantic sequence is identical; all 6,508 miss addresses/actors/operations, selected ways and rotated mask sequences match. Entire-program normal references differ by two post-timed cached loads/hits (61,885 versus 61,887); the first reference-order difference is after each timed end. We therefore do not claim identical entire-program access streams.

The complete ring increases by 274,313 cycles. The union of timed accepted-D-miss-to-completion intervals increases by 274,247. Of 1,711 matched timed misses, 1,675 intervals grow by 160 cycles, 12 do not change, and 24 grow by more than 160; all relative accepted-beat schedules are unchanged. Multiplying 1,711 by 160 gives 273,760, leaving an arithmetic difference of 553 from the ring delta. The difference between the ring delta and pending-union delta is 66. These are numerical co-movements, **not** an exclusive causal partition: pending occupancy is not CPU blocked time, first D-fill beat is not necessarily critical-word/load-ready time, and shared I-side, UCE, hierarchy and queue timing have not been isolated. No residual is assigned to compute or I-side work. Both traces have maximum normal-D pending depth one, zero overlap and no timed carry-in/out.

Conditional exclusive FIFO victim ledgers also match at every tested capacity. Extra lines 0/4/16/32/64/128 cover 0/5/20/39/99/207 of the 1,680 timed target misses; entire-program coverage is 0/32/135/269/526/907. These are fixed-execution coverage diagnostics with actual replacements and store invalidation, not implemented capacity, replay effectiveness, avoided stalls or projected speedup. They suggest limited coverage from a small generic victim store for this lookup stream. They establish neither general D-cache capacity across workloads nor an accepted optimization.

`results.json` retains exact source, model and input hashes, full per-capacity counters and paired distributions. Reproduce the comparison without executing a target:

```sh
python3 -B research/resume-data-reuse-latency200-20261120/closed-comparison/compare.py
```

The unchanged service analyzer's 13 synthetic tests pass, including strict pairing, rotated beats, duplicate/unmatched/partial fills, address/way/clock/count checks and interval overlap/boundary clipping. See `../../resume-data-service-intervals-20261120/closed200/README.md` for its separate reproduction command and first-beat definition. `source-hash-audit.json` binds retained inputs and outputs; large raw FST/ELF/NBF files remain at their manifest paths and are not added to Git. No model, RTL or program was rebuilt or rerun for this analysis.
