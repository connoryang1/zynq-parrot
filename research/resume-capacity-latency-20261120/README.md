This experiment separates additional retained instruction/data capacity from speculative traffic using already accepted physical Linux miss records. It varies transport delay independently of response bandwidth and includes trigger cost and all outstanding traffic in a service endpoint. The results are conditional event-model projections, not FPGA measurements or predicted Linux execution speedups.

# Inputs and scope

The three compressed raw logs are unchanged copies of the accepted inputs to `logs/cache-resume-trace-model-20261029/`. SHA-256 below covers the decompressed original bytes, as in the original acceptance record.

| Input | SHA-256 |
| --- | --- |
| Prior full-window training | `98b23d3c1b3f36024e6534a0be8479812aebac1b7b69b7f1ed1bb33320210022` |
| Source to peer, holdout | `066b633faa245c4ec436b6240d399179b1884d5febbb68702fff85261b75abf9` |
| Peer to source, holdout | `2fc9456151b17163a03da2da8fb47a3ab48e5752800e710a2023ffa7f73e88e2` |

These are **miss-only** records: no ordinary L1 hits, completion times, dependencies, or recurrent measured epochs were recorded. Consequently they cannot identify a full L1 capacity curve, reconstruct how eliminating one miss changes execution, or prove that continuous prefetch beats a one-time preseed. The old full-access scan/trie/pointer JSON inputs cited by RL-013/RL-019 are absent from this checkout; their retained model summaries are not substitutes for those inputs.

The source-to-peer recorder includes one instruction request 43 cycles beyond its explicit endpoint. The model counts and excludes that disarm tail, retaining 47 instruction and three data requests over 11,379 cycles. The reverse window retains 218 instruction and ten data requests over 28,883 cycles. The independently booted windows are evaluated separately, never concatenated into a measured transaction.

# Matched controls

Every case has separate I/D capacity settings of 0, 4, 16, 32, 64, or 128 complete 64-byte lines. Instruction-only, data-only and joint configurations are evaluated.

| Mechanism | Initial contents | During the window |
| --- | --- | --- |
| Base | No added capacity | Every recorded miss issues demand |
| Demand-retained LRU | Prior demand history fills extra side capacity | Ordinary demand fills and LRU replacement; no speculative reads |
| Retained prefix | Prior epoch's first C unique demanded lines, pinned | Same tags and capacity as replay; no speculative reads or ordinary-demand replacement |
| One-time preseed | Initially empty | Read the prior first-C prefix once; only replay fills enter its side store |
| Continuous replay | Initially empty | Read that prefix at each supplied trigger; only replay fills enter its side store |

The pinned-prefix control isolates the value of retaining the exact replay contents without issuing memory traffic. It is a hypothetical first-demand retention policy, not implemented hardware. The LRU control tests a different selection policy; its difference from pinned prefix must not be attributed solely to prefetching. Prior-history population is outside this held-out window, just as ordinary cache warming is; the speculative preseed here starts at the window boundary and is charged through full drain.

Replay tables use only the separate preceding trace, without selecting current holdout addresses. Supplying the evaluated trace as training requires the explicit `--oracle` option. Physical-line recurrence across fresh boots says little about virtual-address/per-task prediction; this model does not implement such a predictor.

# Service model

The discrete-event model has one ordinary demand miss outstanding per I/D side, a shared nonpreemptive response bus, four global replay slots, and independent serial I/D installation queues. Demand responses have priority among ready responses, but cannot interrupt a replay burst already using the bus. Matching demands join in-flight replay; resident or in-flight lines suppress redundant replay. The side capacity is fully associative LRU when replacement is needed, so this is not a model of the accepted four-bank buffer's conflicts or exact replacement.

`results.json` varies first-response latency over 41/82/164/200 cycles with eight beats at one cycle/beat and 19 installation cycles. `bandwidth2.json` repeats the identical latency and capacity matrix with two cycles/beat. The default 32-cycle trigger cost is an explicit illustrative parameter, not a new measurement of the current early-futex hook. Slot lifetime conservatively includes installation.

Demand arrivals stay fixed at their observed acceptance timestamps, with trigger cost added. Same-side requests queue behind the modeled miss pipeline. The endpoint is the maximum of the whole observed window plus trigger cost and **every demand/replay completion**, including unused replay. Summed demand service waits may overlap across lanes and cannot be subtracted from execution time.

# Conditional observations

With the exact prior first-C contents already retained, the following recorded misses are intercepted across the two independent windows at the primary service setting. Counts refer to demand records, not newly measured misses or execution savings.

| Added lines on that side | I records intercepted / 265 | D records intercepted / 13 |
| ---: | ---: | ---: |
| 4 | 3 | 4 |
| 16 | 19 | 8 |
| 32 | 42 | 8 |
| 64 | 60 | 8 |
| 128 | 114 | 8 |

These particular data traces offer only nine unique prior data lines; increasing D-side capacity above sixteen cannot expand that trained footprint. This is a limitation of the captured workload, not evidence that a general application needs no additional D capacity.

At 32 I and 32 D entries, completed pinned contents intercept 33/50 and 17/228 request records in the forward/reverse windows. One-time replay intercepts exactly the same records at 41-cycle first response: capacity and its selected contents explain all of that conditional coverage. Replay nevertheless issues 41 full-line reads per window (32 I plus nine D); 33/17 replay fills are eventually consumed and eight/24 are not. Overall response traffic becomes 58/252 reads versus the base's 50/228. The local reduction in demand reads therefore coexists with **more total response traffic**.

The base model's drained service endpoints are 11,447/28,968 cycles, respectively 68/85 beyond the physical request-window markers. This is an explicit failure to reproduce physical completion timing, because such timing was never recorded. It must not be presented as a calibrated baseline. At 32+32 entries replay's endpoints are 11,479/29,000, including the illustrative 32-cycle trigger cost; these service quantities are not transaction regressions or speedups. Higher latency creates queuing under the fixed arrival schedule, which is why it must not be interpreted as a rescheduled high-latency Linux run.

There is one trigger per captured window. Preseed and continuous rows therefore match exactly by construction, at every swept setting. Distinguishing them requires measured recurrent epochs or a complete-access execution model. The useful next evidence is natural post-switch demand with repeated epochs plus consumption and completion timing, not another performance claim extracted from these old misses.

# Reproduction and checks

From the worktree root:

```sh
python3 -B tools/test_resume_capacity_model.py
python3 -B tools/resume_capacity_model.py \
  --training research/resume-capacity-latency-20261120/raw/cache-miss-trace-pass-1.log.xz \
  --trace research/resume-capacity-latency-20261120/raw/cache-miss-trace-to-peer.log.xz \
  --trace research/resume-capacity-latency-20261120/raw/cache-miss-trace-from-peer.log.xz \
  --output research/resume-capacity-latency-20261120/results.json
```

Repeat the latter command with `--cycles-per-beat 2` and output `bandwidth2.json` for the independent bandwidth control. Nineteen tests cover demand-populated capacity, equal-content prefix retention, separated I/D stores, in-flight joins, nonpreemptive interference, demand response priority, complete unused-traffic drain, trigger cost, independent latency and bandwidth, one demand MSHR per side, single-window preseed equivalence, repeated trigger accounting, invalid timing, and fail-closed trace parsing. Synthetic test schedules demonstrate model invariants only; they are not benchmark evidence.

A first CLI attempt used dictionary union unsupported by the installed Python 3.8 and failed before writing results. It was replaced with `dict(...)`, and the full CLI is now exercised by a regression test. Only the successful regenerated JSON files are retained as model output.
