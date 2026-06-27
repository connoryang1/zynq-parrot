# Simple L1-Backed Register Context Cache Plan

## Goal

Support more software-visible contexts than the two resident hardware slots that fit comfortably in synthesis. The fast resident-hit path should keep the current ISD-forwarding behavior. Resident misses should be correct first: stall, save the evicted resident slot to a reserved cacheable memory image, restore the requested logical context into a resident slot, then resume through the existing context-switch redirect path.

## Starting Point

- The current optimized path is ISD forwarding for resident context switches.
- The current implementation assumes the context ID maps directly to a resident hardware thread slot.
- Synthesis pressure limits practical resident slots to two in the current configuration.
- This plan is for a new phase of work after the repo is cleaned; it should not be mixed with unverified I-cache abort experiments.

## Terminology

- `logical_context_id`: software-visible context ID written to CSR `0x081`.
- `resident_slot_id`: physical hardware slot used by the frontend PC/predictor state, backend regfile bank, scheduler hazards, and writeback routing.
- `resident hit`: target logical context is already mapped to a resident slot.
- `resident miss`: target logical context is not currently resident and must be restored from memory before it can run.

## Design

### Resident Map

Add a small mapping table near the context-switch ownership logic:

- `slot_valid[2]`
- `slot_logical_id[2]`
- `logical_resident_v[num_contexts_p]`
- `logical_resident_slot[num_contexts_p]`
- `current_logical_context_id_r`

Keep existing `current_thread_id_lo` as the resident physical slot ID. The CTXT CSR target becomes a logical ID, which is translated to a resident slot only after the resident map is consulted.

### Fast Path: Resident Hit

If the target logical context is already resident:

1. Translate logical target ID to `resident_slot_id`.
2. Use the existing ISD-forwarding path.
3. Do not enter the context-cache FSM.
4. Preserve current performance counters and waveform expectations for two-context tests.

### Slow Path: Resident Miss

If the target logical context is not resident:

1. Suppress early FE sideband launch for that switch.
2. Stall issue/FE queue so no target-context instructions dispatch before restore.
3. Remember:
   - old logical context ID
   - target logical context ID
   - victim resident slot
   - target NPC / resume PC
4. Wait for `commit_pkt.ctxtsw` so the old context state is architecturally settled.
5. Save the victim slot state to reserved cacheable memory.
6. Restore target logical context state into the victim slot.
7. Update resident map.
8. Launch the normal FE redirect using the restored resident slot.

### Context-Cache FSM

First implementation should be serialized and easy to debug:

1. `idle`
2. `wait_ctxtsw_commit`
3. `wait_drain`
4. `save_regs`
5. `save_npc`
6. `restore_regs`
7. `restore_npc`
8. `install_slot`
9. `launch_fe`
10. `done`

The FSM owns the regfile scan path and D-cache access path only while normal instruction issue is stalled.

### Saved State V1

Save and restore:

- integer registers `x1-x31`
- NPC / resume PC
- minimal metadata needed to validate the context image

Do not save/restore in V1:

- `x0`
- floating-point registers
- full CSR file
- per-logical predictor state
- privilege state
- SATP/ASID state

Tests for V1 must avoid relying on the omitted state across nonresident evictions.

### Backing Store

Use a reserved cacheable memory range:

```text
context_base + logical_context_id * context_stride + field_offset
```

Suggested layout:

- `0x000`: metadata / valid word
- `0x008`: NPC
- `0x010`: `x1`
- `0x018`: `x2`
- ...
- `0x100`: end of integer register area, rounded for alignment

Start with 64-bit word accesses through the existing D-cache path. Line-wide transfers can be a later optimization.

### Regfile Access

Extend `bp_be_regfile_mt` with a debug/service scan port or tightly scoped context-service port:

- one read per cycle for save
- one write per cycle for restore
- selected by `{resident_slot_id, reg_index}`
- active only when the scheduler is stalled/drained

If this conflicts with existing CSR `rpush` or normal writeback ports, the context-cache FSM should only assert ownership while normal issue is blocked and architectural writebacks have drained.

### D-Cache Access

Mux a context-engine load/store request into the existing BE D-cache request path only while normal memory issue is stalled.

V1 constraints:

- one outstanding context-engine request at a time
- no overlap with normal load/store issue
- no attempt to optimize miss latency yet
- waveform-visible state for request, response, current reg index, and target address

## Verification Plan

### Cleanup Checkpoint

Before implementing:

- archive any unverified diffs
- revert failed experiments
- remove generated waveform/debug clutter
- verify both repos are clean except this planning document

### Build Checks

- `git diff --check`
- `git -C import/black-parrot diff --check`
- `make -j24 prep_lite`

### Resident-Hit Regression

Use existing two-context tests. These should not enter the context-cache FSM:

- `mt_ctxtsw_smoke_test`
- `mt_ctxtsw_microbench`
- controlled gap tests previously used for ISD forwarding
- register isolation/regfile tests

Run with:

```sh
make -C cosim/black-parrot-minimal-example/verilator clean run PROG=<test> TRACE=1
```

### New Resident-Miss Tests

Add focused tests:

- `mt_ctxtsw_context_cache_smoke`: three logical contexts with two resident slots.
- `mt_ctxtsw_context_cache_ring4`: four logical contexts round-robin, forcing repeated eviction and restore.
- `mt_ctxtsw_context_cache_dirty_regs`: each context writes distinct integer register values, gets evicted, then verifies restore.
- `mt_ctxtsw_context_cache_hit_miss_mix`: alternate resident hits and resident misses to verify fast path is preserved.

### Waveform Acceptance

Resident hit:

- no context-cache FSM activity
- sideband/ISD forwarding behaves like current optimized path
- no extra stalls beyond known resident-hit behavior

Resident miss:

- early FE sideband is suppressed
- no target logical context dispatches before restore completes
- `commit_pkt.ctxtsw` is observed before victim save begins
- victim registers are saved with the old resident slot ID
- target registers are restored into the selected resident slot
- resident map updates before FE redirect
- normal instruction issue remains blocked while context-cache FSM owns regfile/D-cache service ports

## Performance Reporting

Report resident-hit and resident-miss performance separately:

- resident-hit context-switch overhead
- resident-miss hot-L1 save/restore cycles
- resident-miss cold-cache behavior
- cycles spent in each FSM state

The expected V1 resident miss cost is much higher than the current resident-hit path because it serializes 31 register saves and 31 register restores with word accesses. This is acceptable for the first correctness implementation.

## Risks And Open Questions

- Whether the cleanest regfile service path is a new port or a mux around existing read/write ports.
- Whether D-cache arbitration is easiest in the BE pipe or in a small side engine near the D-cache request interface.
- Exact drain condition required before saving the victim slot.
- How to initialize backing memory for never-before-resident logical contexts.
- Whether minimal CSR/NPC state is enough for all near-term tests.
- Whether synthesis is improved enough by reducing resident slots to two after adding the context-cache FSM and maps.

## Commit Strategy

Use small commits:

1. Add parameters/types and resident map with no behavior change.
2. Add logical-to-resident translation for resident hits and verify existing tests.
3. Add context-cache FSM skeleton with counters/waveform signals but no active miss handling.
4. Add regfile scan support and unit-style resident-miss save trace.
5. Add D-cache save path.
6. Add D-cache restore path.
7. Add resident-miss end-to-end test.
8. Clean debug instrumentation and document measured costs.
