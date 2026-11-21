This records closed-trace HP0 timing and response-integrity checks for native08 and delay200 whole-core run10. It preserves actual request/response events, exact source snapshots and host auditor tests without running another model or target. These are simulated-path timing checks, not physical memory calibration or an application performance comparison.

Both accepted audits observe648 read bursts,5184 R beats and487 AW/B transactions after AXI reset, including loading/setup traffic. Every AR has RID0, ARLEN7 and ARSIZE3: eight64-bit beats. Counts therefore describe the whole observed trace rather than an application-only interval.

| Observed endpoint, AXI cycles | Native08 | Run10 external, before shim | Run10 BP-facing, after shim |
|---|---:|---:|---:|
| AR acceptance to first R offer/accept |1 |1 |201 |
| AR acceptance to RLAST acceptance |8 |8 |208 |
| AW acceptance to B offer/accept |12 |12 |212 |
| WLAST acceptance to B acceptance |1 |1 |201 |
| Consecutive R acceptance spacing within bursts |1 |1 |1 |

All5184 R payloads and487 B payloads in run10 preserve **every** ID/data/response/LAST field and stream order, with first offer and acceptance exactly200 cycles after external acceptance. Thus the complete eight-beat response stream shifts by200; the delay is not restarted serially for each word. No response errors or held-payload violations occur. N is response age since shim acceptance, not AR-to-DRAM service or a load-use latency.

Actual run10 queue peaks are R8/B1, with no full queue, input stall or downstream stall. Both whole-core traces observe at most one outstanding read and one outstanding write; read/write requests can overlap, giving combined peak2. This is fixture coverage, **not** a platform concurrency limit. Multiple-read/multi-ID/same-ID overlap, backpressure and512-entry saturation are exercised only by the21 host auditor fixtures here; RTL shim component evidence is separate. The common path checks all observed HP0 responses, without identifying I/D/prefetch by shared RID0.

FST resolution is1ps and the observed AXI period is50,000ps. I-UCE's positive clock shares AXI's exact trace handle; D-UCE uses the inverted local clock. In these models,200 AXI cycles correspond to200 core clock periods. That does not calibrate any physical FPGA or future CPU frequency.

Separate UCE observations contain44 completed I and48 completed D ACK bursts per case, with no unfinished requests. The retained target request reaches its first L1 ACK in14 clock periods and its full eight-word ACK completion in21 in both cases. These are packet endpoints, not architectural data readiness or application benefit. I advisory admission-to-publication is85/native and485/delayed periods; D is68 and468. Those intervals include the complete upstream path and resident scan; they are not independent DRAM latency measurements. Normal lower-path requests are kept separately from retained-fill state22, and are not classified as HP0 misses solely from UCE state.

Native08 predates the new shim integration; run10 contains it with static200. The exact different sources/models are bound, and this pair is used to verify interface behavior, **not** a matched optimization effect. Future baseline/optimized application comparisons must bind the same integrated source, geometry, N and runtime inputs. The old41-cycle dependent-load result and the closed40/200 pipelined models use different endpoints/topologies and are not substituted for these measurements.

`native08-audit01` is a rejected source-recovery preflight, before FST decode: HEAD had advanced; the accepted `native08-audit02` recovers the exact native source at40be2ee and verifies its compiled hash. `delay200-10-audit01` is accepted. Both preserve selected FSTAPI events, transaction details and the reader build. Large raw FST/model archives stay in their parent's durable ignored locations; the audit binds their identities without copying them into Git. `host21` preserves the unchanged21-test source bindings and log.

`python3 research/hp0-closed-trace-20261121/verify_closed.py` rechecks accepted proof/source/event bindings, the parent archives' raw FST round trips, exact consumed model binary identities, every opaque response and+N age, and the separate UCE state groups. It writes `closed-verification.json` and executes no target.

Compiled-source snapshots preserve exact upstream bytes, including existing trailing whitespace. Those snapshots are data for the SHA checks and are excluded from the new-code/document whitespace check; no upstream source normalization was performed.
