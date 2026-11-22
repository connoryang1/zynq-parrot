This records the actual standalone production-options mapping outcome for the full-payload15-cell store and its matched1792-line canonical control. It preserves the negative area result so future storage changes can be judged against measured resources rather than raw bit arithmetic.

| Same wrapper and constrained synthesis | LUT | FF | BRAM36 tiles | DSP | Native seconds |
|---|---:|---:|---:|---:|---:|
| Exact8df canonical1792/side |1142|2211|56|0|156.40|
| Exactb12 packed1792/side |2617|2375|54|1|329.37|
| Exactb12 packed1911/side |2256|2367|56|1|280.35|

The packed1792 case saves two standalone BRAM tiles while adding1475LUT and164FF; it does not solve the current logic-limited whole-device placement failure. Packed1911 holds more complete64-byte lines at the same56tiles as the1792 canonical control, but its controller costs remain materially higher. Neither result demonstrates whole-chip fit, mapped functional equivalence or an application benefit.

All three actual commands completed0 on blackparrot1; every arm began with an empty vendor inventory, ownership ended RELEASED with no remaining owned group, and no board action occurred. The source-bound wrapper has I invalidation/address tied0, D invalidation variable and all other client ports live, PA34/sets256/epoch8. Vivado2024.2 AreaOptimized_high/global_retiming on/control-set threshold1, opposite50ns clocks and xc7z020clg400-1 are identical across arms.

Actual packed1792 RAM ports are48RAMB36E1 with9-bit A/B, four with18-bit A/B, and two with36-bit A/B, all READ_FIRST on both ports. Packed1911 is56RAMB36E1 with9-bit A/B, both READ_FIRST. These are depth/width decompositions of two36-bit logical ports; raw cell arithmetic alone did not predict their surrounding mux cost. Separate validity storage maps to LUTRAM, and the canonical D epoch RAM retains its distributed mapping. Macro and nested primitive rows overlap and must not be summed as physical sites.

The single DSP48E1 `storage/p_0_out` is concrete evidence for a narrow remedy: its constantB is36, while A is the word/control-derived p_4_in[2:0] followed by0. This is wide word×72 slice/index logic, not an evidenced line×15 address multiplier. Raw response-named groups also contain extra logic/retiming registers, but naming does not establish exclusive cones or additive savings. A separate fixed-slice/typed-index prototype is pending new component/mapping gates; this curation contains no result for it. The alternate SP72/parity-banked layouts remain unimplemented hypotheses.

`review.py --external` independently rehashes every artifact against the closed acquisition receipt and every uploaded source against its admission, recomputes report totals/physical RAM and DSP counts, and checks completion/ownership. `review.json` is the resulting closed proof. Local snapshots preserve exact sources/reports/primitive tables/protocol; DCP and full functional netlists remain externally SHA-bound at `/home/coyang/fpga-artifacts/linux-cell36-mapping-20261122-02/run01`. `review.py` without arguments checks the portable lossless curation. Prior b12 twelve functional runs, separate read-only correctness closure and original operational trace-budget failure retain their distinct statuses.
