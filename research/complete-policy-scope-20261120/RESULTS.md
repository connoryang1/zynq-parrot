This report closes the fixed sixteen-boot FPGA comparison of the historical combined mode14 trigger and its early-only kernel control. It preserves the registered whole-cell comparison and the absolute execution costs; neither establishes a kernel performance improvement.

# Complete four-workload FPGA result

All eight scheduled reservations completed, with two independent fresh boots per image/workload and all sixteen logs accepted by `closed-audit.json`. Acquisition followed the fixed ABBA image waves and forward/forward/reverse/reverse workload order, using the same scoped ELF, 32KiB working sets, 64 loops, 32 warmups and four paired repeats. The two failed B1-second attempts remain declared and excluded as entire attempts; the first complete replacement filled that fixed slot. `attempt-history-review.json` checks the retained session20–27 namespace against those declarations without claiming visibility into arbitrary unrecorded paths.

The registered primary is B-minus-A paired off-on WHOLE benefit, measured in cycles per cell; the table also gives its percentage-point presentation. Positive favors removing the selection trigger. Every interval includes zero. Absolute enabled cost uses the opposite favorable sign: negative favors B.

| Workload | Primary benefit change, cycles/cell [95% interval] | Benefit change, pp [95% interval] | Enabled WHOLE cost change, cycles [95% interval] |
| --- | ---: | ---: | ---: |
| scan | +123,489.5 [-501,615, +642,686] | +0.628 [-2.438, +3.130] | -102,203.5 [-554,321.5, +226,732] |
| lookup | -494,859.5 [-852,876.5, +415,595.5] | -2.961 [-5.180, +2.607] | +73,420 [-326,667.5, +641,784.5] |
| parse | -392,726 [-1,148,519, +753,028] | -0.443 [-1.301, +0.825] | +112,911 [-549,554, +932,959] |
| chase | -341,394.5 [-557,920, +242,289] | -2.642 [-4.240, +1.862] | +69,452.5 [-163,049.5, +417,971] |

The corresponding steady-loop benefit changes are +2.136, -1.108, -0.319 and +0.046pp; all their intervals also include zero. The earlier short counter control proved fewer trigger admissions, but fewer triggers do not establish faster execution. Keep patch0028 as an experimental mechanism control for the separately registered codec comparison; do not promote it as an accepted performance improvement.

All eight raw WHOLE rows, paired order, enabled/disabled medians and sums, controller observations and OS resources are retained for every boot in `closed-analysis.json`. For a compact execution-cost check, these are the sums of the eight measured cell intervals, in cycles:

| Workload | A1 | B1 | B2 | A2 |
| --- | ---: | ---: | ---: | ---: |
| scan | 160,596,155 | 161,404,623 | 160,488,291 | 162,446,708 |
| lookup | 129,998,963 | 129,882,375 | 130,905,884 | 131,058,467 |
| parse | 704,506,917 | 706,025,703 | 706,372,270 | 705,695,465 |
| chase | 103,443,632 | 104,634,011 | 102,906,342 | 103,812,916 |

These totals do not show a consistent reduction across workloads/visits. Within-boot costs also change with repeat/order: for example, scan A1 enabled costs fall from 20,334,092 to 19,638,500, while lookup A2 paired benefits change sign. Neither selecting late repeats nor choosing the favorable arm of an order pattern is authorized. No boot, row or workload is removed by its effect.

WHOLE includes each cell's setup, allocations, fork, warmup, checked work, child reap, frees, mode reset/controller polling and resource observers. The sums exclude process startup and reporting, and are not process wall time. Resource rows show zero major faults throughout, but OS faults/switches/accounting cannot identify cache misses or assign cycle savings.

Two boots per image leave limited between-boot evidence. The hierarchical bootstrap resamples repeat blocks within boots and does not resolve serial dependence, nonlinear drift or retained-line carryover; ABBA is not randomization. Mode-zero cleanup drains reported prefix-controller bits only, and completed lines can survive into subsequent initial setup. Saturated trigger counters cannot localize removed admissions. The low-level runner helper changed after the first three visits only in post-program cleanup, with explicit installation/source evidence; the eight frozen host drivers and guest timing endpoints stayed identical.

The result rules out treating this control as an established broad improvement; it does not prove the true effect is exactly zero or identify a unique hardware bottleneck. This comparison concerns removing the extra late trigger, not whether instruction replay itself has exactly zero benefit. The separate fixed zlib cohort and demand-retention controls remain necessary. Controlled D-service sensitivity and small conditional D-victim coverage remain simulation evidence, not numerical predictions for this FPGA result.
