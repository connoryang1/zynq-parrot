This ledger preserves the current reasoning state of the hardware-context and latency-hiding investigation. It separates ideas we expected beforehand from new measurements, mechanism discoveries, superseded interpretations, and unresolved questions. Raw logs and `WORK_LOG.md` remain the detailed evidence and chronology; this file is the maintained synthesis.

# Research Ledger

## Objective and evaluation criteria

Determine when cheap hardware context switching and detached prefetching improve latency-bound execution, how close they approach a matched batched schedule, and whether the mechanism remains useful in a real FPGA/Linux system. Evaluate primitive switch cost, request overlap, cache behavior, physical DDR behavior, Linux end-to-end performance, correctness over sustained reuse, and implementation cost without mixing those scopes.

## Baseline knowledge and expectations

These were reasonable expectations before the experiments and should not be presented later as newly discovered concepts:

- Cheap switching can hide latency when independent work exists and total interleaving time covers the outstanding latency.
- Concurrency hides latency but does not create memory bandwidth; gains stop when transport, cache installation, or instruction issue becomes the bottleneck.
- More streams help only until latency is covered, and nonresident streams can lose to fewer resident streams when switching overhead dominates.
- A manually interleaved single-thread loop is a strong upper-bound competitor when the workload can be rewritten that way.
- Accelerating a primitive produces limited end-to-end speedup when useful work or unrelated OS overhead dominates total time.
- A low-frequency FPGA can observe DRAM in relatively few core cycles, so results should not be generalized to a high-frequency CPU by cycle count alone.

The experiments are valuable where they quantify these effects, expose unexpected mechanisms, validate them under Linux and on an FPGA, or contradict a simple expectation.

## Current accepted claims

### RL-001 — Hardware context handoff is cheap

- **Status:** confirmed measurement
- **Scope:** accepted two-resident design and Linux persistent-context selector
- **Claim:** bare-metal handoff costs about 5.13 resident cycles and 9.26 nonresident cycles; the Linux-hosted general selector costs 17.074 resident and 22.090 nonresident cycles.
- **Evidence:** `WORK_LOG.md` entries **Final-line redirect overlap validated**, **Relaunch fix latency control**, and **Persistent context group measured under Linux**; detailed evidence under `logs/context-launch-20260922/`, `logs/translated-resident-relaunch-fix-20261004/`, and `logs/linux-context-group-fastpath-20261003/`.
- **Meaning:** the switching primitive is small enough to overlap tens to hundreds of cycles of latency.
- **Limits:** these numbers are not Linux scheduler replacement speedups and should not be added to whole-workload timings without a matched model.

### RL-002 — The physical FPGA has short memory latency in core-cycle terms

- **Status:** confirmed measurement
- **Scope:** PYNQ-Z2 physical DDR and the routed low-frequency core
- **Claim:** representative cold demand accesses are roughly 41 core cycles, detached prefetch completion is roughly 21–25 cycles in the measured path, and an L1 hit is roughly 3 cycles.
- **Evidence:** `logs/fpga-memory-latency-20260923/` and the corresponding `WORK_LOG.md` entries.
- **Meaning:** only a few streams are needed to cover latency in principle, and switching/control overhead matters much more than it would on a high-frequency CPU with 100–300-cycle DRAM latency.
- **Limits:** the detached-prefetch and demand paths are not identical transports, and the values do not establish arbitrary-machine behavior.

### RL-003 — The accepted 200-cycle simulator worker is two cycles behind batch

- **Status:** confirmed final result
- **Scope:** exact fixed full-system simulator, synthetic 200-cycle memory, matched worker and batch ELF
- **Claim:** worker is 398 cycles and batch is 396 cycles. The two-cycle net gap is not a two-cycle switching cost: the worker has 174 extra non-load cycles, offset by 172 fewer load-span cycles along the overlapping response stream.
- **Evidence:** `logs/context-launch-20260922/verification-200-analysis/README.md`; `WORK_LOG.md` entries **Prefetch overlap verified independently**, **Accepted completion preserved across switch flush**, and **Final-line redirect overlap validated**.
- **Meaning:** with sufficiently long latency and ten-way overlap, context switching can make the complete worker schedule nearly match batch.
- **Limits:** this is a schedule-level cancellation in a synthetic model, not a universal two-cycle gap and not a direct measure of context-switch latency.

### RL-004 — The two-cycle gap does not carry to physical DDR

- **Status:** confirmed measurement
- **Scope:** fixed FPGA image, matched ten-request bare-metal physical-DDR microbenchmark
- **Claim:** worker is exactly 310 cycles and batch exactly 176 cycles across seven accepted samples each, a 134-cycle gap. A single demand-ring control is 652 cycles and switch-only control is 253 cycles.
- **Evidence:** `logs/real-ddr-20260923/README.md` and `logs/real-ddr-20260923/analysis/README.md`.
- **Meaning:** when memory completes quickly, the batch schedule benefits more and the worker becomes control/scheduling dominated. The FPGA worker still reduces the complete demand schedule by 52.5% in this narrow control.
- **Limits:** demand, worker, batch, and switch-only rows are complete schedules, not additive primitive costs. No board bus waveform proves the instantaneous request count.

### RL-005 — Ten streams improve sustained dependent pointer chasing on the FPGA

- **Status:** confirmed measurement
- **Scope:** corrected ten-stream physical-DDR workload
- **Claim:** medians are 60,369 demand, 49,796 serial prefetch, 44,636 software interleaving, and 41,570 hardware contexts. Hardware takes 31.1% fewer cycles than demand and 6.9% fewer than software interleaving; two- and four-stream hardware remain behind software.
- **Evidence:** `logs/prefetch-sustained-coverage-20260924/RESULTS.md`; `WORK_LOG.md` entry **Sustained prefetch correction and real-DDR qualification**.
- **Meaning:** hardware contexts can beat optimized software interleaving when there is enough independent work, but the benefit is moderate on this short-latency FPGA.
- **Limits:** this does not imply ten requests multiply physical memory bandwidth or that ten is optimal on another memory/core ratio.

### RL-006 — Two separate cache interactions caused lost prefetch benefit

- **Status:** new mechanism and fixes, confirmed
- **Scope:** detached fills entering the L1 and demands arriving near those fills
- **Claim:** first, a demand could capture stale miss metadata while a same-line detached fill was live, causing a redundant ordinary refill; the demand-join fix holds and rechecks it. Second, concurrent fills could choose the same stale replacement way; reserving live ways, rereading dirty/LRU state at installation, and replaying blocked hints fixed sustained coverage.
- **Evidence:** `WORK_LOG.md` entries **Duplicate-refill timing**, **RTL demand join validated**, and **Sustained prefetch correction and real-DDR qualification**; `logs/matched-prefetch-20260919/` and `logs/prefetch-sustained-coverage-20260924/`.
- **Meaning:** the main loss was not ordinary set mapping alone. It came from timing and metadata arbitration between detached fills, demand miss capture, replacement choice, and serialized installation.
- **Limits:** more SRAM data ports alone do not resolve tag, valid, replacement, dirty, and miss-state coordination.

### RL-007 — Hardware contexts greatly reduce handoff cost but have workload-dependent end-to-end gains

- **Status:** confirmed measurement
- **Scope:** physical Linux persistent context groups and matched useful-work sweep
- **Claim:** the mean Linux handoff is about 5,545.5 cycles versus 17.074/22.090 for resident/nonresident user-level hardware selection. Resident speedup over `sched_yield` falls from about 200.9x near zero work to 26.87x at 205 useful cycles, 8.27x at 781, 2.83x at 3,085, and 1.49x at 12,584.
- **Evidence:** `logs/linux-context-group-fastpath-20261003/`, `logs/linux-context-group-work-scaling-20261003/`, and `logs/linux-scheduler-bypass-envelope-20261003/`.
- **Meaning:** the primitive improvement is real, while total speedup follows the fraction of time that can actually be removed.
- **Limits:** eliminating only low-level `switch_to` cannot remove all Linux scheduling work; the optimistic measured cap for that narrower change is about 1.65x.

### RL-008 — Optimized software interleaving can beat hardware on a rewrite-friendly workload

- **Status:** confirmed measurement
- **Scope:** physical Linux cold random-request workload
- **Claim:** optimized interleaved assembly is 567,541.5 cycles, sequential assembly 575,671, resident hardware handoff 611,886, and Linux threads 680,919.5. Hardware's 5.413-cycle/request excess over interleaved assembly matches the independent resident switch cost.
- **Evidence:** `WORK_LOG.md` entry **Blocking-demand speedup attributed to software path** and `logs/linux-hardware-group-demand-attribution-20261003/`.
- **Meaning:** this workload already expresses the available overlap in one software context; hardware helps over kernel threads but adds its switch cost relative to ideal manual interleaving.
- **Limits:** this does not cover separately written tasks, protected contexts, complex control flow, or applications that cannot practically be fused into one loop.

### RL-009 — The placement-sensitive lifecycle hang had a translated resident-relaunch root cause

- **Status:** new root cause and physically accepted fix
- **Scope:** resident switching under Sv39 when the frontend cannot accept the redirect immediately
- **Claim:** a switch could clear its pending token before delivering the target redirect, allowing fallback fetch of the correct PC with the old thread/register-bank tag. Marking state-reset fallback commands as explicit thread changes fixes the exact failing placement with no measurable 5.13/9.26-cycle latency regression.
- **Evidence:** `logs/translated-resident-relaunch-fix-20261004/`; `WORK_LOG.md` entries **Translated resident relaunch fixed**, **Relaunch fix latency control**, and **Translated resident relaunch physically accepted**.
- **Meaning:** the intermittent failure was a real frontend/context provenance bug, not proof of a cache, alignment, or conditional-prediction root cause.
- **Limits:** predictor-bank alignment remains a separate valid correction even though it was not the lifecycle root cause.

### RL-010 — Persistent contexts survive real Linux process reuse

- **Status:** confirmed measurement
- **Scope:** corrected-timer Linux, rebind-capable FPGA image
- **Claim:** two separate processes completed roughly 1,048,832 handoffs, and ten sequential processes completed about 163,880 handoffs with correct checksums, translations, exits, and no monotonic slowdown.
- **Evidence:** `logs/process-rebind-20261004/`; `WORK_LOG.md` entries **Same-boot separate-process reuse physically accepted** and **Ten-process rebind lifecycle stress passed**.
- **Meaning:** hardware contexts can be persistently managed and rebound across process lifetimes rather than serving only a bare-metal demonstration.
- **Limits:** this is a controlled benchmark lifecycle, not broad application compatibility.

### RL-011 — Historical Linux timing was misconfigured

- **Status:** new measurement and correction
- **Scope:** historical FPGA Linux image
- **Claim:** the old timer ran near 1.125 MHz while software declared much higher rates, making monotonic time about 8.9x too short and suppressing normal ticks. The corrected ~8 MHz source shows a 250 Hz tick cost around 20,485.5 core cycles and predicts observed long-run inflation within 0.8%.
- **Evidence:** `logs/linux-timer-calibration-20261004/`; `WORK_LOG.md` entry **Linux timer scale and interrupt cost calibrated**.
- **Meaning:** earlier long-duration Linux results without corrected ticks are not representative of normal interrupt overhead.
- **Limits:** cycle-counter measurements inside short timed regions remain distinct from incorrectly scaled wall time.

### RL-012 — The liveness diagnostic can separate target stalls from host MMIO stalls

- **Status:** simulator-validated, physical capture pending
- **Scope:** full-system host runner at commit `e3f54c52`
- **Claim:** sequence-numbered pre-read markers and post-read counter/timing lines distinguish advancing retirement, a target counter plateau, and a blocked GP/MMIO read. In the simulator, all 15 markers pair and the two reads take a 41.228-ms median host time.
- **Evidence:** `logs/process-rebind-20261004/control-liveness-instrumentation-status.json`; `WORK_LOG.md` entry **Boot-stall liveness instrumentation validated**.
- **Meaning:** the next physical nonreturn can be localized without guessing from an absent final line.
- **Limits:** no recovery-qualified physical stall has yet been captured. Board SSH is reachable again, but the external power controller still rejects both recovery requests, so the required physical power cycle cannot be confirmed.

### RL-013 — Resume-footprint prediction was already modeled

- **Status:** confirmed trace analysis
- **Scope:** retained scan, trie/irregular-stream, pointer-plus-compute, and ten-dependent-chain traces using 16-byte sectors
- **Claim:** retaining the ordered first unique sectors from a context's previous epoch is the strongest tested small predictor. At depth two, next-resume precision is 91.5% for scan and 45.7% for trie, supplying about 1.87 and 1.21 useful sectors per resume; pointer-plus-compute and dependent-chain controls are effectively 0%. Prior MRU order performs much worse. Two entries are the conservative starting point, with adaptive expansion toward four when consumption feedback is positive.
- **Evidence:** `logs/context-resume-footprint-20261002/README.md` and `model-results.json` in the same directory.
- **Meaning:** the address-recurrence opportunity, predictor family, useful depth, timeliness model, negative controls, and sub-1-KiB ten-context storage estimate have already been investigated. This is not future preliminary work.
- **Limits:** the source traces are synthetic and mostly warm-cache. They estimate recurrence and timeliness rather than forced-cold Linux end-to-end speedup.

### RL-014 — Correct resume hints were tested physically under Linux

- **Status:** confirmed physical measurement
- **Scope:** same-mm Linux precision sweep with eight explicit hints, corrected whole-entry reclaim, and round-robin stale-entry replacement
- **Claim:** after the buffer fixes, eight correct hints save 271.5 application cycles toward main and 239 toward worker beyond translation priming. Hints seven and eight alone save 69 application cycles in each direction. Observed total medians finish 80/73.5 cycles faster than cold demand, but independent-bootstrap intervals include zero; repeatable scheduler-inclusive break-even is not established. Eight stale hints remain 240/189 cycles slower than cold.
- **Evidence:** `logs/linux-prefetch-precision-sweep-rotate-20261003/README.md`, `logs/linux-prefetch-retention-controls-rotate-20261003/README.md`, and the `WORK_LOG.md` entry **Stale side-buffer replacement recovers late hints on real DDR**.
- **Meaning:** useful cache restoration is physically real, but confidence filtering and hardware-side issue/training are necessary; software issue and general Linux scheduling overhead can consume the gain.
- **Limits:** this supplies controlled correct/stale hints rather than automatically learning and replaying a per-context signature. The same-mm setup controls translation and does not establish separate-process behavior.

### RL-015 — The realistic automatic D-resume opportunity is tens, not hundreds, of cycles

- **Status:** evidence-linked projection, not a measured implementation
- **Scope:** previous-first trace precision combined with translation-primed physical application-work savings
- **Claim:** eight exact correct hints save an average 255.25 cycles in a 3,254.5-cycle phase, a 7.84% reduction or 1.085x phase speedup. A realistic previous-first signature projects only 10.0–45.5 cycles for scan at depth two and 33.4–81.3 at depth four; trie projects 6.4–22.8 and 14.4–46.1 cycles. These are 0.2–2.5% phase reductions. Pointer-plus-compute and dependent-chain controls project zero.
- **Evidence:** `logs/automatic-resume-signature-projection-20261006/README.md` and reproducible `analyze.py`/`results.json` in that directory, combining the exact inputs from RL-013 and RL-014.
- **Meaning:** an automatic D-cache signature can remove tens of cycles from recurring resumes, but D-cache history alone is unlikely to produce a large end-to-end result on these 3.2k-cycle phases. Depth two is the low-risk starting point; depth four needs positive consumption feedback.
- **Limits:** the ready-only floor ignores useful partial progress, while the full-hit-value cap assumes the trace predictor realizes the value of controlled physical hints. Hardware training/replay costs and cache pollution are not modeled.

### RL-016 — Cold Linux resume instruction and data penalties were already decomposed

- **Status:** confirmed physical measurement
- **Scope:** same-mm `sched_yield` on the FPGA with independent and combined cache/TLB displacement controls
- **Claim:** the hot resume median is 5,551 cycles. A 32-KiB instruction footprint raises it to 12,160 (+6,609), a 128-KiB clean-data footprint to 11,136.5 (+5,585.5), and both to 17,335–17,421.5. Only 2.7–3.4% of the two penalties overlaps. The instruction sweep is equivalent to about 175 serialized line refills and the data sweep to about 143, suggesting 128–192 remembered lines on each side as useful design points.
- **Evidence:** `logs/linux-scheduler-resume-20261002/README.md` and `results.json`; component controls in `logs/cold-resume-components-20261002/README.md`.
- **Meaning:** the large ordinary-Linux cold-resume opportunity is kernel/task instruction and data recovery, with an ideal combined hot-floor opportunity around 3.12–3.14x. A few application data hints cannot recover this interval.
- **Limits:** refill-equivalent counts are sizing guides rather than measured unique misses. The experiment includes syscall, scheduler, and return work and is not the five-cycle hardware handoff.

### RL-017 — Large application-state replay was already bounded physically

- **Status:** confirmed physical upper bound and replay-cost measurement
- **Scope:** ideal completed replay of private 128/160/192-line working sets before same-mm Linux dispatch
- **Claim:** replay reduces post-resume application work by 6.23x, 6.59x, and 6.08x for 128, 160, and 192 lines. Scheduler-inclusive measured speedups are 1.39x, 1.49x, and 1.56x because Linux resume remains about 11.37k cycles. Combining replay work with the separately measured hot-kernel floor projects 2.63x, 2.78x, and 2.85x. Serial software replay costs 5.6k–8.5k cycles: it fits inside Linux resume slack but is far too long for a 5–11-cycle hardware handoff.
- **Evidence:** `logs/linux-post-resume-replay-20261002/README.md`, `results.json`, and `cost-results.json`.
- **Meaning:** a substantial design must either begin replay while the task is off CPU or entering the Linux scheduler, exploit much more replay parallelism, or preserve/partition cache state. Switch-time replay alone cannot rebuild hundreds of lines.
- **Limits:** completed replay is an oracle upper bound using exact lines and ordinary loads. The projected combined result is composed from measured components rather than an end-to-end hardware replay implementation.

### RL-018 — Replay and retention serve different scheduling regimes

- **Status:** evidence-linked architectural accounting model
- **Scope:** measured 128/160/192-line replay costs, 11.35k-cycle Linux resume slack, and two 32-KiB eight-way resident caches
- **Claim:** combined I+D replay at 128 lines each already fits the measured Linux resume interval at the serial software rate; 160 and 192 lines need only 1.24x and 1.48x that rate, or 32.5 and 38.7 MB/s. Retaining the same state for two resident contexts consumes 4, 5, or 6 of eight ways in each cache, leaving 4, 3, or 2 ways shared. Address histories for ten logical contexts require a raw minimum of about 5–7 BRAM18 blocks.
- **Evidence:** `logs/cache-resume-replay-vs-retention-20261006/README.md` and reproducible `model.py`/`results.json`, derived from the accepted RL-016/RL-017 inputs.
- **Meaning:** resident contexts need retention for immediate hot state because a 5–11-cycle handoff cannot hide large replay. Nonresident or normally scheduled contexts can use background replay during the long Linux interval. A hybrid design matches both regimes.
- **Limits:** RL-019 through RL-022 now bound retention pollution, data installation, and aggregate transport feasibility. Exact replay addresses, trigger time, instruction-path implementation, and useful-before-demand behavior remain unmeasured. The 160-line retention point is not a uniform integer-way partition.

### RL-019 — Two-way resident retention is the safer capacity point

- **Status:** trace-driven cache-policy model
- **Scope:** warm data traces in a 64-set/eight-way LRU model with contexts 1 and 2 protected and context 0 sharing the remainder
- **Claim:** reserving two ways per resident leaves four shared ways and adds zero scan misses and three trie misses in the repeated warm traces. Three ways leaves only two shared and adds 340 scan plus 74 trie misses. In pointer-plus-compute, one/two protected ways raise context-0 misses from 907 to 1,127/1,163, an absolute miss-rate increase of 0.97/1.13 points; two-way protection adds an estimated 9,984 cold-increment cycles across 22,666 accesses.
- **Evidence:** `logs/cache-retention-trace-model-20261006/README.md` and reproducible `model.py`/`results.json`.
- **Meaning:** two ways (128 lines/context) are the lower-risk retention prototype. Static protection still taxes an unprotected cache-sensitive workload, so inactive or low-confidence ownership should be releasable.
- **Limits:** the workers are already warm and see no misses, so these traces measure capacity cost rather than retention benefit. The model omits instruction accesses, dirty state, and exact BlackParrot replacement behavior.

### RL-020 — Two-way retention captures the modeled forced-cold application benefit

- **Status:** trace-driven forced-displacement upper bound
- **Scope:** previous-epoch first-use lines, 64-byte granularity, two lines per set, and a 39-cycle cold-data increment
- **Claim:** across 616 scan resumes, retention preserves a median four useful lines and saves an upper-bound 156 cycles, for a 3.85x median forced-cold resume-window projection. Across 280 trie resumes it retains ten lines, seven useful, and saves 273 cycles, for 1.71x. Pointer-plus-compute retains one line but gets zero reuse and zero benefit. The 128-line/two-way and 192-line/three-way policies have identical benefit because these application epochs never need the extra capacity.
- **Evidence:** `logs/cache-retention-forced-displacement-20261006/README.md` and reproducible `model.py`/`results.json`.
- **Meaning:** conditional two-way retention has a material payoff when recurring state would actually be displaced, while three ways add no application benefit here. Consumption feedback can distinguish the positive scan/trie cases from pointer chasing.
- **Limits:** every evaluated resume is hypothetically fully cold and each useful line receives the full serialized 39-cycle credit. Real below-L1 hits, overlap, and instruction state can reduce or change the result.

### RL-021 — Concurrent data-cache replay installation was already demonstrated

- **Status:** accepted simulator evidence; FPGA placement failed
- **Scope:** detached 64-byte data-line prefetches, three resident contexts, synthetic 40-cycle memory, and the existing single-port L1 installation path
- **Claim:** per-request response buffering lets later hints issue while an earlier line installs. The closed 33-node trace admits and completes all 33 hints, reaches four outstanding UCE/AXI reads, records 27 hint allocations and issues during a prior fill, and has zero ordinary fallbacks. Concurrent installation reduces the 120-node run from 4,455 to 2,542 cycles; banked storage further reduces it to 2,512, only 9.6% above the 2,292-cycle narrow-buffer result. The direct installer is exactly 17 cycles in 40/40 traced lines, while the concurrent response-buffer waveform ranges from 16 to 21 cycles with a 19-cycle median.
- **Evidence:** `logs/clock-pipeline-20260929/full-line-lat40-sweep-120/RESULTS.md`, `logs/clock-pipeline-20260929/full-line-lat40-sweep-120/fill-buffer-concurrent/trace-k3-m3-n33/analysis/installer-overlap.json`, and `logs/prefetch-sustained-coverage-20260924/final-trace/k10-m2/final-installer-audit.json`.
- **Meaning:** the replay question is no longer whether data-line installation can overlap request issue. The direct 17-cycle path does not overlap later requests, while every concurrent implementation measured so far has a 19-cycle median and exceeds RL-022's strict whole-footprint requirement.
- **Limits:** the implemented paths install data lines only. The corrected ten-slot BRAM implementation synthesized but failed PYNQ-Z2 placement by 172 slices, and the four-slot physical endpoint was not qualified.

### RL-022 — Four slots suffice only for the unachieved 17-cycle concurrent scenario

- **Status:** conditional measured-input architectural lower bound
- **Scope:** conservative ceilings of 175 kernel instruction and 144 kernel data refill-equivalents, 160 application data lines, a 17-cycle installer, 64-byte lines, one 64-bit/18-MHz AXI response channel, a conditional 41-cycle request-to-first-beat input, and a 5,551-cycle hot-resume deadline
- **Claim:** replaying all 479 lines before first user dispatch requires 99.4 MB/s. Under the conditional 41-cycle input, one/two/three outstanding slots have aggregate lower bounds of 19,647/9,848/6,581.7 cycles and miss the deadline. Four slots reduce transport to 4,948.5 cycles. A hypothetical concurrent 17-cycle installer would finish at 5,217 cycles with 334 cycles left, but the measured banked 19-cycle median finishes at 5,825 and misses by 274; its 25-cycle maximum gives 7,649 and misses by 2,098. No slot count fixes an installation-rate miss. A single shared 17-cycle installer takes 8,192 cycles.
- **Evidence:** `logs/cache-resume-shared-path-bound-20261006/README.md` and reproducible `model.py`/`results.json`; separate I/D UCE and cache-array paths in `import/black-parrot/bp_top/src/v/bp_unicore_lite.sv`; shared demand-priority AXI arbitration in `import/black-parrot-subsystems/blackparrot/v/bp_axi_top.sv`.
- **Meaning:** queue depth was only one condition. The measured concurrent installer is now the strict whole-footprint bottleneck, so the first implementation should replay a prioritized prefix or combine replay with retention. An instruction path should still use the physically separate I-cache resources.
- **Limits:** the physical 41-cycle result is critical load-to-use, not detached 64-byte request-to-first-beat timing, so physical feasibility remains unproved. The 175/144 values are serialized-latency equivalents rather than actual miss counts, and the calculation omits address order, DDR/arbitration bubbles, translations, dirty victims, capacity replacement, and real scheduler interference. No instruction replay injector currently exists.

### RL-023 — Conditional whole-footprint replay requires an early target prediction or hint

- **Status:** conditional measured-input trigger-window upper bound
- **Scope:** RL-022's conditional four-slot/41-cycle transport, the measured banked 19-cycle median, separate I/D installers, the 5,551-cycle hot-resume window, and the measured 2,139–2,238-cycle alternate-thread increment beyond a no-peer yield
- **Claim:** the 479-line target takes 5,825 cycles and misses hot dispatch by 274 cycles even when started at yield entry. A generous 2,238-cycle late window completes at most 214 mixed lines: 44.7% of the 479-line target or 67.1% of the 319-line kernel-only target. The kernel-only target takes 3,374 cycles and must begin within 2,177 cycles, 61 cycles before that generous late window begins. A 5.13- or 9.26-cycle hardware handoff cannot complete one line.
- **Evidence:** `logs/cache-resume-trigger-bound-20261006/README.md` and reproducible `model.py`/`results.json`, derived from RL-022 and `logs/linux-hot-scheduler-breakdown-20261003/analysis.json`.
- **Meaning:** a `switch_to`-time context identifier is too late for complete replay. An explicit pre-yield hint, an early target predictor, or replay already running while the context is off CPU is required for private state. Common kernel lines can start at syscall entry without knowing the incoming task. Resident five-cycle handoffs still require retention.
- **Limits:** the Linux delta is not a direct task-selection timestamp; assigning all of it to post-selection replay is intentionally optimistic. The 41-cycle full-line endpoint remains conditional, and capacity does not establish usefulness because address order and individual demand deadlines remain unknown.

### RL-024 — Early target prediction needs at least 75% median confidence for eight hints

- **Status:** physical-outcome-derived planning bound
- **Scope:** accepted same-mm FPGA medians for eight correct hints versus eight stale hints after the side-buffer replacement fix
- **Claim:** a correct target's eight hints save 80/73.5 total cycles toward main/worker, while a wrong target's eight stale hints cost 240/189. Solving `p*save - (1-p)*penalty > 0` gives median break-even target accuracies of 75.0% and 72.0%; use 75% as the conservative small-batch planning floor. Even 90% accuracy projects only 48/47.25 cycles of expected median saving.
- **Evidence:** `logs/cache-resume-target-confidence-20261006/README.md` and reproducible `analyze.py`/`results.json`, derived from the accepted physical `logs/linux-prefetch-precision-sweep-rotate-20261003/results.json`.
- **Meaning:** early replay should scale with two distinct confidence signals: confidence in the next context and confidence in each line. Full replay is appropriate only for deterministic/high-confidence pairings; moderate confidence should issue a short high-value prefix, and low confidence should wait or use releasable retention.
- **Limits:** the correct-hint scheduler-inclusive bootstrap intervals cross zero, so this is a median planning bound rather than repeatable end-to-end proof. An eight-hint same-mm result is optimistic for hundreds of wrong full-line requests, whose pollution can be nonlinear.

### RL-025 — An exact ordered Linux miss trace fits in two additional BRAM tiles

- **Status:** corrected RTL-topology sizing, confirmed by RL-027
- **Scope:** accepted 34-bit physical-address endpoint, 64-byte lines, separate I/D UCE request streams, 256 timestamped 64-bit records per cache, and the routed 18-MHz FPGA utilization
- **Claim:** a 64-bit record holds a 32-bit cycle, 28-bit physical line address, and four metadata bits. Independent 256x64 I/D buffers permit simultaneous capture and leave 81/112 entries above the conservative 175/144 refill-equivalents. A 256x64 history requires one RAMB36, so the pair consumes two BRAM tiles rather than the originally projected single tile.
- **Evidence:** planning artifact `logs/cache-resume-miss-tracer-design-20261006/README.md`, corrected implementation evidence in `logs/cache-miss-trace-route-20261006/`, and final RAM mapping in routed job `logs/fpga/20261006T182248Z-e860ceea/`.
- **Meaning:** the exact evidence required by OQ-005 can be gathered on the FPGA without building the replay engine or perturbing the cache datapaths. Capture accepted non-prefetch BedRock reads separately at the existing I/D UCE boundaries and merge by global timestamp.
- **Limits:** refill-equivalents are not literal event counts, so overflow flags are required. Request time gives the replay deadline but not response completion. The earlier one-tile estimate was incorrect because RAMB18 cannot hold 256x64; RL-027 is authoritative for fitted resources.

### RL-026 — The ordered I/D miss recorder works end to end in simulation

- **Status:** accepted clean simulation, routed implementation, and directed FPGA execution; Linux capture completed in RL-029
- **Scope:** separately armed 256x64 I/D histories at the accepted physical cache-request interfaces, demand misses only, custom CSR control/readout, and the maintained two-resident/four-logical Zynq model
- **Claim:** a clean trace-enabled build captures the intended cold function and data lines, reports two accepted I misses and one accepted D miss with zero overflow, and reads every record back after disarm. The selected cold instruction line is timestamped at `0x623be` and the data line at `0x623fd`. The existing context-switch smoke test remains accepted with the recorder compiled in and disarmed.
- **Evidence:** `logs/cache-miss-trace-sim-20261006/README.md`, exact transcript/ELF/NBF/FST and hashes in that directory, the directed `testing/mt_cache_miss_trace_test.c` gate, and routed acceptance in RL-027. The full 607-module `bp_axi_top` hierarchy also compiles with the recorder explicitly enabled.
- **Meaning:** RL-025's proposed measurement interface is now real rather than a sizing sketch. It observes accepted post-translation physical demand misses, excludes detached prefetch requests, preserves simultaneous I/D capture, and can be compiled out of unrelated BlackParrot configurations.
- **Limits:** the 63-cycle I-to-D timestamp difference includes instruction sequencing and cold-function execution and is not a DRAM-latency result. RL-028 supplies the directed board trace and RL-029 supplies the Linux interval.

### RL-027 — The miss recorder routes with block RAM and recovers 787 LUTs

- **Status:** accepted routed before/after comparison and directed physical execution
- **Scope:** default 20-MHz `e_bp_unicore_zynqparrot_cfg`, identical dependencies except for the recorder read shape, complete synthesis/place/route/bitstream, and the clean two-resident/four-context simulation gates
- **Claim:** the original ternary registered read made Vivado reject both `ram_style="block"` attributes and use 173 total `RAM64M` primitives. Independent registered I/D read outputs map the histories to two `RAMB36` blocks. Placed use falls from 50,941 to 50,154 LUTs (95.75% to 94.27%), registers fall from 21,640 to 21,577, and BRAM rises from 80 to 82 tiles. Signoff WNS improves from +1.777 to +3.390 ns; both builds have zero setup/hold failing endpoints and complete bitstreams. The directed recorder result remains exactly two I misses, one D miss, and timestamps `0x623be`/`0x623fd`; the disarmed context-switch smoke and all 15 harness checks pass.
- **Evidence:** reproducible comparison and source job identifiers in `logs/cache-miss-trace-route-20261006/`; routed summaries in `logs/fpga/20261006T173322Z-6da84fc6/` and `logs/fpga/20261006T182248Z-e860ceea/`; corrected top/BlackParrot revisions `e860ceea`/`52c5dde70`.
- **Meaning:** the measurement hardware fits with 3,046 LUTs and 58 BRAM tiles still unused, and the BRAM-compatible structure improves timing margin while preserving behavior. RL-028 proves physical readout; the same interface is ready for OQ-005's Linux interval.
- **Limits:** the routed comparison alone does not prove Linux scheduler-line coverage. The WNS improvement includes placement randomness from the changed netlist, so the resource delta is the stronger causal result.

### RL-028 — The ordered miss recorder is deterministic on FPGA/real DDR

- **Status:** accepted directed physical validation
- **Scope:** exact routed top `e860ceea`, BlackParrot `52c5dde70`, bitstream `f4a183d8…`, directed NBF `e30d602e…`, the PYNQ-Z2 HP0/PS-DDR path, and nine clean physical invocations
- **Claim:** all nine samples find the intended physical cold-code and cold-data lines, report exactly two I-cache misses and one D-cache miss, preserve guest/core/runner pass, and place the data request exactly 47 core cycles after the selected instruction request (47/47/47 min/median/max). The identical NBF records 63 cycles in simulation. The initial standard 64-MiB runner failed before NBF loading because CMA could not allocate 16,384 contiguous pages despite 118,492 KiB reported free; a temporary 16-MiB runner covers the NBF's highest write at offset `0x9e67`, uses only the first 8-MiB usage bucket, and frees cleanly. The original 64-MiB runner was restored at its exact prior hash after measurement.
- **Evidence:** raw retained transcripts, transferred board archive, per-file hashes, reproducible `analyze.py`, and `results.json` in `logs/cache-miss-trace-board-20261006/`; simulation control in `logs/cache-miss-trace-sim-20261006/`; routed identity in `logs/fpga/20261006T182248Z-e860ceea/`.
- **Meaning:** the recorder's synthesis, CSR control/readback, physical-address identity, ordering, and timestamp behavior are now proven on the real memory path rather than inferred from simulation. The zero-range nine-sample interval also rejects host timing noise in this directed result. The shorter physical interval shows that the simulator's fixed memory behavior is not a cycle-exact proxy for this board.
- **Limits:** 47 cycles is accepted I-request to accepted D-request, including instruction-miss service and intervening execution; it is not a direct DRAM response latency. This program contains no Linux context switch, does not fill the 256-entry histories, and does not measure useful-before-demand replay coverage.

### RL-029 — Linux handoff misses are overwhelmingly shared privileged instructions

- **Status:** accepted physical Linux measurement
- **Scope:** fresh-boot same-CPU futex handoff on the recorder bitstream and corrected non-debug Linux image, with independent source-to-peer and peer-to-source windows
- **Claim:** the complete sliced windows contain 48 I/3 D misses in 11,379 cycles and 218 I/10 D misses in 28,883 cycles. Their 40,262-cycle sum is within 412 cycles (1.01%) of the complete 40,674-cycle full-window run. Of the 266 sliced instruction misses, 262 (98.5%) map to kernel or OpenSBI executable text. The two instruction windows have 48 and 215 unique lines, with maximum per-set occupancies of ten and nine in an eight-way cache. Across repeated full-window prefixes, an eight-most-recent-lines-per-set predictor trained on the preceding run covers 222/256 (86.7%) instruction records but only 14/35 (40.0%) data records.
- **Evidence:** exact image identities, board-side log hashes, counts, mappings, overflow behavior, and analyzer are in `logs/linux-cache-miss-trace-20261006/README.md`, `linux-tests/cache_miss_trace_capture.c`, and `tools/analyze_cache_miss_trace.py`.
- **Meaning:** the first replay prototype should prioritize a shared privileged-instruction slice and preserve per-set recency. Duplicating a complete observed footprint per task wastes state on the dominant shared code and can overfill individual sets even when total byte capacity fits. Private data and userspace instruction histories should remain small, confidence-gated additions.
- **Limits:** the two legs are independent fresh-boot runs, and one source-to-peer instruction request was accepted 43 cycles after the disarm timestamp. The recorder observes accepted demand requests rather than response completion or whether a replay would arrive before demand. Full-window instruction history can overflow at 256 entries, and this workload does not establish stability across broader scheduler and application mixes.

### RL-030 — Full-line replay needs a 57-cycle reverse response start

- **Status:** conditional measured-input architectural bound
- **Scope:** RL-029's unique-line counts and first-demand timestamps, an eight-beat 64-byte response, the measured 17--25-cycle data-installer range, shared transport slots, and separate ideal I/D installers
- **Claim:** using the direct path's 17-cycle installer, the forward first instruction demand at cycle 1,006 permits a first-response-beat latency up to 78 cycles for four transport slots to deliver and install all 48 unique instruction lines. At a conditional 41-cycle response start, 17/19-cycle installers finish at 865/961 with 141/45 cycles left; 21/25-cycle rates finish at 1,057/1,249 and miss by 51/243. The reverse first instruction demand at cycle 82 requires its first response beat by cycles 57/55/53/49 for 17/19/21/25-cycle installers, leaving 16/14/12/8 cycles at the conditional 41-cycle input. The physical 41-cycle demand result does not prove this full-line condition.
- **Evidence:** reproducible latency sweep, thresholds, and endpoint distinctions in `logs/linux-cache-replay-bound-20261006/`; the physical load endpoint is documented in `logs/fpga-memory-latency-20260923/README.md`.
- **Meaning:** aggregate capacity is not enough to establish replay usefulness. The forward leg is tolerant enough for pre-wake shared-code replay, while the reverse leg needs retained early lines, an earlier trigger, or a physically verified full-line path whose first response beat begins within 57 cycles.
- **Limits:** this is an optimistic capacity bound, not end-to-end replay. It assumes exact addresses and ordering, consecutive response beats, no dirty victims or scheduler interference, and a hypothetical instruction installer matching the data path. The physical full-line response and I-cache installation latencies are unmeasured, and the unavailable local raw sequence prevents a per-line early/late classification.

### RL-031 — Concurrent full-line installation is usually 19 cycles, not 17

- **Status:** accepted retained-waveform measurement
- **Scope:** `prefetch_install_state_r` active intervals in the accepted direct-installer, concurrent response-buffer, reconstructed banked minimal-wrapper, and banked FPGA-facing 64-bit-wrapper traces
- **Claim:** all 40 direct-path installations take exactly 17 cycles. Concurrent response buffering and the banked minimal wrapper both produce `16:1, 17:3, 18:3, 19:25, 21:1`, for a 19-cycle median, 18.70-cycle mean, and 21-cycle maximum. The FPGA-facing 64-bit wrapper has a 19-cycle median, 19.61-cycle mean, and 25-cycle maximum. Complete ten-slot banked runs take 802 cycles in the minimal wrapper and 805 cycles in the FPGA-facing wrapper. The historical 771-cycle result is not reproducible from the committed state, and reducing the reconstruction to four slots slows it to 2,241 cycles.
- **Evidence:** reproducible VCD parser, exact source paths, distributions, and results in `logs/full-line-installer-timing-20261006/`.
- **Meaning:** the strict 479-line Linux target permits at most 18 cycles per data line under RL-022's conditional 41-cycle response input. The direct path meets that rate but sacrifices concurrent issue; every measured concurrent implementation misses it. The exact banked trace therefore rejects the previous whole-footprint feasibility inference and shifts the target to a prioritized shared kernel prefix or retained state.
- **Limits:** these are RTL simulation state intervals with a synthetic 40-cycle memory response, not physical DDR measurements. They cover the data cache only. The 64-bit wrapper matches the FPGA interface width, but physical detached full-line latency and instruction-cache installation remain unmeasured.

### RL-032 — Two retired, unaccepted hints explain the four-slot collapse

- **Status:** accepted retained-waveform root-cause measurement
- **Scope:** the exact four-slot, three-stream, 33-node banked full-line reconstruction under the synthetic 40-cycle memory model and 32-bit minimal wrapper
- **Claim:** all 33 intended hint addresses reach the UCE, but only 31 allocate and issue. Stream 2's node-1024 line (`0x8001d000`) and node-92 line (`0x8000e700`) each attempt twice while all four slots are occupied, receive neither an accept nor `prefetch_drop`, and then retire 4.5 cycles after the final attempt. Those exact two lines become the trace's only ordinary fills. Each ordinary 64-byte fill is serialized into sixteen 32-bit requests and spans 676/670 cycles; their 1,346-cycle sum is 93.5% of the 1,439-cycle increase from 802 to 2,241 cycles. Full occupancy occurs for only 223 cycles (10.0%), while the two fallbacks create 700/716-cycle allocation gaps and cause four completed accepted hints to enter the installer drop state instead of publishing.
- **Evidence:** `logs/banked-full-line-timing-20261006/analyze_queue_depth.py`, `results-queue-depth.json`, the retained `events-k4.vcd.xz`, and checked `k4-trace-run.log`.
- **Meaning:** the four-slot result exposes a hint-retirement/backpressure bug rather than an intrinsic four-slot throughput limit. The intended UCE refusal reaches the memory pipe, but it does not keep the architectural hint alive until acceptance. A pending-hint queue or correct replay-to-retirement coupling should avoid the two catastrophic demand fallbacks; demand refill should also retain full-line transport. This does not remove RL-031's independent 19-cycle installer-rate limit.
- **Limits:** the exact fallback penalty is specific to the minimal wrapper's serialized ordinary path and synthetic memory. RL-033 measures the fixed four-slot rerun; the FPGA-facing 64-bit/physical-DDR endpoints remain unmeasured.

### RL-033 — Correct hint replay restores four-slot throughput to 900–905 cycles

- **Status:** accepted fix with retained before/after waveform measurement
- **Scope:** RL-032's exact four-slot workload after pipeline-aligning a late D-cache-busy suppression bit into architectural replay, measured through both the 32-bit minimal and FPGA-facing 64-bit wrappers
- **Claim:** the fixed minimal-wrapper run takes 900 cycles instead of 2,241 and retains checked guest/core/host pass markers. It accepts and allocates all 33 intended hints, issues exactly 33 nonzero-ID AXI prefetch lines, and has zero ordinary AXI requests, UCE drops, or installer-drop entries. The fix recovers 1,341 cycles, 93.2% of the broken path's 1,439-cycle excess over the 802-cycle ten-slot control. Its residual is 98 cycles (12.2%). The fixed FPGA-facing wrapper takes 905 cycles, 100 above its 805-cycle ten-slot control, and has the same complete 33-line/no-fallback accounting. The 32-to-64-bit change shifts fixed/ten-slot totals by only 5/3 cycles.
- **Evidence:** BlackParrot commit `d4c20786d`; reproducible minimal and FPGA-facing analyzers, results, filtered VCDs, and checked run logs in `logs/banked-full-line-timing-20261006/`.
- **Meaning:** queue depth and correctness were previously conflated. Four slots carry this three-stream synthetic workload efficiently once late busy suppression reliably replays. Ten slots still remove about 100 cycles of retry delay, but adding six slots buys only about 11% relative to the fixed four-slot runtime. The matched wrapper results show that this residual is queue/replay scheduling rather than external beat width. The Linux replay decision should therefore be based on installer rate, first-demand deadlines, and physical memory behavior rather than the rejected 2,241-cycle result.
- **Limits:** both wrappers use synthetic 40-cycle memory. Routed fit, physical DDR timing, and useful-before-demand Linux replay remain unmeasured.

### RL-034 — Five slots reproduce ten-slot runtime in both wrappers

- **Status:** verified retained-waveform measurement
- **Scope:** the fixed replay path with three resident streams, 33 dependent nodes, and the nominal 40-cycle synthetic memory model, measured through the minimal 32-bit and FPGA-facing 64-bit wrappers
- **Claim:** the minimal-wrapper depth curve is 1,106/900/802/802 cycles for three/four/five/ten slots. Three and five slots both accept and allocate all 33 hints, issue 33 nonzero-ID AXI line reads, and have no ordinary fallback or installer drop. Three slots are full for 724/1,107 samples (65.4%); five are full for 74/803 (9.2%). The fourth slot saves 206 cycles and the fifth saves the remaining 98. The FPGA-facing curve independently measures 905/805/805 for four/five/ten slots. Its five-slot run has the same complete 33-line/no-fallback accounting, is full for 73/806 samples (9.1%), and retains the ten-slot wrapper's exact three-cycle increase over minimal (802 to 805).
- **Evidence:** `logs/banked-full-line-timing-20261006/analyze_queue_fix_k3.py`, `analyze_queue_fix_k5.py`, `analyze_queue_fix_k5_main64.py`, their results, retained filtered VCDs, and checked run logs
- **Meaning:** matching slot count to stream count is insufficient because completed lines still wait for the shared installation path. Extra entries let new hints allocate while older entries await response or installation. Five is the minimum measured depth that reproduces ten-slot runtime in both simulated wrappers; slots six through ten have zero measured benefit here. This is not yet a physical-DDR or Linux sizing result.
- **Limits:** the run uses a synthetic memory model and the minimal wrapper. It reaches checked guest/core/host pass markers before the pre-existing DPI finalization assertion.

### RL-035 — The five-slot design routes on PYNQ-Z2 with timing met

- **Status:** accepted routed implementation and verified bitstream package
- **Scope:** `e_bp_unicore_zynqparrot_prefetch5_cfg` with five detached-prefetch transaction entries, two resident architectural register banks, and ten logical contexts, at top commit `4e527cad1`, BlackParrot commit `d4c20786d`, 12 Vivado threads, the selected 20 MHz AXI clock, `Flow_AreaOptimized_high` synthesis, and `Area_Explore` implementation on XC7Z020
- **Claim:** the default flow fails after optimization at 53,448 logic LUTs versus 53,200 available. The area flow places at 46,349 logic LUTs (87.12%), 49,303 total slice LUTs (92.67%), 27,968 registers (26.29%), 85.5 BRAM tiles (61.07%), and 11 DSPs (5.00%). Routing completes with zero failed/unrouted/partially routed nets and zero overlaps. Signoff timing has WNS 0.263 ns, TNS 0, WHS 0.021 ns, and THS 0 across 92,321 setup and 92,255 hold endpoints. Bitgen and package verification pass; package SHA-256 is `07de6afb133990998135da3fc26ae70e26386cb99564a964d5b34506f67c6e5c` and bitstream SHA-256 is `933777e636853c0a6e9c6cb6d068778b4a49209510d16e49226c63bcbb6793ea`.
- **Evidence:** `logs/fpga/20261007T023053Z-19e7bb55/console.log` for the default-flow failure; `logs/fpga/20261007T030907Z-4e527cad/{summary.txt,revisions.txt,console.log,black_parrot_bd_1.zynq.pynqz2.tar.xz.b64}` for the passing route and verified package; the exact outcome is summarized in `logs/banked-full-line-timing-20261006/README.md`.
- **Meaning:** five slots are not merely a simulation-only capacity point. The complete corrected design fits the target FPGA with 6,851 logic LUTs free after placement and meets timing without removing the replay fix. Area strategy selection, rather than an architectural rollback or invasive RTL reduction, resolves the narrow default-flow capacity failure.
- **Limits:** this proves route, timing, and artifact integrity. Board liveness passed, but physical performance acceptance exposed RL-036's adjacent-word regression and a ten-stream failure. The routed artifact predates that fix, so RL-034's five-versus-ten throughput equality remains synthetic.

### RL-036 — Whole-sector consumption erased narrow-prefetch speedup

- **Status:** physical root cause fixed for passing two-to-four-stream workloads; ten-stream correctness remains rejected
- **Scope:** the fast 16-byte side-buffer path on the five-slot `d4c20786d` route and ten-slot `db5a52da5` control, using the matched 2/3/4/10-stream real-DDR benchmark; corrected current RTL at BlackParrot `4f56fba7d`
- **Claim:** a three-repetition alternating-order five-slot physical sweep measures demand near 60,000 cycles, serial prefetch at 82,411--82,608, software interleaving at 60,678--62,851, and hardware switching at 69,893--74,377 for 2/3/4 streams; all 45 accepted runs pass, the largest within-cell range is 0.15%, and the separate ten-stream hardware gate reproduces `CORE FAIL`. A newer ten-slot control remains slow (61,168 two-stream software and 76,023 ten-stream hardware), excluding five-slot capacity as the performance cause. Commit `10cb0e645` invalidated both words of a 16-byte advisory entry after the pointer word hit, so the adjacent value load incurred one ordinary DRAM miss per node. A focused physical probe confirms this directly across 96 sectors split evenly between the buggy five- and ten-slot images: the first prefetched word is always 3 cycles, while its adjacent word has a 42-cycle median and 42--45-cycle combined range. The 39-cycle median penalty predicts 49,920 extra cycles over 1,280 nodes, accounting for 91.1--103.8% of the observed software-interleaved regression and 96.4--97.1% of the serial-prefetch regression; demand medians differ by only 7--30 cycles between images. The corrected simulator instead measures 3 cycles for both words in all 16 samples. Restoring word-granular consumption while retaining rotating stale replacement reduces the exact current two-stream narrow simulation from 80,803 to 10,715 cycles (7.54x), passes a five-slot/ten-stream hardware-switch simulation, and passes the stale-entry replacement regression.
- **Evidence:** exact identities, physical table, controls, mathematical interpretation, and corrected simulation results in `logs/five-slot-physical-20261007/`; RTL fix `4f56fba7d`; the original fast physical matrix is retained in `logs/prefetch-mlatency-20260926/board-real-ddr-18mhz-v1/`.
- **Meaning:** the recent poor FPGA numbers did not disprove latency overlap and were not caused by reducing ten request slots to five. The benchmark needs both words returned by each narrow hint; discarding the neighbor adds a directly measured 39-cycle median demand penalty to every node. Rotating replacement handles unused neighbors without sacrificing useful spatial data. The corrected simulator recovers the expected prefetch advantage.
- **Limits:** the corrected image now measures 19,262/21,823/22,723 hardware cycles for two/three/four streams, or 3.119x/2.749x/2.644x versus matched demand. The ten-stream gate still fails after the adjacent-word fix, so passing simulator correctness does not establish full physical correctness.

### RL-037 — The switch-drain fix is timing-clean and area-neutral

- **Status:** store-handoff behavior physically accepted; ten-stream correctness rejected and localized
- **Scope:** the exact five-slot, two-resident/ten-logical-context, 20 MHz corrected narrow-prefetch design at top commit `c43549d3` and BlackParrot `ee522c10c`, including the local-memory drain interlock before CSR `0x800` handoffs
- **Claim:** matched synthesis uses 52,144 slice LUTs, 20 fewer than the pre-fix design, with identical 27,967 registers, 85.5 BRAM tiles, and 11 DSPs. The first complete `Area_Explore` route was legal but failed signoff at WNS/TNS `-0.377/-24.827 ns`; the limiting 68-level dispatch-to-I-cache path was unrelated to the new interlock. Aggressive post-route physical optimization changed eight cells or nets, added and removed none, and recovered 0.397 ns to WNS/WHS `+0.020/+0.023 ns`. A second identical physical-optimization pass made no changes because Vivado only optimizes negative-slack paths. An independent `AggressiveExplore` route from the identical placed checkpoint improves final WNS/TNS to `+0.198/0 ns` while preserving WHS/THS `+0.023/0 ns`, with 85,098/85,098 routable nets complete and zero routing errors. This is 0.178 ns or 9.9x more setup margin, moving the timing-derived ceiling from 20.008 to 20.080 MHz. DRC, bitgen, and package verification pass. The preferred package/bitstream SHA-256 values are `e541d1e8994c3e3deac89c4617b313bd3dfdf5b49056e50645560c148368e3b6` and `9d6c4eb5e90f85ddc225c08d6fd930b1e405cf45cd15ae59e17c1356e052c29b`.
- **Evidence:** `logs/context-switch-drain-interlock-20261007/`, the original recovered route in `logs/fpga/20261007T085800Z-c43549d3-postroute-physopt/`, and preferred aggressive route in `logs/fpga/20261007T131845Z-c43549d3-aggressive-route/`; launcher timing gate commit `aed30e72`
- **Meaning:** the interlock does not consume measurable state or reduce the selected 20 MHz clock. Three physical repetitions exactly reproduce the predicted 12.11/16.11-cycle four-store resident/nonresident handoffs. On sustained prefetch workloads it adds about one cycle per resident handoff, producing +1,284/+645/+435 cycles for two/three/four streams. The route also exposed and fixed an infrastructure error: Vivado can write a bitstream and exit zero with negative WNS, so artifact existence alone cannot establish an acceptable image.
- **Limits:** the preferred fixed image is loaded and its store behavior is accepted, but the fresh zero-gap ten-stream test returns from its worker, then reloads zero from the saved `ra` stack slot and traps at PC 0. No-successor and prime-only controls pass; context-4-only hints fail while five other hinting contexts pass. The context-4 step sweep passes through 120 nodes per stream and fails at 124; an alternating fresh-overlay repeat makes the 120-step point pass twice more at 68,592/68,620 cycles and the 124-step point fail twice more at exactly minstret 2,552. This rejects a simple five-slot, aggregate-request, or probabilistic-latency explanation. Three fresh-overlay zero-gap repetitions all stop at exactly minstret 2,348, and two fresh trap-reporting repetitions reproduce the same PC-zero/register signature at minstret 2,362 with only a four-cycle spread in the measured interval; the endpoint is deterministic. Successor-only hints fail, prime-only passes, a terminal fence fails, and a double stack reload returns zero twice. The residual fault is therefore after the final handoff in the stack reload path, not an undrained result store or a demonstrated context-register restore error. The four newly added context-4 hint destinations map to sets 22/28/32/12. The same four iterations add 40 ordinary demand nodes and two map to the saved stack line's set 62, but that correlation is not the missing mechanism: the exact simple-memory 120/124 traces and a 40-cycle/four-outstanding 124 trace all evict the stack line earlier on `0x80014f80`. Every trace captures the correct dirty words, accepts all eight writeback beats, and refills the correct line at the epilogue. The 40-cycle model passes with all 248 prefetch words accepted, although its 788,788-cycle total makes it an ordering stress test rather than a board-runtime calibration. A physical replacement-order divergence remains possible but unproved. A simulator-validated reporter plus same-line/different-sector, adjacent-set, and same-set/different-tag stack variants are built. The old full-line prefetch installer cannot evict the stack line in current RTL: its entry condition is tied low, while detached replies use a dedicated side-buffer acknowledgment and assert no L1 data/tag/status SRAM write. The retained ten-stream waveform confirms this dynamically: all 2,560 accepted detached words use the prefetch-data opcode, with zero accepted tag or status commands and the installer idle throughout. It also shows both saved-word stores hitting L1 way 1 and draining with the correct data and full masks in their issue cycles; neither saved address is written again among the 44 subsequent-window write-buffer drains. The routed checkpoint further maps the side buffer to 55 distributed RAM32M roots at 55 SLICEM locations, physically separate from L1's eight data RAMB36E1s, three tag RAMB36E1s, and one status RAMB18E1; no memory location is shared. The corresponding worst selected setup/hold margins are +14.783/+0.262 ns into and +12.285/+1.232 ns out of side-buffer storage, and +2.491/+0.196 ns into and +36.273/+0.630 ns out of L1 data storage; neither boundary is globally critical. The physical failure is now a board-only schedule/state-corruption problem triggered by the added iterations; no tested simulation identifies the stage that loses the saved word. The ordinary AXI path is single-outstanding and does not accept a new request until the prior response, reducing the likelihood of an intentional write/read ordering hole. An isolated all-set sweep forces 64 dirty target evictions and refills, proves every target absent with an all-ones slow-reload mask, and preserves all 512 checked words in both simulation and the physical FPGA; set 62 also passes. The recovery reporter then reads zero for all four known words in the original set-62 stack line. Moving the saved pair within that line still fails; moving it 4 KiB to a different tag in the same set fails twice at `minstret=2,348`; moving it 64 bytes into set 61 passes twice at 76,122/76,123 cycles. In those passing runs, the original set-62 `nodes` local still prints zero, proving that the old line is erased while the relocated return-critical words survive. The placement binaries differ only in the matched `run_window` stack displacement/restoration, and fresh overlay reloads plus alternating order reproduce the split. The fault therefore follows set 62 under the concurrent ten-stream schedule, not the original line address, tag, sector, or a general routed dirty-writeback defect.

### RL-038 — The physical fault is instruction-spacing sensitive

- **Status:** accepted physical timing-race localization
- **Scope:** the fixed 20 MHz route, ten logical contexts, context-4-only successor hints, 124 nodes per stream, fresh overlay before every run, and hash-pinned checkpoint NBFs
- **Claim:** context zero's saved return address remains `0x80000300` at every tested checkpoint from 124 through one node remaining, and each checkpoint read rescues execution. With no earlier stack touch, lightweight probes see it correct after contexts 0 and 1 complete their final nodes but zero after context 2; their first zero appears after context 2's final pointer demand to set 7. A matched control then uses byte-identical `.text` for entry, post-pointer, post-payload, and post-publication observations, with NBF maps differing only at one volatile stage word. All four matched variants read `0x80000300` and pass in 77,127--77,193 cycles. The common stage-selection instructions suppress the failure before any observation.
- **Evidence:** sources, disassemblies, manifests, exact FPGA transcripts, NBF hashes, byte-identical text hashes, and the re-extracted set-7 simulator trace in `logs/context-switch-drain-interlock-20261007/stack-slot-diagnostics/{stack-sentinel,final-lap-sentinel,context2-event-sentinel,matched-event-sentinel}/`; machine-readable summary in `logs/context-switch-drain-interlock-20261007/result.json`
- **Meaning:** the set-7 load is a timing landmark in the lighter probe, not a proven direct corruptor. The robust result is a narrow instruction-spacing-sensitive cross-request or response/context-transition race. One stack-line recency update and modest common-loop spacing independently suppress it, while ordinary set-associative replacement cannot make a set-7 request evict set 62.
- **Limits:** every stack checkpoint is an intervention, and the common matched instrumentation changes traversal spacing enough to remove the failure. The board exposes no internal cache waveform, so the exact corrupting internal signal and cycle remain unmeasured. The simulator supplies timing and hit/miss context but does not reproduce the corruption.

### RL-039 — One cycle adjacent to the switch repairs the physical fault

- **Status:** accepted physical causal placement and cost result
- **Scope:** the exact physical-failing ten-stream, 124-node-per-stream, context-4-successor-hint NBF
- **Claim:** replacing the four-byte hot-loop jump with same-size `c.nop; c.j` changes exactly one NBF record and no address or data. In the alternating fresh-overlay physical matrix, both original repetitions and the unreachable-NOP `c.j; c.nop` encoding control fail, both post-switch executed-bubble repetitions pass at 72,038/72,033 cycles, the pre-switch bubble passes at 71,992, and the body bubble fails. Every target invocation used bitstream SHA `9d6c4eb...29b`, the hash-pinned NBF, and control program SHA `2dd9c411...f30`.
- **Evidence:** exact single-record diffs, reproducible patch builder, simulator controls, ten downloaded physical transcripts, transcript hashes, and machine-readable results in `logs/context-switch-drain-interlock-20261007/stack-slot-diagnostics/post-switch-bubble/`, especially `physical-matrix-20261012-r2/`
- **Meaning:** an executed cycle is causal, compressed-jump encoding is excluded, and a general loop-period explanation is excluded. One cycle immediately before or after the handoff repairs the zero-gap boundary; the physical evidence does not distinguish the exact outgoing-hint, handoff, or incoming-request signal that otherwise corrupts state.
- **Performance result:** the exact k2 original and unreachable-NOP encoding control both measure 19,262 physical cycles. The post-switch bubble measures 20,540, adding exactly 1,278 cycles for 1,278 nonfinal handoffs, matching the simulator projection. It is 6.64% slower than the original hardware path but remains 2.925x faster than the 60,077-cycle demand baseline, versus 3.119x originally.
- **Limits:** the single-cycle software placement is a demonstrated workaround and implementation bound, not yet an RTL repair. A hardware interlock still needs targeted simulation, routing, and physical acceptance; a more selective condition requires evidence beyond this matrix.

### RL-040 — Active detached transport is already idle before the final corruption boundary

- **Status:** accepted simulator temporal constraint; physical mechanism unproved
- **Scope:** the retained exact 124-step FST and the final 3,800-cycle interval containing the lightweight context-2 boundary
- **Claim:** all ten final switch dispatches have `mem_busy=0`, `mem_ordered=1`, and `ctxtsw_order_haz_v=0`. The final lap has zero detached request accepts, response accepts, completed fills, or side-buffer writes. The last fill and last side-buffer write precede the context-2 demand by 616 and 614 cycles. One valid prior-lap context-4 entry remains; only context 4 consumes its two words, later than the context-2 boundary. Retained prefetch state is present at 38/48 traced dispatches (79.2%) and the first 4/10 final dispatches, including context 2. Nine of ten final pointer demands are ordinary L1 misses and all replay-hit exactly 13 cycles later: contexts 0 and 1 already exhibit the same pattern while the lightweight physical stack checkpoint remains correct, context 2 is the third, and context 3 repeats it afterward.
- **Evidence:** retained extractor source, exact TSV, and machine-readable analysis under `logs/context-switch-drain-interlock-20261007/stack-slot-diagnostics/post-switch-bubble/`
- **Meaning:** an interlock conditioned only on in-flight AXI/prefetch transport would not activate around contexts 0–2 in this schedule. Context 2 is neither the first ordinary miss nor latency-distinct, so a generic first-demand-miss condition is also broad and non-discriminating. Retained side-buffer state covers the boundary but is only moderately selective: it would avoid 10/48 traced bubbles, about 20.8% of unconditional overhead if cost scales directly. A narrower request/context transition remains preferable if the physical placement matrix shows that a bubble repairs the failure.
- **Limits:** the simulator preserves the stack line and may not reproduce physical response timing. This excludes candidate conditions in the traced schedule; it does not prove the FPGA's corrupting signal.

### RL-041 — The commit-cycle boundary pulse expired before target dispatch

- **Status:** rejected by exact physical acceptance
- **Scope:** BlackParrot `6c79a4210`, which blocks backend issue for the one cycle after every committed context switch while allowing the frontend issue queue to fill
- **Claim:** the clean traced nonresident U-mode handoff and the 1,280-node two- and ten-stream hardware-context workloads pass. The retained k2 waveform contains 1,292 committed switch pulses and 1,292 settle pulses after reset, proving the interlock activates for every switch in the complete run. The issue queue is empty in every protected cycle. The archived byte-identical k2 NBF still measures exactly 19,258 cycles before and after the RTL change, so its one-cycle temporal separation is fully overlapped by the existing frontend gap; unlike the software NOP, it does not inherently add one retired cycle per handoff.
- **Evidence:** commands, exact identities, retained transcripts, waveform extractor, pulse counts, and machine-readable results in `logs/context-switch-drain-interlock-20261007/rtl-interlock-20261012/`
- **Physical result:** the routed image at top `65f30750` / BlackParrot `6c79a4210` meets timing at WNS/WHS `+0.431/+0.025 ns`. On fresh overlays, the exact original ten-stream NBF again produces `CORE FAIL` twice, while the exact k2 control passes at the unchanged 19,262 physical cycles. The implementation is therefore physically rejected without evidence of a generally bad image.
- **Meaning:** the simulation's zero cost was the defect. The pulse asserted only during the already empty redirect gap and cleared before the first target queue head arrived, so it never changed occupied pipeline sequencing and did not supply the executed cycle demonstrated by RL-039.
- **Evidence:** routed artifacts in `logs/fpga/20261012T162001Z-65f30750-direct-worker/` and hash-pinned physical transcripts in `logs/context-switch-drain-interlock-20261007/rtl-interlock-20261012/physical-board-r1/`

### RL-042 — The protected-RPC software contract costs 287 cycles warm versus 76 for a function call

- **Status:** accepted clean traced simulator baseline; hardware fast path not implemented
- **Scope:** two U-mode Sv39 domains, one monitor-held depth-one return, one caller/capability pair, fixed server entry, four register arguments, one result, distinct private code/data/stack pages, and one explicitly shared page
- **Claim:** the test rejects an invalid capability without entering the server, maps the same private VA to distinct physical pages, preserves the caller private value and ABI state, prevents user control of the return continuation, transfers the shared payload, and completes with its specific PASS marker plus guest/host PASS. A matched ordinary call doing the same useful loads, arithmetic, and stores takes 76 cycles. Flush-on-every-switch protected calls take 824 cycles first and 450 repeated; retaining safe entries under the implementation's two distinct ASIDs reduces them to 773 and 287. The repeat trace attributes 109/83 cycles to the entry/return monitor instruction streams, 57/6 cycles to reaching those handlers, and 25 cycles to the server body through its return ECALL.
- **Evidence:** source/harness gate, accepted logs, disassembly, FST extractor, dispatch timeline, hashes, and machine-readable result in `logs/protected-rpc-reference-20261012/`
- **Meaning:** the first hardware opportunity is now measured rather than estimated. Removing the two software monitor streams addresses 192 of the 211 cycles separating the repeated protected path from the matched function call; accelerating the protected transition can plausibly approach tens of cycles without changing application semantics.
- **Limits:** this is a bare-metal M-mode reference with one immutable capability and no interrupts or nested calls. It does not yet prove Linux integration, revocation, multi-client scheduling, or a hardware `pcall`/`preturn` implementation.

### RL-043 — A pending interlock holds exactly the first issue-ready target cycle

- **Status:** accepted routed and physical FPGA repair
- **Scope:** BlackParrot `30479f1a2`, which latches a committed switch across the empty redirect gap and consumes the latch only when the first target queue head would otherwise issue
- **Claim:** the nonresident U-mode handoff and 1,280-node ten- and two-stream tests reach their specific guest markers plus guest/host PASS. The nonresident trace has two switches and exactly two issue-ready interlock edges. The ten-stream trace has 1,340 switches and 1,340 such edges; its measured interval rises from 23,972 to 25,264 cycles, exactly one cycle for each of 1,292 timed handoffs. The byte-identical archived k2 NBF rises from 19,258 to 20,547 simulator cycles, 1,289 cycles or 6.69%, while retaining 2.924x speedup over the 60,077-cycle demand baseline.
- **Physical result:** top `9990e673` / BlackParrot `30479f1a2` routes with WNS/WHS `+0.150/+0.035 ns`, 50,099 LUTs, 27,995 registers, 85.5 BRAM tiles, and 11 DSPs. On the exact bitstream SHA `347d3281...2e3a`, the formerly failing original k10 NBF passes twice at 72,038/72,042 cycles after fresh overlays. The byte-identical k2 control passes at 20,547 cycles, exactly matching corrected simulation.
- **Evidence:** source identity, waveform counts, exact-NBF transcripts, route/package hashes, and machine-readable results in `logs/context-switch-drain-interlock-20261007/rtl-interlock-20261012/pending-interlock-20261013/`; route job `logs/fpga/20261013T071833Z-9990e673-direct-worker/`
- **Meaning:** the hardware now implements the occupied target-boundary delay physically bounded by RL-039. Unlike the rejected commit-cycle pulse, it cannot be hidden inside the empty frontend redirect gap. Its cost is consequently close to the explicit software bubble and is deterministic at one issue opportunity per switch.
- **Limits:** the simulator still does not reproduce the physical corruption, so the interlock is a physically validated conservative repair rather than an internally observed corruption mechanism. Its deterministic one-cycle-per-handoff cost remains.

### RL-044 — Existing unprotected two-context RPC costs 109 cycles warm versus 31 direct

- **Status:** accepted clean traced simulator transport bound; protected hardware path not implemented
- **Scope:** two resident U-mode contexts with distinct Sv39 roots/ASIDs and private pages, one explicit shared page, four integer arguments, one result, and the existing CSR `0x802` register-seed plus CSR `0x800` switch interface
- **Claim:** same-address timed helpers measure 224/31 cycles for first/warm matched direct service and 179/109 cycles for first/warm raw context RPC. The meaningful warm transport premium is 78 cycles. The raw waveform partitions 109 cycles into 53 from timer read through four argument writes and call-switch dispatch, 6 for the call handoff, 44 from parked-server resume through result seed and return-switch dispatch, and 6 for the return handoff. Both domains retain their private values and two distinct argument tuples return the expected results.
- **Evidence:** test/harness source, accepted transcript, disassembly, complete selected-PC dispatch stream, boundary summary, FST/ELF/NBF hashes, and machine-readable result in `logs/rpc-context-transport-20261013/`
- **Meaning:** the 287-cycle warm software-protected reference is not a switch-mechanism floor. Most avoidable raw cost is four separately serialized argument writes and a separate result write. An atomic `pcall`/`preturn` using the existing switch machinery has a measured first target around 45--50 warm cycles, subject to RTL validation.
- **Limits:** the raw interface is intentionally unsafe: the caller chooses target registers and execution state. The 45--50-cycle figure is a design estimate from measured boundaries, not a protected-hardware result.

### RL-045 — Atomic protected RPC reaches 71 cycles warm but exposes a repeat-entry frontend epoch bug

- **Status:** accepted traced simulator checkpoint with an explicit correctness limitation; route and FPGA validation pending
- **Scope:** CSR `0x808` `pcall` and CSR `0x809` `preturn`, one M-installed capability from resident U-mode context 0 to resident U-mode context 1, fixed server entry, hardware-held depth-one continuation, atomic `a0`--`a3` argument transfer, atomic `a0` result transfer, two distinct Sv39 address spaces, and a hostile U-mode descriptor overwrite attempt
- **Claim:** invalid call and return operands retire locally, U-mode cannot replace the M-installed protected entry, both calls produce the expected results, private mappings remain distinct, and the run reaches its specific marker plus guest/host PASS. The matched direct helper measures 220/31 cycles first/repeated and protected hardware RPC measures 43/71. Relative to RL-044's 109-cycle warm raw transport, the protected path is 1.535x faster and reduces the warm transport premium over direct from 78 to 40 cycles, removing 48.7% of that premium.
- **Evidence:** exact source, accepted transcript, FST, ELF/NBF, disassembly, selected-PC stream, extractor, hashes, and machine-readable result in `logs/protected-rpc-hardware-20261013/`
- **Meaning:** atomic register transport and hardware-held authorization remove a substantial fraction of the serialized raw-interface cost while enforcing the initial capability contract. The result is already far below RL-042's 287-cycle warm software reference, although that comparison is not workload matched.
- **Limits:** the 71-cycle repeat includes a 22-cycle recovery through a server-side backward branch. Replacing unreachable post-`preturn` code with NOPs and a self-loop proves that a stale `0x200ac` frontend stream can survive into the second entry and hang. Commit reset, commit-gated launch, metadata bypass, PC-only filtering, and commit-cycle packet-drop experiments were rejected or removed; a correct repair needs a redirect epoch or purge acknowledgment spanning I-cache responses, realignment, and the FE-to-BE queue. The legacy unsafe CSR interfaces also remain enabled, endpoints must be resident, nesting/revocation/interrupt behavior is not implemented, and routed/physical acceptance remains pending.

### RL-046 — Protected entry survives cold replay and reaches 66 cycles warm without recovery code

- **Status:** accepted clean traced simulator repair; route and FPGA validation pending
- **Scope:** RL-045's resident protected RPC contract with eight unreachable NOPs and a fatal self-loop after `preturn`
- **Claim:** both calls enter the fixed service, transfer the protected arguments/result, and reach the specific guest marker plus guest/host PASS. The matched direct helper measures 220/31 cycles first/repeated and protected RPC measures 90/66. The selected-PC trace contains 16 fixed-entry and four `preturn` dispatch samples, with zero at the sequential `0x200ac` NOP and zero at the `0x200cc` fatal loop. RL-044's raw 109-cycle warm transport is therefore 1.652x slower; protected transport adds 35 cycles over the 31-cycle direct helper versus raw's 78, removing 55.1% of the raw premium. The raw regression remains exactly 224/31 direct and 179/109 raw, and all 15 harness tests pass.
- **Evidence:** exact source, accepted transcript, local FST, ELF/NBF, disassembly, complete selected-PC stream, forbidden-PC audit, extractor, hashes, and machine-readable result in `logs/protected-rpc-hardware-fixed-20261013/`
- **Meaning:** the stale repeat entry was a context-state coherence defect rather than a need for a general frontend epoch. The protected redirect selected the fixed entry, but a legitimate ITLB/I-cache replay consulted the target resident context's stale saved NPC and CSR APC. Rebinding both to the capability entry on the protected-call commit makes the fixed-entry authorization invariant survive replay and removes the hidden server recovery path.
- **Limits:** routed timing and FPGA execution are pending. The first two timing-clean routes used stock `e_bp_unicore_zynqparrot_cfg` against prefetch5-configured programs; their timeouts and k2 failure are invalid cross-configuration evidence. A matched `e_bp_unicore_zynqparrot_prefetch5_cfg` route is required. The prototype still has one resident capability and depth-one continuation; unsafe legacy CSRs remain enabled, and nonresident endpoints, nesting, revocation, interrupt semantics, and Linux integration remain unimplemented.

## Superseded or rejected findings

### RS-001 — The 418/396 result is an intermediate configuration

The demand-join milestone measured 418 worker / 396 batch at 200-cycle latency. Later early-restore and final-line redirect optimizations produced the accepted 398/396 result. Future summaries should use 398/396 when describing the final synthetic result and retain 418/396 only when explaining the contribution of individual optimizations.

### RS-002 — The 78.14x synthetic demand ratio is not a general workload speedup

The intermediate 32,661 demand / 418 worker ratio correctly describes that synthetic experiment, but transport and schedule differences make it unsuitable as a broad hardware speedup claim. Use matched worker/batch distance for ideal-overlap discussion and physical sustained results for FPGA claims.

### RS-003 — The two-cycle synthetic gap is not the physical result

Physical DDR measured a 134-cycle worker/batch gap. The synthetic two-cycle result remains valid in its 200-cycle model, but any statement that hardware switching is universally within two cycles of batch is contradicted by the FPGA measurement.

### RS-004 — “Cache conflict” was too vague

Ordinary associativity was not the complete explanation. Accepted evidence separates same-line demand/refill joining from concurrent fills choosing stale replacement ways. Future discussions should name the specific mechanism.

### RS-005 — Predictor alignment did not fix the sustained lifecycle failure

The predictor-bank provenance fix is correct RTL, but the exact failing placement still hung afterward. The translated resident-relaunch fix in RL-009 is the physically confirmed lifecycle root cause.

## Open questions

### OQ-001 — What stops during the next physical nonreturn?

- **Known:** the staged liveness runner can distinguish retirement plateau, timer plateau, and blocked MMIO reads.
- **Missing:** one clean, recovery-qualified physical capture.
- **Blocker:** board SSH is reachable, but the external power controller is still unreachable; the 23-hour uptime proves that no new recovery cycle occurred before the latest status check.
- **Decisive experiment:** power-cycle, wait for PYNQ readiness, reload the exact overlay, verify hashes, then run the staged diagnostic until completion or bounded failure.

### OQ-002 — How much physical worker time is exposed memory waiting?

- **Known:** physical worker is 310 cycles and appears control dominated; batch is 176.
- **Missing:** a same-ELF cold-versus-prewarmed-data comparison with unchanged timed bodies.
- **Decisive experiment:** verify that warmed measured lines survive preparation, alternate cold/warm order, and compare both worker and batch schedules.

### OQ-003 — How well does the mechanism transfer to a faster core or longer-latency machine?

- **Known:** the 200-cycle simulator shows near-batch overlap; the low-frequency FPGA has short core-cycle DDR latency and moderate sustained gain.
- **Missing:** a detailed memory model or physical platform with a realistic higher core-to-memory frequency ratio and matched request capacity.
- **Decisive experiment:** sweep latency, bandwidth, return pacing, slot count, resident count, and switch cost independently using the final RTL and one common benchmark binary.

### OQ-004 — Does an automatic per-context signature retain the modeled and explicit-hint benefit?

- **Known:** the previous-first predictor, depths 1/2/4/10, timeliness, negative controls, storage estimate, and physical correct/stale-hint value have already been measured in RL-013 and RL-014.
- **Missing:** hardware training and replay tied to context selection, forced-cold separate-context execution, and a comparison of automatic signature against explicit hints and no hints.
- **Decisive experiment:** implement the already proposed two-first/adaptive-four signature with consumption confidence, context generation tags, L1 lookup, and counters for issued, consumed, late, unused, and dropped entries. Run scan and trie as positive cases and dependent chains as the no-regression control.

### OQ-005 — Should the large design use background replay or cache-state retention?

- **Known:** RL-018 shows that replay fits the Linux regime with only 1.0–1.5x serial throughput, while two-context retention fits in 4–6 ways and is the only option that can make a five-cycle handoff immediately hot. RL-021 shows overlapping data-line issue. RL-031 traces the exact banked pipeline through request, eight 64-bit response beats, installation, and tag publication: its median installer interval is 19 cycles and maximum 25. RL-032 explains the apparent four-slot collapse: two hints retire after capacity-backpressured, unaccepted attempts, and their serialized demand fallbacks explain 93.5% of the 802-to-2,241-cycle increase. RL-033 fixes that replay race: four slots now take 900/905 cycles in the minimal/FPGA-facing wrappers with 33/33 accepted hints and no fallback, only 98/100 cycles above their ten-slot controls. RL-034 measures the corrected minimal depth curve at 1,106/900/802/802 cycles for three/four/five/ten slots and the FPGA-facing curve at 905/805/805 for four/five/ten; five is the minimum measured depth matching ten slots in both wrappers. Under RL-022's conditional 41-cycle response input, the measured median still completes the strict target in 5,825 cycles, 274 cycles beyond the hot window even when started at yield entry. The 319-line kernel-only target takes 3,374 cycles and must start by cycle 2,177; a generous 2,238-cycle late window misses by 61. RL-024 places the observed eight-hint median target-confidence floor at 75%. RL-019/RL-020 select conditional two-way retention over three static ways. RL-029 shows that 98.5% of sliced instruction misses are shared privileged code. RL-030 requires the reverse first response to begin by cycles 49–57 across the measured installer range.
- **Missing:** physical-DDR detached full-line endpoint timing; useful-before-demand coverage and completion time for an ordered shared privileged-instruction prefix; target-prediction accuracy on broader scheduler workloads; an instruction-cache replay path; and coexistence with real scheduler traffic.
- **Decisive experiment:** replay RL-029's stable shared privileged-instruction prefix through a separate I-cache installer starting at syscall entry, counting issued, completed-before-demand, late, consumed, unused, and dropped lines against recorder-only and replay-disabled controls. Pair it with a physical detached full-line probe so the simulation's conditional 41-cycle input can be replaced with measured request-to-first-beat and final-beat timing.

## Next experiment

The immediate next correctness experiment remains OQ-001 when board recovery is available. For the cache-resume architecture, do not repeat footprint, component, oracle-replay, retention-capacity, recorder-fit, directed recorder validation, Linux miss-capture, or banked-pipeline tracing. The next architectural experiment is ordered useful-before-demand replay of RL-029's shared privileged-instruction prefix, starting at syscall entry and measuring how many lines publish before their actual demands. A physical detached full-line probe should run alongside it when the board is available, replacing the conditional 41-cycle input without blocking the useful-prefix implementation.

## Delta log

- **2026-10-06 — Ledger created after a demonstrated synthesis regression:** a later summary incorrectly promoted the intermediate 418/396 result over the accepted 398/396 result. The ledger now distinguishes baseline expectations, final synthetic evidence, physical-DDR evidence, sustained Linux/FPGA results, and superseded interpretations.
- **2026-10-06 — Resume-footprint omission corrected:** the initial ledger incorrectly listed bounded-history modeling as future work. The repository already contains the completed predictor-depth/timeliness study and a 448-sample physical Linux precision sweep after side-buffer fixes; RL-013/RL-014 now capture them, and OQ-004 is narrowed to the unimplemented automatic training/replay mechanism.
- **2026-10-06 — Automatic-signature value bounded:** combining trace precision with physical application-work savings projects only 0.2–2.5% phase reduction for realistic depth-two/four signatures, versus a 7.84% reduction for eight exact hints. This prompted an audit of whether larger cold-resume components had already been measured.
- **2026-10-06 — Existing cold-resume decomposition recovered:** instruction-only, data-only, translation, combined-pollution, ideal 128–192-line replay, and replay-cost experiments were already complete. The ledger now treats background replay versus cache-state retention as the unresolved architectural choice instead of proposing another component measurement.
- **2026-10-06 — Replay-versus-retention regimes separated:** the measured middle point needs only 1.24x serial replay throughput to hide combined I+D replay under Linux, whereas a five-cycle hardware handoff needs retained state. Two resident contexts can retain the measured 128–192-line range using 4–6 of eight ways; the remaining question is measured contention and capacity loss.
- **2026-10-06 — Retention capacity loss modeled:** two protected ways per resident are nearly free in warm scan/trie traces but add 1.13 percentage points of misses to pointer-plus-compute's shared context; three ways also harms scan/trie. Two-way, releasable retention is the safer first design point.
- **2026-10-06 — Forced-displacement retention benefit bounded:** conditional two-way retention preserves median four/seven recurring scan/trie lines, worth upper bounds of 156/273 cycles and 3.85x/1.71x cold resume-window speedups; pointer chasing remains at zero. Three ways captures no additional application benefit.
- **2026-10-06 — Existing concurrent installer result recovered:** the full-line experiments had already established four outstanding data reads, 27/33 hint issues during prior installation, an earlier reported 17-cycle install, and a 2,512-cycle endpoint. The later retained-waveform audit below corrected that install-rate interpretation before it was used for the next design step.
- **2026-10-06 — Shared-path replay feasibility bounded conditionally:** conservative physical refill-equivalents plus the measured application point require 479 lines and 99.4 MB/s before hot dispatch. A hypothetical 17-cycle concurrent installer would finish in 5,217 cycles under the conditional 41-cycle response start, but the later exact banked trace measures a 19-cycle median and supersedes that feasibility result. Physical full-line latency remains unmeasured.
- **2026-10-06 — Replay trigger deadline bounded conditionally:** the earlier 334-cycle deadline applied only to the hypothetical 17-cycle concurrent rate. The later exact banked trace makes strict whole-footprint completion 5,825 cycles, missing the 5,551-cycle window by 274 even at yield entry; the kernel-only target must begin by cycle 2,177.
- **2026-10-06 — Early target confidence bounded:** eight correct physical hints save 80/73.5 total cycles while eight stale hints cost 240/189, putting median break-even target accuracy at 75%/72%. This supports confidence-scaled replay rather than unconditional whole-history launch.
- **2026-10-06 — Exact miss recorder sized:** separate 256x64 I/D timestamp buffers cover the conservative kernel refill-equivalents with 81/112-entry margins and add two BRAM tiles, projecting the routed endpoint to 60.36% BRAM use. This is the direct path to ordered useful-before-demand evidence.
- **2026-10-06 — Exact miss recorder validated in simulation:** custom CSRs now arm, clear, stop, and synchronously read independent I/D accepted-demand histories. A clean directed run finds the intended cold code/data lines with counts 2/1 and no overflow, the disarmed context-switch smoke remains accepted, and the complete FPGA hierarchy compiles; routed fit and physical Linux capture remain pending.
- **2026-10-06 — Exact miss recorder validated physically:** nine FPGA/real-DDR samples all find the intended 2-I/1-D physical misses and reproduce a 47-cycle accepted-request interval, versus 63 in simulation. Physical CSR readout is accepted; Linux scheduler capture is now the remaining trace step.
- **2026-10-06 — Linux scheduler miss capture completed:** independent fresh-boot handoff legs contain 266 I and 13 D misses over 40,262 cycles, within 1.01% of a complete full-window run. Privileged code accounts for 98.5% of the instruction misses, shifting the first replay target from per-task whole-footprint duplication to a shared, per-set-recency-managed kernel/OpenSBI instruction slice.
- **2026-10-06 — Measured replay deadline corrected:** after accounting for four-slot transport and the eight-beat full-line response, the forward leg tolerates a response start up to 78 cycles, while the reverse first line requires one by cycle 57. The earlier 24-cycle/two-line statement incorrectly treated the 41-cycle critical load-to-use measurement as verified full-line service and omitted response beats; it is superseded by RL-030's conditional 16-cycle/one-line result at that assumption.
- **2026-10-06 — Installer endpoint separated:** the direct path is exactly 17 cycles across 40 installs, but the concurrent response-buffer path is 19 cycles median and 21 maximum. The strict aggregate model therefore needs a banked concurrent trace showing at most 18 cycles per line; four request slots alone do not prove feasibility.
- **2026-10-06 — Exact banked pipeline traced:** reconstructed committed banked RTL completes the 33-node workload in 802 cycles in the 32-bit minimal wrapper and 805 cycles in the FPGA-facing 64-bit wrapper. The latter carries eight beats per line but still installs at a 19-cycle median and 25-cycle maximum, including one repeated tag handshake under contention. Four slots take 2,241 cycles. This invalidates the historical 771-cycle/four-slot-equivalence claim and the strict 479-line replay projection; the next target is the ordered shared privileged-code prefix.
- **2026-10-06 — Four-slot collapse explained:** exact tracing finds two hints that are refused while the slot table is full but retire without acceptance. Their two serialized ordinary line fills span 1,346 cycles, explaining 93.5% of the four-slot penalty, and trigger four secondary installer drops. Four-slot capacity must be reevaluated after repairing hint replay; the independent 19-cycle installation-rate bound remains.
- **2026-10-06 — Late-busy replay fixed:** a hint can pass dispatch before another request asserts D-cache busy, then be suppressed at the memory pipe without the old D-cache-generated replay bit. Pipelining that suppression into replay restores four-slot runtime from 2,241 to 900/905 cycles in the minimal/FPGA-facing wrappers, accepts all 33 hints, and eliminates ordinary fallbacks and installer drops. Four slots are now only 12.2–12.4% slower than ten, and the matched wrapper deltas show that the residual is queue scheduling rather than beat width.
- **2026-10-06 — Corrected queue-depth knee measured:** the fixed minimal path takes 1,106/900/802/802 cycles for three/four/five/ten slots with complete 33-line/no-fallback accounting. The FPGA-facing path independently takes 905/805/805 for four/five/ten. Five is the minimum measured depth matching ten-slot runtime in both wrappers.
- **2026-10-07 — Five-slot FPGA route accepted:** the default flow narrowly exceeds XC7Z020 logic capacity, while the established area flow places at 46,349 logic LUTs and routes with zero failed nets. Signoff setup/hold slack is +0.263/+0.021 ns, and the generated package verifies exactly. Physical board performance remains the next gate.
- **2026-10-07 — Physical prefetch regression explained and fixed:** both five- and ten-slot newer routes collapse toward the 60k demand baseline because the first hit discarded the adjacent useful word from each 16-byte reply. Word-granular consumption recovers the exact narrow simulation from 80,803 to 10,715 cycles while the rotating stale-entry test still passes. A rebuilt physical matrix remains required, including the five-slot ten-stream failure gate.
- **2026-10-07 — Adjacent-word penalty measured directly:** a new same-sector probe measures the buggy five- and ten-slot physical paths across 96 sectors at 3 cycles for the first prefetched word and a 42-cycle median for the adjacent discarded word, versus 3/3 cycles for all 16 corrected simulator samples. This independently attributes a 39-cycle median per-node penalty to whole-sector consumption and provides an exact five-slot/20 MHz before image; the corrected physical comparison remains gated by the live FPGA build.
- **2026-10-07 — Context-4 boundary mechanism corrected after latency stress:** exact simple-memory simulations of the physical 120/124 NBFs and a 40-cycle/four-outstanding 124 run evict the saved stack line on the same earlier `0x80014f80` request, write all eight correct dirty words, and refill them correctly. The two demand nodes added in set 62 at iterations 121/123 correlate with the physical transition but cannot cause the eviction in any tested simulation.
- **2026-10-07 — Ordinary dirty eviction passes physically across all sets:** the naked-assembly sweep displaces all 64 dirty targets and preserves all 512 words on the FPGA, including set 62. This rejects a general routed L1-to-DDR writeback defect.
- **2026-10-07 — Physical corruption follows D-cache set 62:** the recovery reporter reads four zeros from the original stack line. Same-line/different-sector and same-set/different-tag placements fail at PC zero, while the adjacent set-61 placement passes twice. Its original set-62 `nodes` local remains zero, so moving only the return-critical words permits completion while the old line is still erased. The defect requires the ten-stream schedule and follows the set rather than address, tag, or sector.
- **2026-10-07 — Final-lap fault proven timing sensitive:** lightweight checkpoints first see the saved return address change from correct to zero around context 2's final set-7 demand, but byte-identical matched controls at entry, post-pointer, post-payload, and post-publication all retain the correct value and pass. Their only NBF difference is one stage data word. One stack recency update and modest common-loop spacing therefore suppress the fault; the exact corrupting instruction remains unmeasured. Software interleaving with the same ten streams and hints passes twice, hardware switching without successor hints passes, and one detached hint against eight dirty victims passes. The remaining target is a schedule-sensitive cross-request or response/context-transition race, not ordinary same-set replacement.
- **2026-10-07 — Exact one-bubble control built:** recompilation was rejected as the primary causal control after linker relaxation changed unrelated code. A single-record patch now replaces the exact failing hot-loop jump with `c.nop; c.j`, preserves all addresses and data, and adds 1,192 simulator cycles (1.34%). Physical A/B remains pending.
