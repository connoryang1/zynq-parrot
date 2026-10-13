This directory records the corrected pending target-dispatch interlock and its simulation evidence. It explains why the first routed implementation was ineffective and pins the correctness, waveform, and exact performance controls used before rebuilding the FPGA image.

# Pending first-target interlock

BlackParrot commit `30479f1a2` keeps the interlock pending across the empty frontend redirect gap. It clears only on the cycle when a target queue head exists and all ordinary issue conditions are ready, so that head is held for exactly one occupied cycle and dispatches on the next cycle.

All maintained tests reached their specific guest marker, `CORE PASS`, and host `BSG PASS`; the known post-PASS DPI finalization assertion remains outside guest behavior. The nonresident handoff trace consumed one issue-ready interlock cycle for each of two switches. The ten-stream trace consumed one for all 1,340 switches and increased the timed region from 23,972 to 25,264 cycles, exactly one cycle for each of its 1,292 timed handoffs.

The byte-identical archived two-stream NBF increased from 19,258 to 20,547 simulator cycles: 1,289 cycles or 6.69%. It retains a 2.924x speedup over the 60,077-cycle demand baseline. This cost is close to the explicit software-bubble control, as expected now that the hardware interlock actually reaches the first target instruction.

The replacement route at top `9990e673` / BlackParrot `30479f1a2` meets timing at WNS/WHS `+0.150/+0.035 ns`. On its exact bitstream, the formerly failing original k10 image passes twice at 72,038 and 72,042 cycles after separate fresh overlays. The byte-identical k2 control passes at 20,547 physical cycles, exactly matching the corrected simulation. This is the accepted FPGA repair; full identities and transcripts are in `physical-board-r1/`.

One discarded lower-level invocation omitted the prefetch-depth model identity and began rebuilding the wrong configuration. It was stopped before running; the maintained test target rebuilt the correct `nt2/nc10/pfels10` model, and `results.json` records only accepted runs.
