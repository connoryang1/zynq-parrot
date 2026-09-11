# Coroutine-style L1 prefetch design

The fast-switch benchmark requires a prefetch to survive a context switch as an
independent L1 fill. The current RTL now provides that path through a ten-entry
UCE queue and a detached full-line L1 fill route.

## Required transaction contract

An accepted hint reserves one L1 miss entry and returns to the pipeline without an
architectural completion. The entry contains the physical line address, selected
way and set, logical context ID, fill-beat mask, and a demand-waiter bit. The
memory request carries the entry ID. A response may arrive after any other entry;
the ID selects the destination and releases the entry after the final beat.

A demand for a line with an active hint joins that entry. A demand for another
line can allocate another entry while the first request is in memory. Duplicate
hints coalesce, and hints are dropped when no entry is available. Demand misses
retain priority over hint allocation and issue.

## RTL stages

1. The dcache emits an explicit prefetch transaction and carries its replacement
   way in the request ID.
2. UCE maintains ten detached entries, tracks each fill beat, matches responses
   by physical line address, and writes data/tag state without architectural
   completion.
3. The tag is published only after the complete line arrives; partial responses
   cannot make a line valid.
4. Context-switch acceptance remains independent of outstanding hint entries; only
   architectural ordering operations may drain or fence them.

The production simulator configuration uses ten entries for the ten-logical-worker,
two-resident benchmark. The focused UCE regression covers accepted hints, full-line
fills, reordered replies, demand routing, backpressure, and dropped hints.

## Completion evidence

The focused RTL path is verified. The end-to-end simulator also passes the
nonresident prefetch benchmark; the latest rows are demand `0x56e22`,
prefetch/yield/load `0x56dad`, and batched ideal `0x2ca`. The prefetch row is
117 cycles faster than demand, while switch/restore overhead remains the dominant
cost and keeps the result far from the batched ideal.
