# Context D-Cache Service Experiments

## Baseline

The nonresident GPR image path is intentionally serialized through
`bp_be_pipe_mem.sv`:

1. `bp_be_top.sv` reads one victim register.
2. It issues one physical, cacheable 64-bit D-cache request.
3. It waits for the store completion or load response.
4. It advances the save/restore mask.

The representative minimal `0 <-> 2` benchmark measured approximately 204
global cycles per nonresident switch. Its GPR service state alternated between
about 195 cycles for `31 saves + 3 loads` and 139 cycles for `3 saves + 31
loads`.

The trusted baseline passes both:

- `mt_ctxtsw_nonresident_overhead_benchmark`
- `mt_ctxtsw_nonresident_gpr_overhead_benchmark`

The latter was clean-rebuilt with `TRACE=1` after the failed experiment below
and reached `CORE PASS` / `BSG PASS`.

## Reverted Store-Streaming Experiment

Date: 2026-07-19

Experiment: allow context-image stores to enter the ordinary D-cache pipeline
without waiting for an individual completion, then wait on `dcache.ordered_o`
before target restore.

Observed performance before revert:

- nonresident control-loop interval: about 165-170 global cycles/switch
- save-heavy GPR phase: 195 -> 136 cycles
- load-heavy GPR phase: approximately 139 -> 136 cycles

Correctness result:

- minimal overhead benchmark: pass
- focused nonresident GPR stress benchmark: `CORE FAIL`

The RTL was not committed and was reverted immediately. Do not resurrect that
change by merely reintroducing a store fence. It relaxed a single-request
completion contract without preserving request identity through the D-cache
pipeline.

## Verified D-Cache Contract

`bp_be_dcache.sv` is a normal pipelined 64-bit D-cache:

- request: `dcache_pkt_i` / `v_i`
- TL stage: physical tag and store data on the following cycle
- TV stage: hit data or miss result
- `busy_o`: blocks new requests once the cache enters a non-ready state
- `ordered_o`: indicates its pipelines and cache-engine credits are drained

The cache propagates `rd_addr` and `thread_id` through its TL/TV stages.
`bp_be_pipe_mem.sv` currently forces the context-service packet fields to zero
and exposes no context request ID on response. Its internal cache data-memory
ports are not a physical-address line-copy API: they require resolved cache
set/way/coherence state, so they must not be used directly by this feature.

## Required Next Design

Implement a bounded context-service adapter, not an untracked store stream.

1. Extend the context-service interface with a request ID (the target GPR
   number is sufficient for V1) and return that ID with each load response.
2. Keep a small FIFO/scoreboard for accepted context requests. It must track
   operation type, GPR number, data-valid state, and outstanding count.
3. Permit at most the verified D-cache pipeline window of context requests;
   begin with two entries, not an unbounded stream.
4. Block new issue whenever D-cache `busy_o` asserts. Do not infer that a
   request completed from acceptance.
5. Complete stores only after the final `ordered_o` fence. Complete loads only
   when their tagged response arrives and is written into the target regfile.
6. Keep normal instruction memory requests excluded while context service owns
   the D-cache; the context FSM already drains BE state before entering this
   phase.

## Verification Gates

For each implementation checkpoint:

1. `git diff --check`
2. `make -j24 prep_lite`
3. clean `TRACE=1` minimal nonresident benchmark with global-cycle markers
4. clean `TRACE=1` nonresident GPR stress benchmark
5. inspect waveform request ID, acceptance, D-cache busy, tagged load response,
   outstanding count, and final ordered fence

Commit only after both correctness tests pass. Measure performance from global
testbench markers; `rdcycle` is virtualized and is not elapsed time across a
nonresident restore.
