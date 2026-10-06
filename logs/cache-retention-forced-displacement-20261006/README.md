This analysis estimates the benefit side of resident cache retention under deliberate displacement. It applies the retained application epoch traces to a per-set two-way or three-way retention policy and credits matching retained lines with the measured 39-cycle cold-data increment. It is a forced-cold upper bound, not an implemented cache or cycle-accurate run.

# Forced-displacement resident retention

## Method

For every resume of contexts 1 and 2, the model remembers first-use-ordered 64-byte lines from that context's previous epoch. Policies retain at most 128 lines with two lines per set or 192 lines with three per set. The next epoch is treated as fully displaced without retention; every retained line reused anywhere in the epoch avoids at most one 39-cycle cold-data increment.

The projected cold window is the observed warm first-to-last-access span plus 39 cycles for every unique target line. This makes the calculated speedup an upper-bound-style estimate rather than a measured execution time.

## Result

| Trace | Evaluated resumes | Median retained/useful lines | Median saved cycles | Median projected forced-cold speedup | Median reduction |
|---|---:|---:|---:|---:|---:|
| Sequential scan | 616 | 4 / 4 | 156 | 3.85x | 74.1% |
| Trie/irregular stream | 280 | 10 / 7 | 273 | 1.71x | 41.5% |
| Pointer + compute | 127 | 1 / 0 | 0 | 1.00x | 0% |

The 128-line/two-way and 192-line/three-way policies produce identical benefit in these traces. Their epochs retain at most 21 scan lines and 28 trie lines, well below either global budget, and the extra per-set way captures no additional recurring line.

This separates two sizing regimes:

- Small recurring application epochs need far less than 128 retained lines; two ways already capture all modeled benefit.
- The earlier 128–192-line sizing points come from displaced Linux instruction/data state and large application working sets, not from these scan/trie epochs.

Pointer-plus-compute remains the required no-benefit control: its next line is data dependent and no prior-epoch line recurs.

## Combined decision with capacity cost

The warm capacity model found that two protected ways are nearly free for scan/trie but add 1.13 percentage points of misses to pointer-compute's unprotected context. This forced-cold model shows why protection can still be worthwhile when displacement is real: it saves a median 156–273 cycles on recurring scan/trie resumes.

Protection should therefore be conditional. Enable two-way retention for contexts with demonstrated reuse, and release or steal those ways when consumption feedback is poor or shared-cache pressure is high. Three static ways add capacity cost without benefit in these application traces.

## Reproduction and limits

Run `python3 logs/cache-retention-forced-displacement-20261006/model.py`. Script SHA-256 is `e3fb9e9b49b2b65666b3e4ee7baad61ce290afda020d2c3b719a709328958966`; result SHA-256 is `26f31f66866c54aae51e2f78990623d7d02852a6511224037f865f5cb9499b9c`.

The model covers data lines only, assumes full displacement, and credits every recurring line with a serialized 39-cycle miss. Real misses can hit below L1, overlap, or arrive after useful computation. First-use history is used rather than an oracle selector.
