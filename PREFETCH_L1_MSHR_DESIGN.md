# Coroutine-style L1 prefetch design

The fast-switch benchmark requires a prefetch to survive a context switch as an
independent L1 fill. The current RTL now provides that path through a ten-entry
UCE queue and a detached full-line L1 fill route.

## Required transaction contract

An accepted hint reserves one UCE slot and returns to the pipeline without an
architectural completion. The dcache supplies its replacement metadata on the
following cycle; the slot cannot issue until that metadata arrives. Each slot
stores the physical line address, selected way, sent state, and fill-beat count.
A response may arrive after any other slot and matches the unique reserved line.

A demand for a line with an active hint waits until that hint completes before
issuing its normal access. A demand for another line can proceed while hints are
in memory. Duplicate same-line hints and hints accepted while the table is full
are acknowledged and dropped; their following metadata beat is consumed without
polluting the ordinary metadata FIFO. Demand traffic retains issue priority.

## RTL stages

1. The dcache emits an explicit prefetch transaction followed by its normal
   replacement metadata beat.
2. UCE maintains ten detached entries, tracks each fill beat, matches responses
   by physical line address, and writes data/tag state without architectural
   completion.
3. The tag is published only after the complete line arrives; partial responses
   cannot make a line valid.
4. The minimal Zynq top routes full-line hints through a ten-ID AXI burst bridge;
   ordinary traffic retains AXI ID zero and priority at a backpressure-safe arbiter.
5. Context-switch acceptance remains independent of outstanding hint entries; only
   architectural ordering operations may drain or fence them.

The production simulator configuration uses ten entries for the ten-logical-worker,
two-resident benchmark. The focused UCE regression covers accepted hints, full-line
fills, reordered replies, demand routing, backpressure, and dropped hints.

## Completion evidence

The focused UCE regression verifies ten slots, delayed replacement metadata,
duplicate and full-queue drops, reordered replies, backpressure, demand routing,
and malformed-response rejection. The bridge regression verifies a full queue,
interleaved AXI IDs, BedRock backpressure, 32-to-64-bit data assembly, and slot
reuse.

On the final 200-cycle simulator model, demand takes 1,113,898 cycles, the
ten-worker prefetch/yield/load schedule takes 1,084,758, and the batched ideal
takes 10,383. The candidate is 2.616% shorter than demand, with two UCE hints and
three AXI reads observed outstanding. Nine of ten later loads avoid a normal
same-line miss. The remaining 104.47x candidate-to-ideal gap is dominated by the
ordinary instruction/context traffic between worker hint admissions.
