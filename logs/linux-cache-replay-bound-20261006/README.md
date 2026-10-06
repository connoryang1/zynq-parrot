# Measured Linux trace replay-latency thresholds

This model combines the complete physical Linux handoff counts in RL-029 with
the eight-beat 64-byte response shape and the 17-cycle data-installer bound
from RL-021/RL-022. It identifies how quickly a full-line response must begin
for replay to beat the first observed demand. Run `python3 model.py` to
regenerate `results.json`.

The physical 41-cycle cold-load result is deliberately not treated as a
measured full-line response latency. That number is processor-visible
load-to-use for a critical word. The physical narrow prefetch result is also a
16-byte side-buffer path rather than the proposed 64-byte I-cache replay path.
No accepted physical measurement currently times a detached 64-byte request
from acceptance through its final response beat and L1 installation.

## Defensible thresholds

The source-to-peer window has 48 unique instruction lines and three unique data
lines. Its first instruction demand occurs at cycle 1,006. Under ideal ordering
and separate cache installers, an installer considered alone tolerates a
182-cycle first-response delay. Four shared transport slots impose the tighter
bound: the first response must begin within 78 cycles for all 48 instruction
lines to arrive and install before cycle 1,006. If the unverified 41-cycle
value were representative of a full-line response start, completion would be
cycle 865, leaving 141 cycles. The forward path therefore has useful margin,
but much less than an installer-only calculation suggests.

The peer-to-source window is much tighter. Its first instruction demand occurs
at cycle 82, so the first response beat must arrive no later than cycle 57:
`57 + 8 + 17 = 82`. Under a conditional 41-cycle response-start assumption,
only one complete line fits by cycle 82 and it has 16 cycles of slack. At 65
cycles no replayed full line can be installed before the first demand. The
reverse path therefore needs an actual full-line timing measurement before any
claim that replay covers even its first miss.

Bulk capacity remains less sensitive. At the conditional 41-cycle point,
four shared slots and separate I/D installers bound the forward and reverse
footprints at 865 and 3,704 cycles, within their 11,379- and 28,883-cycle
windows. This does not establish usefulness because the earliest reverse
deadline is far tighter than the complete window.

The result supports a hybrid design:

- launch shared kernel/OpenSBI replay at the pre-wake marker for the forward
  leg;
- retain the earliest reverse-path lines or launch them before peer entry;
- measure request-to-final-beat and installation latency on the physical
  full-line path before using the 41-cycle demand result in replay projections;
- preserve per-set recency because RL-029 observed nine or ten unique lines in
  individual eight-way instruction-cache sets.

## Limits

This remains an optimistic capacity model. It assumes perfect addresses and
ordering, consecutive response beats, no dirty victims, no scheduler traffic,
and independent serial I/D installers. The 17-cycle value is measured for the
data installer; an equivalent instruction replay installer does not yet exist.
The Linux recorder timestamps accepted demand requests rather than completion
or saved stall cycles. Exact per-line early/late coverage still requires the
full ordered record list and a physically timed instruction replay path.
