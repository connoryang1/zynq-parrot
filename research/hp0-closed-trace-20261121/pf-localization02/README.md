This addendum localizes the advisory admission-to-publication increase in the same closed08/10 traces. It separates UCE acceptance, downstream request issuance, HP0 response and completed PF publication without rerunning a target or changing RTL, fixtures or the frozen21-test auditor. It supports a simulator-path explanation only.

All entries below are clock periods relative to that lane's actual advisory admission. D's half periods reflect its inverted local clock relative to HP0.

| Endpoint | I native | I N200 | D native | D N200 |
|---|---:|---:|---:|---:|
| PF FSM issue |2 |2 |2 |2 |
| Accepted UCE memory-forward request |3 |3 |3 |3 |
| Target HP0 AR acceptance |29 |229 |12.5 |212.5 |
| BP-facing first R offer/accept |30 |430 |13.5 |413.5 |
| BP-facing RLAST acceptance |37 |437 |20.5 |420.5 |
| UCE first PF reply accepted |44 |444 |27 |427 |
| UCE full PF reply accepted |51 |451 |34 |434 |
| Completed retained PF publication |85 |485 |68 |468 |

Each UCE receives eight accepted consecutive64-bit reply beats in both cases. Full reply to publication stays34 periods: dispatch/drain, ordinary-L1 resident-tag scan and retained-store publication do not acquire the extra400. Nor is there UCE submission deferral: accepted forward remains at+3. The added400 consists of200 **before target AR issuance**, followed by200 on the target's own HP0 response. No AW/B transaction overlaps this window, so a dirty-victim/write-ACK explanation is excluded here.

Three HP0 reads occur in order:637 is ordinary I demand PA0x8000b240,638 is I advisory PA0x80001000,639 is D advisory PA0x80012000. Separate UCE demand events identify637; explicit top-level address-remap signals verify all three PA/HP0 mappings with base0. RID0 alone is not used to identify their origin. The ordinary I request starts four periods before I admission; D admission itself also moves200 periods later relative to I admission while that ordinary demand is serviced.

The specific observed blocking gate is the shared L2 forward **word** stream. For637 it holds PA0x8000b250, its third word, selecting bank1 with `cache_pkt_v=2`, `cache_pkt_yumi=0` and `fsm_fwd_yumi=0`. The held interval grows11→211 periods. Consequently the following I advisory's bank0 header cannot advance through the shared forward pump until that prior line's remaining word commands are accepted. The same11→211 hold occurs at0x80001010 for the I advisory, delaying the following D advisory in bank0.

During these holds, the bridge has `read_rr_v=0`, `tag_fifo_ready=1` and `r_fence=0`. Actual compiled/traced bridge parameters are two cache DMA interfaces and two read tag slots. Thus this observed delay is **not** AXI credit exhaustion or an ordering fence. The bridge source drives ARVALID from read-RR valid, tag readiness and the fence; the missing DMA request is upstream. The controller source advances its current forward word only when the selected cache bank accepts it. This explains observed read serialization despite two L2 banks without asserting a platform-wide outstanding limit or the exact upstream buffer holding each queued header.

`localization.json` preserves exact events and address translations; `../lower-gate03/gate.json` preserves the blocked intervals/parameters. `verify.py` checks eight PF beats, all timings, the11→211 gate and no overlapping writes, and binds exact compiled controller/pump/hash/AXI-bridge source snapshots. Run it with `python3 research/hp0-closed-trace-20261121/pf-localization02/verify.py`. `../pf-localization01` preserves the rejected union-field selection preflight, before body decode. Literal upstream snapshot whitespace is retained for source hashes. No policy refinement is implemented and no CPU load-use, FPGA or application-performance result is inferred.
