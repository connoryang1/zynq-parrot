This is the first complete execution and full-access audit of the checked 1 KiB-per-actor lookup control. It validates a fitting working set and its complete access stream. It does not establish a Linux/FPGA speedup, useful larger-footprint capacity, or an implemented data-retention optimization.

The exact program completes all 64 requests/checks, custom PASS, CORE PASS and host BSG PASS. The maintained archived checker accepts the exact documented three-line GPIO shutdown exception after both PASS markers; the simulator's `-6` exit is not treated as a generic exception. The runner succeeds. The complete printed interval is **324,256 core-global cycles** for 32 timed requests and 32 hardware-context handoffs. Setup, eight warm rounds, checks and UART reporting are outside that interval, but the whole program must and did complete. No new target execution or model build was performed for this audit.

`fst2vcd` consumed the entire 5,647,908-byte FST to EOF with zero status and empty stderr. The frozen auditor and its current source/helper/tests are byte-identical. One run of that exact frozen code therefore validates both source identities; 14 focused auditor tests also pass. The trace samples actual D-cache/UCE edges opposite BE edges, validates BE-retired request labels separately, and joins them through the physical global counter. All four logical actors are observed executing target loads on both resident slots, consistent with the selected 2-resident/4-logical model.

| Check | Observed and verified |
|---|---:|
| Actual normal L1-D geometry | 64 sets × 8 ways × 64 B = 32 KiB |
| Initialized tag slots / validated synchronous tag-read rows | 512 / 33,293 |
| Complete request begin/end pairs | 64, exactly 16 per actor |
| Independently expected target loads, warm / timed | 5,253 / 5,381 |
| Target loads served by normal L1 | All 10,634 |
| Target ordinary misses, warm / timed | 0 / 0 |
| Full-program accepted cached loads / stores | 21,883 / 9,962 |
| Full-program normal hits / ordinary misses | 31,521 / 324 |
| Matched actual tag publications / complete normal refills | 324 / 324 |
| Matched fill beats | 2,592 |
| Actual valid normal-L1 replacement evictions | 0 |

Every per-context, per-epoch target-load count matches the independent generated-key/probe count in `trace-metadata.json`. Actual accepted tag writes, all eight-way synchronous read outputs, permission/hit vectors, accepted misses, eight-beat fills and complete notifications match throughout. There are no open requests or outstanding unmatched fills at EOF. All cached setup, stack, metadata and other traffic remains in the reconstruction; target ranges filter reporting only. The 726 accesses by another logical context into a corpus are retained as initialization/interference, not counted as that actor's request work.

Within the printed timed interval, **all 6,118 accepted normal cached references hit L1** (5,797 loads and 321 stores). All 324 full-program ordinary misses lie outside that measured ring interval. The 64 observed target-request lines are an access observation, not a claim that each request reads every allocated corpus byte; calloc byte bounds and shared boundary lines are preserved without alignment tuning.

The conditional exclusive-victim ledger admits only actual valid normal-L1 replacement victims, removes them on actual refills, and invalidates retained copies on stores/invalidation. It makes no prefetch/memory requests or oracle seeds. Since this trace has no actual eviction, every capacity remains empty:

| Additional victim lines | Nominal bytes | Peak entries | Covered ordinary misses |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 4 | 256 | 0 | 0 |
| 16 | 1,024 | 0 | 0 |
| 32 | 2,048 | 0 | 0 |
| 64 | 4,096 | 0 | 0 |
| 128 | 8,192 | 0 | 0 |

This is conditional fixed-execution address coverage, not rescheduled execution or retained-data correctness. The zero curve validates the fit negative control; it says nothing about opportunity at 32 KiB per actor, chase or codec. The source-level Amdahl distinction also matters: each request still performs 64 generated hash queries, mixes/remainders, probing and bookkeeping, and the complete interval includes handoffs. An avoided-miss count would not be an avoided-cycle count. This case has no measured-ring normal D miss for additional demand retention to remove; no counterfactual speedup is projected.

Exact bindings are in `manifest.json` and `summary.json`, with all 64 request details in `analysis.json` and the full ordered event stream in `events.jsonl`:

| Artifact | SHA256 |
|---|---|
| Compact fixed-256-KiB-heap ELF | `f35e5da8dcb527cfa04c16edab0616f1f80a7715c9b05278500799c9b66393dd` |
| Validated trace-filtered model | `77f76ae7527c2e9ed796fad48a8344e2dbbc10a5d90a69ccfb829e0bc2754ad5` |
| Complete FST | `a1bdedaf8809057ead080ae3cc7b8f70bc1b2d5b3e1f2cf35e45d015d79aaa59` |
| Request metadata | `67ff3d79bb12817a528917aa8dc5b55cc2c0bee567108451cd9a608aca7dd3db` |
| Full audit report | `ba4918145528cf26ec0ec506e5bafe568a21ecb60888a30f8399d13990325728` |
| Full ordered reference/fill/boundary event stream | `e6c796597b2e4240607a58b28ce45759aa9832dc7d3bb68f80fa9804e294c403` |

The manifest records the converter binary hash, exact converter/analyzer argv and a final unchanged-input rehash. Reproduction streams `fst2vcd runtime/dump.fst` to the frozen `analyze_resume_data_reuse_vcd.py` with `--metadata trace-metadata.json --output analysis.json --events events.jsonl`; never materialize a large intermediate VCD. The output paths must be new when reproducing retained evidence.

The model is the source-bound FFC full-burst capture-off40 copy, with configured first-response latency 40 model ticks, not a board DRAM projection. Earlier file-limit/native-timeout attempts remain failed. The root agent separately authorized a same-ELF 32 KiB case after this audit; no partial result from that active case is read or included here.
