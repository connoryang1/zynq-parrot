# Coroutine-style L1 prefetch design

The fast-switch benchmark requires a prefetch to survive a context switch as an
independent L1 fill. The current `prefetch.r` path is advisory downstream traffic
and does not satisfy this contract.

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

1. Replace the single data-cache `mshr_reg` with a parameterized entry array and
   expose an entry ID on the cache-engine request metadata.
2. Add an L1-fill response arbiter that writes tag, status, and data beats for
   the selected entry while preserving ordinary demand completion signals.
3. Extend the UCE request state from one active miss to a small entry pool, with
   independent address/way metadata and response matching.
4. Extend the CCE memory request state similarly, or provide a dedicated
   read-only prefetch request channel whose responses carry the L1 entry ID.
5. Keep context-switch acceptance independent of outstanding hint entries; only
   architectural ordering operations may drain or fence them.

The first useful configuration is two entries for the two resident contexts. A
four-entry configuration should then be used for the ten-logical-worker,
two-resident benchmark. The simulator must report accepted hints, maximum
outstanding entries, completed L1 fills, demand joins, and dropped hints.

## Completion evidence

The implementation is complete only when the nonresident coroutine benchmark
shows multiple accepted entries outstanding concurrently, later loads hit or
join those L1 fills, and the demand-only, prefetch/yield/load, and batched-ideal
cycle rows are all collected from fresh boots. Functional PASS without those
trace counters is insufficient.
