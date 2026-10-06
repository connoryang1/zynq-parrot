# Measured Linux trace replay-capacity bound

This model combines the complete physical Linux handoff counts in RL-029 with
the accepted 41-cycle cold-memory service input and 17-cycle full-line
installer bound used by RL-021/RL-022. It asks whether an ideal replay engine
has enough aggregate capacity and how much time exists before the first
observed demand. It is a lower bound, not a replay speedup measurement.

Run `python3 model.py` to regenerate `results.json`.

## Result

The source-to-peer window has 48 unique instruction lines and three unique data
lines. With four shared transport slots and separate I/D installers, the
aggregate lower bound is 857 cycles, far below the 11,379-cycle window. The
first instruction miss appears at cycle 1,006. An ideal ordered replay can
finish all 48 instruction lines by cycle 857, leaving 149 cycles before that
first demand. Three slots already reach the same installer-bound result; one
or two slots take 2,091 and 1,066 cycles.

The peer-to-source window has 215 unique instruction lines and ten unique data
lines. Its four-slot lower bound is 3,696 cycles, also far below the
28,883-cycle window, and three slots are already installer-bound. Aggregate
throughput is therefore not the main problem for this measured footprint.
Timing the beginning is: the first instruction demand occurs at cycle 82. A
41-cycle response plus one 17-cycle installation can finish the first ordered
line at cycle 58, leaving only 24 cycles. At most two instruction lines can be
installed by cycle 82. The later 215-line bulk can fit, but it cannot all be
present when the reverse leg begins.

This asymmetry sharpens the architecture choice:

- Shared kernel/OpenSBI replay can cover the source-to-peer leg if launched at
  the measured pre-wake marker.
- The reverse leg needs the earliest lines retained, launched before peer
  entry, or predicted in exact order. Triggering a whole replay at peer entry
  is too late for all but roughly the first two instruction lines.
- Three slots suffice for these exact unique-line counts under the optimistic
  model. RL-022's four-slot recommendation still applies to the larger
  479-line kernel-plus-application target and provides margin for arbitration.
- Per-set recency still matters: RL-029 observed nine or ten unique lines in
  individual eight-way instruction-cache sets. Bulk capacity does not prove
  that replayed lines survive until demand.

## Limits

The model assumes perfect address knowledge, ideal request ordering, a
work-conserving memory system, no dirty victims, no ordinary-demand
interference, and independent serial I/D installers. The 41-cycle value is a
processor-to-memory-path service input, not isolated DRAM-chip latency. The
trace records request acceptance rather than response completion. Without the
full ordered record list locally, this model cannot count each line as early,
late, or useful; that remains the decisive replay experiment.
