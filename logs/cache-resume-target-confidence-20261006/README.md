# Early target-prediction confidence bound

RL-023 shows that whole-footprint replay must begin before ordinary Linux task selection. This analysis asks how accurate an early target prediction must be using the accepted eight-hint physical outcomes.

For a prediction that selects the correct incoming context, eight correct hints finish 80 cycles faster than cold demand toward main and 73.5 cycles faster toward worker at the observed total-cycle medians. For a wrong-context prediction, the eight-stale-hint condition is 240 and 189 cycles slower than cold. The expected median change is:

```text
expected saving = p * correct saving - (1-p) * stale penalty
```

The resulting break-even target accuracies are **75.0% toward main** and **72.0% toward worker**. A conservative median planning rule should therefore require at least 75% confidence even for an eight-line replay. At 90% accuracy, the expected median savings are only 48 and 47.25 cycles; at 99%, they are 76.8 and 70.875 cycles.

This threshold is a lower bound for a large replay. Hundreds of wrong full-line requests can consume bandwidth and evict useful state nonlinearly. The scheduler-inclusive correct-hint confidence intervals also cross zero, so 75% is not repeatable end-to-end proof. It says low-confidence early prediction is already unattractive in the smallest physically tested batch.

The design implication is confidence-scaled replay: deterministic or highly stable pairings may launch the full history at yield entry, moderate confidence should launch only the highest-value lines, and low confidence should wait for selection or rely on releasable retention. Target-context confidence and per-line confidence need separate counters.

Reproduce with:

```sh
python3 logs/cache-resume-target-confidence-20261006/analyze.py
```
