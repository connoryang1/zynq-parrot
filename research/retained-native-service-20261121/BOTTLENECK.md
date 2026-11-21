This closed, read-only analysis explains the negative native0 capacity-control pair using identical cached work, actual retained transactions, normal D refill packets and the complete HP0 bus. It does not change the program/model, rerun a target, assign overlapping service intervals to exclusive stalls, or project simulation to FPGA/Linux performance.

The original complete result remains WHOLE +32,146 core cycles (+2.7726%) and timed ring +8,925 (+2.4341%) for joint15 versus off0. Both arms execute exactly the same43,926cached WHOLE references and10,586checked target loads. All normal tags/refills,512bit retained publication-to-hit provenance, control/ownership drainage and full execution checks passed in checkpoint `fbde8060587ea5506dd5635836cdada69111c373`.

The native external-memory response is fast: every actual read is one full64B burst (ARLEN7,8B beats), first R offer/accept at AR+1AXI cycle, RLAST at AR+8, sustained one beat/cycle. Every write response is AW+12 and WLAST+1. Both before/after opaque R/B streams, per-ID ownership, burst length/LAST and backpressure stability passed the unchanged HP0 auditor. The observed maximum is one pending read and one pending write, with no stalls; this is workload activity, not a platform concurrency bound. AXI and BE clock periods are both50,000FST ticks, verified from actual clocks/counters. No arbitrary per-word delay or DRAM calibration is inferred.

| Actual HP0 traffic | Off0 | Joint15 |
|---|---:|---:|
| WHOLE AR / AW |9105 /2993|7950 /2992|
| WHOLE accepted R beats / B responses |72840 /2993|63600 /2992|
| Timed AR / AW |1709 /21|937 /21|
| Timed R beats / B responses |13672 /21|7496 /21|

All1150joint D hits, including772timed, have an exact baseline cached-reference counterpart with one uniquely matched same-physical-line HP0 read inside that baseline normal miss interval. The joint counterpart has no matching HP0 read. The timed AR reduction is exactly772. Source association uses observed BP→HP0 translation and owned time windows, not RID0. There are no actual advisory admissions, and none of the110instruction request lines overlaps any D-hit line in either full trace. Whole AR reduction exceeds the1150direct hit joins by five; that additional difference is not assigned to a policy or stall mechanism here.

| Timed normal miss→full accepted L1 write | Baseline counterpart median | Joint median | Paired delta median |
|---|---:|---:|---:|
|772retained hits |30|25|−4|
|908retained misses |30|42|+12|

Matched deltas range −18…+1for hits and +3…+21for misses. First D-cache write medians are22→18for hits and22→34for misses. Critical-receive flag medians are22→20and22→34; that flag is **not** architectural load readiness or necessarily the requested word. Every accepted write/flag is joined bijectively to the already-audited eight-beat refill. The smaller difference between overall medians and the median of matched differences is expected; these are distinct statistics.

Accepted retained lookup→consumed-response service is11lane cycles for all908timed misses and12/14/16/18/20for772hits (counts179/162/168/142/121, median16). Successful timed insertions publish at20cycles. Thus this native regime saves real external reads but only a few local full-refill cycles on a typical hit, while the more numerous retained misses pay a substantial consultation cost. This is an evidence-supported service-cost bottleneck, not a decomposition of the whole loss into a sum of11cycle misses.

Offer waiting is measured separately. All1680timed D lookups and the one timed I lookup accept on their first offered lane edge. All1696accepted ordinary cached D requests and the one I request also accept immediately. There are no timed clear/epoch-wrap episodes or offered cache-request backpressure. This workload's timed loss therefore is not explained by observed offer waiting behind capture or clear, although those conditions matter in WHOLE:

| Joint WHOLE lookup waiting | Actual observed condition |
|---|---|
| I1667cycles |1219in an explicit-clear sweep;448with backend insertion active and raw UCE insert ownership1|
| D108cycles |All with backend insertion active and raw UCE insert ownership1;4069/4080lookups accept immediately; six wait8, four wait11, one waits16|

Both arms and both lanes have two explicit clear requests, each reaching lookup-ready after1281lane cycles, with1280clear-state samples. No epoch wrap occurs in WHOLE or timed ring; thirteen D wrap sweeps occur only in the full traces, including reporting. Every accepted ordinary cached WHOLE request accepts immediately. Each arm also has34one-cycle provisional D offers which withdraw before acceptance while UCE state16(`e_writeback_write_req`);17joint samples overlap raw insert ownership. These withdrawn offers are explicit and are not relabeled as accepted miss waiting or proof that capture caused a stall.

The union of actual pending D miss→full-write intervals grows50,149→57,482cycles in the timed ring and206,185→234,939in WHOLE. These are unions clipped to checked CSR bounds, including boundary-crossing misses. They overlap instruction, queue, writeback and computation activity and are **not** exclusive critical-path stall fractions. Median deltas, occupied cycles and clear durations must not be summed into a causal partition. The current pair demonstrates D capacity use and no I retained hits; it does not establish useful I capacity or general application benefit.

The data justify reducing serial lookup service cost as an experimental direction, subject to correctness, routed resources and complete matched endpoints. A separate row-store prototype's component numbers are not measured application results here. Controlled higher-latency evidence still requires one calibrated shared all-traffic R/B path, matched baseline/retention controls and measured first/full/bandwidth behavior. No linear miss-count×delay projection is used.

Machine-readable proofs are `matched-service01/analysis.json`, its complete counterpart joins, `mode{0,15}-{hp0,dcache,time-index,offers}/analysis.json` and `closed-inputs.json`. All input FSTs, selected streams, exact original RTL snapshots and host sources are bound by hashes. The additional46host tests include the unchanged21HP0 protocol cases. Large raw/selected traces remain external; a future compact checkpoint must preserve their paths/hashes and actual ledgers. Only a proposal for a trace-only clone follows; no clone build or additional target execution is authorized by this report.
