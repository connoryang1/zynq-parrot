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
- **Limits:** concurrent replay throughput, cache installation contention, retention pollution, and useful-before-demand behavior remain unmeasured. The 160-line retention point is not a uniform integer-way partition.

### RL-019 — Two-way resident retention is the safer capacity point

- **Status:** trace-driven cache-policy model
- **Scope:** warm data traces in a 64-set/eight-way LRU model with contexts 1 and 2 protected and context 0 sharing the remainder
- **Claim:** reserving two ways per resident leaves four shared ways and adds zero scan misses and three trie misses in the repeated warm traces. Three ways leaves only two shared and adds 340 scan plus 74 trie misses. In pointer-plus-compute, one/two protected ways raise context-0 misses from 907 to 1,127/1,163, an absolute miss-rate increase of 0.97/1.13 points; two-way protection adds an estimated 9,984 cold-increment cycles across 22,666 accesses.
- **Evidence:** `logs/cache-retention-trace-model-20261006/README.md` and reproducible `model.py`/`results.json`.
- **Meaning:** two ways (128 lines/context) are the lower-risk retention prototype. Static protection still taxes an unprotected cache-sensitive workload, so inactive or low-confidence ownership should be releasable.
- **Limits:** the workers are already warm and see no misses, so these traces measure capacity cost rather than retention benefit. The model omits instruction accesses, dirty state, and exact BlackParrot replacement behavior.

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

- **Known:** RL-018 shows that replay fits the Linux regime with only 1.0–1.5x serial throughput, while two-context retention fits in 4–6 ways and is the only option that can make a five-cycle handoff immediately hot.
- **Missing:** achieved concurrent replay/install rate and interference, plus retention benefit under forced displacement. RL-019 now bounds warm-trace capacity loss and rejects three static ways as the first prototype.
- **Decisive experiment:** simulate 160-line combined background replay with scheduler traffic, then compare it against two-way retention under a forced-displacement trace. Measure useful-before-demand fraction, install stalls, shared-context misses, and total cycles.

## Next experiment

The immediate next experiment is OQ-001 because the diagnostic is complete and a physical capture can resolve a current correctness uncertainty. It requires a confirmed recovery cycle and exact overlay reload; no simulator result substitutes for the board observation. For the cache-resume architecture, do not repeat footprint, component, oracle-replay, or first-order replay/retention modeling: RL-013 through RL-018 cover them. The next new measurement is OQ-005's targeted simulation of achieved replay/install overlap versus retention capacity loss; OQ-004's small automatic signature is a complementary low-cost path rather than the main speedup mechanism.

## Delta log

- **2026-10-06 — Ledger created after a demonstrated synthesis regression:** a later summary incorrectly promoted the intermediate 418/396 result over the accepted 398/396 result. The ledger now distinguishes baseline expectations, final synthetic evidence, physical-DDR evidence, sustained Linux/FPGA results, and superseded interpretations.
- **2026-10-06 — Resume-footprint omission corrected:** the initial ledger incorrectly listed bounded-history modeling as future work. The repository already contains the completed predictor-depth/timeliness study and a 448-sample physical Linux precision sweep after side-buffer fixes; RL-013/RL-014 now capture them, and OQ-004 is narrowed to the unimplemented automatic training/replay mechanism.
- **2026-10-06 — Automatic-signature value bounded:** combining trace precision with physical application-work savings projects only 0.2–2.5% phase reduction for realistic depth-two/four signatures, versus a 7.84% reduction for eight exact hints. This prompted an audit of whether larger cold-resume components had already been measured.
- **2026-10-06 — Existing cold-resume decomposition recovered:** instruction-only, data-only, translation, combined-pollution, ideal 128–192-line replay, and replay-cost experiments were already complete. The ledger now treats background replay versus cache-state retention as the unresolved architectural choice instead of proposing another component measurement.
- **2026-10-06 — Replay-versus-retention regimes separated:** the measured middle point needs only 1.24x serial replay throughput to hide combined I+D replay under Linux, whereas a five-cycle hardware handoff needs retained state. Two resident contexts can retain the measured 128–192-line range using 4–6 of eight ways; the remaining question is measured contention and capacity loss.
- **2026-10-06 — Retention capacity loss modeled:** two protected ways per resident are nearly free in warm scan/trie traces but add 1.13 percentage points of misses to pointer-plus-compute's shared context; three ways also harms scan/trie. Two-way, releasable retention is the safer first design point.
