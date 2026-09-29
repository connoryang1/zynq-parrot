# Clock-frequency refactor analysis

This analysis uses the exact board-qualified 18 MHz image at top commit
`f912a8a25e14e69d41871df899bcb302ae5578f1` and BlackParrot commit
`81601d1c8c41505d25a50f6b2a4752d435c5abce`.  The routed image has
WNS `+1.007 ns`, 49,819/53,200 LUTs (93.64%), 28,475/106,400 registers
(26.76%), and 13,299/13,300 occupied slices (99.99%).  Its 1,562 unique
control sets and almost completely occupied fabric make routing, rather than
flip-flop capacity, the dominant physical constraint.

## Realistic frequency ranges

| Change class | Realistic target | Increase from 18 MHz | Assessment |
|---|---:|---:|---|
| Placement, synthesis, and local logic cleanup | 20 MHz | 11% | High confidence.  The prior 20 MHz route missed by only 0.682 ns. |
| Aggressive area refactor without a pipeline change | 21-23 MHz | 17-28% | Plausible if 6-10k LUTs are removed and control-set pressure falls.  Sixty-level paths remain the limit. |
| Area refactor plus three targeted pipeline cuts | 25-30 MHz | 39-67% | Realistic architectural target.  This requires breaking both long full-cycle control paths and fixing the half-cycle D-cache path. |
| Deeper pipeline redesign | 35 MHz | 94% | A stretch target with visible load/switch latency changes and several route iterations. |
| 40 MHz or more | 122%+ | Not a planning estimate for the current microarchitecture/device.  It likely needs broader pipeline and memory-system restructuring. |

The first implementation target should be 25 MHz, followed by a 30 MHz
route once the new timing report identifies the next paths.  Frequency does
not scale directly with area: the present worst path is 53.667 ns, so 25 MHz
requires it below 40 ns and 30 MHz requires it below 33.333 ns.

## Where the LUTs are

The numbers below are inclusive hierarchy totals, so child rows must not be
added to their parents.

| Block | LUTs | Share of design | Observation |
|---|---:|---:|---|
| Backend | 33,900 | 68.1% | Primary area target |
| Calculator, inside backend | 30,052 | 60.3% | Contains the four largest backend opportunities below |
| System/CSR pipe | 8,853 | 17.8% | Two CSR engines plus context-switch control |
| Reservation/operand conversion | 8,016 | 16.1% | Stores raw operands, performs integer unboxing, and performs three FP unboxes |
| Memory pipe | 6,234 | 12.5% | Includes the 5,368-LUT D-cache |
| L2 cache slice | 3,849 | 7.7% | Useful to the memory experiment; shrinking it would change memory behavior |
| Frontend | 3,739 | 7.5% | Includes 1,930-LUT I-cache |
| Scheduler | 2,769 | 5.6% | Includes 1,502-LUT issue queue |
| Long divide/FP pipe | 2,652 | 5.3% | ISA-dependent |
| Forward and reverse memory crossbars | 2,444 | 4.9% | Candidate for a fixed one-core/one-slice topology |
| FMA pipe | 1,553 | 3.1% | Also uses all 11 DSPs |
| D-cache and I-cache UCEs | 2,619 | 5.3% | Fixed-width specialization may help, but these are not the largest blocks |
| Context memory | 628 | 1.3% | Uses 16 BRAM36s; capacity is not a large LUT consumer |
| Dedicated prefetch AXI master | 105 | 0.2% | The detached prefetch transport is not a useful area target |

The system/CSR total is unusually actionable.  It contains two complete CSR
instances of 3,049 and 2,882 LUTs plus an 886-LUT wrapper.  Only one resident
thread executes at a time, so a banked CSR state array around one shared
decode/update datapath should save roughly 2-3.5k LUTs while preserving two
resident architectural states.

The 8,016-LUT reservation block is the other large refactor target.  It
currently derives integer and three recoded floating-point operands in
parallel.  Keeping raw 64-bit operands through the reservation stage and
performing only the conversion selected by the destination pipe should avoid
large duplicated conversion/mux cones.  A synthesis experiment is needed for
an exact number, but 2-4k LUTs is a reasonable target while retaining the ISA.
An integer-only endpoint has a larger potential saving: the explicit FMA and
FP register-file rows alone account for 1,880 LUTs, before removing FP
unboxing, FP divide, CSR flags, and muxing.  A total 3-6k LUT reduction is
plausible, at the cost of losing the F/D extensions.

A fixed-topology replacement for the 1,047-LUT forward and 1,397-LUT reverse
memory crossbars could plausibly recover another 1-2k LUTs.  These estimates
overlap, especially the reservation and integer-only estimates; a combined
6-10k LUT reduction is a defensible goal, not their arithmetic sum.

## What must be pipelined

The fifty worst setup endpoints collapse into three path families:

1. **Frontend/I-cache to I-cache UCE request FIFO:** 53.667 ns, 60 logic
   levels, with 42.319 ns (78.9%) in routing.  The path propagates I-cache and
   realigner state through frontend redirect/context control and TLB selection
   into the UCE FIFO write enable.  A small elastic request boundary with
   registered validity/credit should break the combinational ready path.  It
   can be placed on the miss/request path, so the likely architectural cost is
   one cycle when launching a cache request rather than one cycle on every
   instruction hit.

2. **Exception/CSR/context control to integer register-file BRAM enable:**
   53.749 ns, 53 logic levels, with 43.000 ns (80.0%) in routing.  It crosses
   the duplicated CSR/context logic, exception state, issue queue, and context
   register-bank selection.  Registering the committed context action before
   scheduler/register-file control should cost about one context-switch cycle.
   Sharing the CSR datapath also shortens and localizes this path.

3. **Negative-edge D-cache result to positive-edge calculator state:**
   26.088 ns against a 27.781 ns half-cycle requirement, with 30 logic levels.
   At 25 MHz the half-cycle budget is only 20 ns; at 30 MHz it is 16.667 ns.
   Area cleanup cannot make this safe by itself.  Moving the D-cache/result
   boundary to a full-cycle path or adding a result stage is required.  The
   straightforward version adds about one cycle to load-use latency; a more
   careful retime may preserve some hit behavior but is higher risk.

Breaking only the first path does not raise the clock appreciably because the
second path is 0.082 ns slower in raw data delay, and the half-cycle path then
limits higher targets.  All three should be treated as one frequency project.

## Expected performance trade

The pipeline changes probably add one cycle to cache-request launch, one cycle
to a context switch, and potentially one cycle to load-use.  Those costs are
small compared with a 39-67% frequency increase for the pointer-chasing
workload.  For example, even an extra cycle per one of the 1,278 nodes would
raise the current three-stream hardware result from 21,825 to about 23,103
cycles.  At 25 MHz that is about 0.924 ms, versus 1.213 ms for 21,825 cycles at
18 MHz; at 30 MHz it is about 0.770 ms.

The architectural changes still require full regressions because the first
two paths participate in redirect and context-switch correctness, while the
third changes the load pipeline.  The recommended order is to synthesize
area-only variants first, implement the frontend elastic boundary, register
context-switch scheduler control, then retime the D-cache half-cycle path and
route at 25 MHz before attempting 30 MHz.

## Evidence

- `logs/prefetch-mlatency-20260926/clock-analysis-hier-util-deep.rpt`
  (`SHA-256 347c9f41228f2e688326ec4e34c132481eb6e0efb44705b914b4170a72fe8013`)
- `logs/prefetch-mlatency-20260926/clock-analysis-top50.rpt`
  (`SHA-256 d5b064ea96ce364a610130270d086196bf143a7aa2f29ad455c7603f1e2dfd96`)
- Routed implementation report under
  `/tmp/zynq-parrot-fpga-20260926T105308Z-f912a8a2/`

