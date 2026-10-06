This analysis combines the accepted resume-footprint trace model with the accepted physical Linux correct-hint sweep. It estimates the benefit available to an automatic previous-resume signature after excluding software hint-issue and Linux scheduler time. The output is a cross-experiment projection, not a measured automatic predictor.

# Automatic resume-signature projection

## Result

The physical translation-primed application phase takes a direction-average 3,254.5 cycles. Eight exact correct hints reduce it to 2,999.25 cycles, saving 255.25 cycles: a 7.84% reduction or 1.085x application-phase speedup.

The trace-derived previous-first predictor does not normally produce eight correct early predictions. Scaling the measured exact-depth application savings by ordered prediction precision gives:

| Trace | Depth | Ready-only floor | Full-hit-value cap | Phase reduction range |
|---|---:|---:|---:|---:|
| Sequential scan | 2 | 10.04 cycles | 45.52 cycles | 0.31%–1.40% |
| Sequential scan | 4 | 33.37 cycles | 81.32 cycles | 1.03%–2.50% |
| Trie/irregular stream | 2 | 6.41 cycles | 22.78 cycles | 0.20%–0.70% |
| Trie/irregular stream | 4 | 14.35 cycles | 46.05 cycles | 0.44%–1.42% |
| Pointer plus compute | 2 or 4 | 0 | 0 | 0% |
| Ten dependent chains | 2 or 4 | 0 | 0 | 0% |

The ready-only floor credits only ordered hits that the warm-trace timing model says are fully complete after five cycles of launch lead. It is conservative because partially completed hints reduce demand latency and the first miss delays later accesses. The cap credits every ordered hit at the direction-average value measured by the corresponding exact-depth physical condition. It is not guaranteed because the physical sweep had long Linux scheduler lead and used a different dependent phase.

## Interpretation

A small automatic D-resume signature can plausibly save tens of cycles per recurring resume, with a bounded no-benefit result on dependent chains if confidence suppresses their replay. On the measured 3.2k-cycle application phase, the realistic projected gain is around zero to 2.5%, substantially below the eight-address oracle. This does not by itself support a large end-to-end speedup claim.

The result favors depth two as the lowest-risk small-signature design and depth four only after positive consumption feedback. The already completed cold-resume decomposition shows that the larger opportunity lies in kernel/application instruction and data footprints, not in measuring those components again: instruction and clean-data pollution add roughly independent 6.6k and 5.6k-cycle Linux resume penalties, while ideal 128–192-line application replay accelerates post-resume work by 6.1–6.6x. The small signature should therefore be treated as a low-cost complement to a larger retention or background-replay design.

## Method and reproduction

`analyze.py` loads `logs/context-resume-footprint-20261002/model-results.json` and `logs/linux-prefetch-precision-sweep-rotate-20261003/results.json`. For depths two and four, it multiplies the measured direction-average translation-primed work saving by ordered previous-first precision. The ready-only floor additionally multiplies by the trace model's five-cycle fully-ready fraction.

Run:

```sh
python3 logs/automatic-resume-signature-projection-20261006/analyze.py
```

The script writes `results.json`, including exact input hashes, all intermediate values, and limitations. Script SHA-256 is `4433b46c07a0e99226952151230850fb55a6213f2ac55bf1698fc982e9a4db15`; current result SHA-256 is `2cb213c45a597cd4cfb85f3c9bbb9f2d5aa81bdf8c00db1df1cd9e31e7703f08`.
