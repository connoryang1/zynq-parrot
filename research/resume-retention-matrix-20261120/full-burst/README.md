This report consolidates the completed full-burst synthetic instruction-retention controls at two memory service latencies. It distinguishes demand-copy publication from useful retained capacity and checks the complete recorded prefix handoff-and-return endpoint. These are full-core simulator results, not Linux application gains or FPGA measurements.

All 16 runs pass their archived maintained guest/host acceptance gate and retain closed FSTs. Every run uses ELF SHA256 `0bc79caf23b8f6f4f16525f2b4332752f91f6e10aeb6ed882e1d7467a27a93ca`, unchanged 96-operation/checksum prefix code, and original NBF SHA256 `512e926c14328c323ab79ac64f34791a3642b3a49f5ab637e89b2c5629365ab6`. Only the reversible aligned NBF mode word changes among modes; each mode's patched NBF is identical across all four models.

| Control | 40-tick capture on | 40-tick off | 200-tick capture on | 200-tick off | Extra cycles at 200 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cold | 664 | 664 | 1,944 | 1,944 | 1,280 |
| Target warm | 197 | 197 | 357 | 357 | 160 |
| Source warm | 254 | 254 | 574 | 574 | 320 |
| Switch only | 111 | 111 | 271 | 271 | 160 |

Capture on/off differences are exactly zero at both latencies for every control. No confidence interval is inferred from these deterministic single-run cells. The timer covers the complete target prefix handoff and return, including refill/copy effects within that interval, but excludes target seeding, warm/oracle execution and final printing. Every complete architectural test also reaches its checked terminal result; the timer is not total process setup/runtime.

The model topology is explicitly **two physical resident slots and four logical contexts**, verified by each archived Verilator SV command's `BP_NUM_THREADS=2` and `BP_NUM_CONTEXTS=4`. This is the custom Zynq base configuration recorded in each session; simulator configuration is not substituted for physical FPGA elaboration proof. All four model revisions are BlackParrot `ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57`, with empty recorded BP diffs. The current root import later moved to the separate `2958` first-completed policy; this report hashes immutable `ffc9` Git objects instead of mislabeling current source as the older build. Off200 explicitly selects `/home/coyang/bp-linux-demand-copy-control` and records its exact nested sources. The first-completed policy is not measured here.

Capture engagement was audited in all eight capture-on traces. At both latencies, modes 0/1/2 accept 39 cached misses, copy 312 accepted beats through the registered stage, and publish 39 completed line epochs; mode 3 records 32/256/32. All traces show eight beats per line, at most 27 complete side entries, and zero provenance mismatches. Crucially, there are **zero side-only eligible cycles and zero consumed side-only fetches across every capture-on run**. Cold capture-off traces independently show parameter zero, no captured beats and no complete side entries; the other off modes execute the same respective archived binaries.

Both warm modes have all seven prefix lines complete in the side store at timed begin. All 50 timed prefix fetch responses use ordinary L1. At either latency, target-warm has one refill completion/eight copied beats crossing into the timed interval with no new miss accepted there; source-warm has two completions/16 beats and one newly accepted miss. Counter boundaries can intersect previously started refill tails. These observations establish working demand capture but no useful extra unique capacity in this workload. A physical 32-line copy store is not 32 guaranteed additional unique lines; warming gains cannot be attributed to side-store prefetch.

The cold AXI audits establish the controlled service timing:

| Property | 40 setting | 200 setting |
| --- | ---: | ---: |
| Accepted timed AR transactions | 8 | 8 |
| ARLEN / ARSIZE | 7 / 3 | 7 / 3 |
| Bytes per transaction | 64 | 64 |
| AR to first R offer, model ticks | 40 | 200 |
| AR to final R acceptance, ticks | 47 | 207 |
| Accepted within-burst beat spacing | 1 tick | 1 tick |
| R backpressure | 0 | 0 |
| Max outstanding AR, entire run / queue capacity | 1 / 4 | 1 / 4 |

BE and AXI clocks share the exact VCD handle; source connects both to `aclk`. Each cold window reads raw AXI lines `0x340` and `0x1000,0x1040,...,0x1180` once. The wrapper translates architectural physical DRAM addresses by XORing `0x80000000` and adding its configured DRAM base, so raw AXI addresses remain separately labeled. The full-burst cache-to-AXI bridge emits eight 64-bit beats per line, and the responder starts an independent absolute due time on each accepted AR while preserving response order and beat bandwidth. All 56 within-burst intervals are one tick; both traces end with no pending read or audit issue.

The cold increase is exactly `1,944 - 664 = 8 × (200 - 40) = 1,280` cycles, consistent with the eight serialized line requests. Queue depth four is available but no overlap beyond one outstanding request is demonstrated. The earlier minimal wrapper used 128 serialized single-word AR transactions for this cold path; its results must remain separate. Neither model's injected tick counts calibrate real DRAM latency, bandwidth, FPGA timing, or application performance.

[summary.json](summary.json) binds all four session manifests, distinct model binaries, build logs/commands, archived runner snapshots, source/diff identities and every run's ELF/NBF/log/acceptance/FST by SHA256. It also binds the ten compact capture audits, two AXI audits, immutable historical RTL/converter sources and parser/transport source hashes. Offline consolidation rechecked hashes, exact NBF patches, checksums, native timeout markers and all 16 recorded acceptance results. No new model build, simulator run, synthesis or board action was performed.
