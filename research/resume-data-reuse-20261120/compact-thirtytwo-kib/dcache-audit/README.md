This complete offline audit accepts the checked **32 KiB-per-actor lookup** execution on the source-bound FFC model with two resident slots, four logical actors and a normal **32 KiB L1 D-cache**. It validates all 64 requests and independently generated load counts, the custom completion marker, CORE PASS and host BSG PASS. All actors execute target loads on both resident slots. It provides conditional address coverage only, with no Linux/FPGA performance, prefetch-benefit, rescheduled-execution or retained-data correctness claim.

The complete printed interval is **431,132 core-global cycles**, including 32 timed requests and 32 handoffs. Its 1 KiB fit control reports 324,256 cycles, 6,118 timed normal L1 hits, 5,381 timed target hits and zero replacement evictions. The two footprints have different probe/load counts and computation; their ring-time difference cannot be attributed solely to cache capacity.

`fst2vcd` consumed the entire **11,767,177-byte closed FST** to EOF with return code0 and empty stderr. The current analyzer/helper/tests match their frozen copies byte for byte; copies are retained in `source/`. The frozen auditor passed all105 required signals and 14 focused host tests. It reconstructs tags only from actual masked SRAM writes, checks synchronous tag reads and accepted demand hit vectors, and matches every normal miss to a tag publication and complete refill. The Dcache/UCE and BE retirement clocks are sampled separately and joined through the physical global counter.

| Full-program validation | Count |
|---|---:|
| Initialized actual normal tag slots | 512 |
| Validated synchronous tag-read rows | 70,757 |
| Accepted cached references | 61,885 |
| Loads / stores | 28,089 / 33,796 |
| Normal L1 hits / ordinary misses | 55,377 / 6,508 |
| Matched tag publications / complete refills | 6,508 / 6,508 |
| Matched unique normal refill beats | 52,064 |
| Actual valid-line replacement evictions | **5,996** |

All32 warm target requests contain **5,320 loads: 3,600 hits and1,720 misses**. All32 timed target requests contain **5,266 loads: 3,586 hits and1,680 misses**. The complete printed timed interval also includes bookkeeping, stack and handoff references: **6,003 references, 4,292 hits and1,711 misses**, with1,711 actual replacement evictions. Full-program access extraction includes initialization and every other cached reference as interference; target filtering applies only to the reported actor request work.

The exclusive FIFO victim ledger starts empty and admits only **observed valid baseline L1 replacement victims**. It removes entries on actual normal refills and invalidates copies on stores and invalidation. A covered event must be an ordinary miss whose line is absent from actual L1; no resident duplicate receives credit. These nominal capacities are additional hypothetical victim storage, not the accepted FPGA advisory store.

| Additional victim lines | Bytes | Warm target misses covered /1,720 | Timed target misses covered /1,680 | All timed-interval misses covered /1,711 | Full-program misses covered /6,508 |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | 256 | 6 | 5 | 5 | 32 |
| 16 | 1,024 | 24 | 20 | 25 | 135 |
| 32 | 2,048 | 53 | 39 | 51 | 269 |
| 64 | 4,096 | 98 | 99 | 115 | 526 |
| 128 | 8,192 | 192 | 207 | 230 | 907 |

These counts condition on the exact baseline access sequence and cache transitions. They do not include a victim lookup's latency/area, changed replacement/execution, coherence implementation or target data correctness. A covered miss is not a saved-cycle estimate. The model's configured first-response latency is40 model ticks; it is not a measured board DDR latency.

`analysis.json` retains all64 request windows and counts; `events.jsonl` retains the complete accepted-reference/fill/eviction stream. `summary.json` independently cross-checks event totals, per-epoch counts, conditional coverage and printed ring boundaries. `manifest.json` binds the ELF, runtime NBF/config, model/admission, FST, metadata, log, source/helper/tests, checker, exact argv, exit codes and unchanged-input rehash. Source proofs for FFC tag/fill decisions remain in the bound prior observability evidence.

An initial host-check invocation incorrectly supplied a benchmark selector unsupported by the archived checker. Its rejected argument log is retained as `checker-unsupported-selector.log`; this did not reject the trace or execute any target. The supported common checker subsequently passed, as did a separate exact frozen compact guest parser and regeneration of the expected target-load metadata. The sole documented post-PASS GPIO shutdown exception is accepted for simulator exit-6; no generic nonzero-exit exception is introduced.

Reproduce to a **fresh output directory** with `python3 -B reproduce.py --output-dir /path/to/new-audit` from this directory, then run `python3 -B summarize.py --audit-dir /path/to/new-audit`. No intermediate VCD is written and no model/board execution occurs. The audit adds evidence and scripts only; maintained analyzer/test/workload sources are unchanged.
