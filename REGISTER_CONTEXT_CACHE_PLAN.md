# Register Context Cache Plan

## Current Implementation Status (2026-07-25)

The original L1/Dcache-backed GPR service has been replaced on branch
`ctxtsw-context-sram` by a dedicated private context-memory interface:

- `bp_be_context_mem.sv` stores logical-context GPR images independently of the
  normal Dcache.
- Nonresident saves write the context memory directly; restores request four
  wide register lines into a local buffer before writing the physical regfile.
- Restore uses both existing physical-regfile write ports, so it installs two
  GPRs per cycle. Save now uses both physical-regfile read lanes and two
  context-memory write lanes.
- FP and CSR nonresident state remain on their existing paths and are not part
  of this GPR-specific performance result.

The dedicated-memory restore is verified by clean `TRACE=1` runs of
`mt_ctxtsw_nonresident_gpr_overhead_benchmark` and
`mt_ctxtsw_nonresident_ring_test`.

## Context-Switch Timing Record

Use global simulator cycles for nonresident timing. `rdcycle` is virtualized
per logical context and is not a wall-clock timer while a context is evicted.

| Configuration | Result | Evidence / interpretation |
| --- | ---: | --- |
| Original resident-only Banyan path | 7 cycles/switch | Original minimal resident warm path; not a nonresident result. |
| Current ISD-forwarded resident path | about 4 cycles added overhead | Best-case warm/steady result: redirect begins when ctxtsw reaches ISD, before architectural commit. |
| Original serialized Dcache GPR service | 203.64 global cycles/switch | `52131 / 256` in the 2026-07-18 global-marker run. Each switch serialized 34 64-bit Dcache requests/responses. |
| Dedicated context memory, one GPR restore port | Absolute cold cost not yet re-baselined | Functional checkpoint. It removes the normal-Dcache transaction dependency and restores from a four-line local buffer. |
| Dedicated context memory, two GPR restore ports | 15 global cycles saved per cold switch vs. one-port dedicated restore | Two otherwise-identical traced runs differed by 7,680 global cycles. Only the two 256-switch cold phases use this path: `7680 / 512 = 15`. |
| Dedicated context memory, two GPR save and restore ports | 191.41 global cycles/cold switch | Direct clean `TRACE=1` measurement: marker `0xc1` at cycle `454679`, marker `0xc2` at `503681`; `(503681 - 454679) / 256 = 191.41`. This phase contains only the measured 256 cold switches. |

The historical serialized-Dcache measurement is not a same-build baseline for this
marker interval, so `203.64 - 191.41` is not a validated optimization saving. The
prior controlled deltas still attribute 15 cycles to the second restore lane and
11.50 cycles to the second save lane across their respective builds. Add equivalent
warm markers and measure save/restore state-machine residency before assigning the
current cold cost to individual states or comparing it to the old Dcache path.

The benchmark writes host signal markers `0xc1` and `0xc2` immediately before and
after `t0_cold_bench()`. Under Verilator, `bsg_host` records the simulator timekeeper
cycle when each marker packet reaches the host. This is a host-observed whole-loop
interval, not a virtualized `rdcycle` value.

## Storage Clarification

The older RTL shadow image and the current `bp_be_context_mem` are *not* the
physical ISA register file. The physical active-thread GPR banks are implemented
by `bp_be_regfile_mt.sv` and are indexed by `{physical_thread_id, register}`.
Arrays such as `context_cache_int_shadow_r` and the `mem` array inside
`bp_be_context_mem` describe separate hardware storage for nonresident logical
contexts.

In RTL simulation, a `logic` array behaves like stored values. In synthesis it
may infer flops or a memory macro depending on the coding style, reset behavior,
and target technology. It does not silently reuse the processor's physical GPR
cells. The problem with the original design was primarily the serialized
64-bit Dcache save/restore protocol, not that the shadow array itself was a
physical regfile. The current private-memory module is an interface intended to
map to dedicated SRAM/BRAM later; its behavioral array is still a model, not a
PPA claim.

## Goal

Support more software-visible contexts than the number of physically resident hardware slots. The fast resident-hit path must preserve the current ISD-forwarding behavior. Resident misses are correctness-first: stall, save the evicted resident slot to a reserved cacheable memory image, restore the requested logical context into a resident slot, then resume through the existing context-switch redirect path.

## Current Branch Scope

The current `ctxtsw-regfile-caching` branch implements a restore-capable prototype:

- resident-hit ctxtsw remains on the existing fast path
- nonresident GPR state is saved to and restored from the reserved cacheable L1-backed image
- nonresident FP state is saved to and restored from an RTL shadow image, with two regfile
  scan lanes; it is not yet L1-backed
- logical NPC / privilege / translation-enable / ASID metadata is virtualized
- virtual CSR state is saved/restored on a resident miss

`mt_ctxtsw_nonresident_fp_ring_test` and `mt_ctxtsw_nonresident_fp_target_test` pass on
this branch. The implementation has not yet been validated for every CSR architectural corner
case, and restoring virtual `mcycle` means `rdcycle` is not a wall-clock performance metric
across a nonresident switch.

## Measured Nonresident Cost (2026-07-18)

The minimal nonresident benchmark was measured with global testbench cycle markers, rather
than `rdcycle`:

- resident `0 <-> 1`: `1053 / 256 = 4.11` global cycles per switch
- nonresident `0 <-> 2`: `52131 / 256 = 203.64` global cycles per switch

The apparent old `rdcycle` result of `3.55` cold cycles/switch is invalid. A nonresident
launch restores virtual CSR state, including `mcycle`, so each logical context excludes time
while the other context owns the resident slot.

Debug state accounting in the timed cold region establishes the steady-state alternating
directions:

| Direction | GPR dirty state at save/restore entry | GPR FSM cycles | FP FSM cycles | Approx. launch-to-launch cost |
| --- | --- | ---: | ---: | ---: |
| `0 -> 2` | save 31, target has 3 | 195 | 32 | 239 |
| `2 -> 0` | save 3, target has 31 | 139 | 17 | 170 |

Each direction has exactly 34 GPR L1 requests and responses: 31+3. The GPR path is serialized
because `bp_be_top.sv` allows one context-cache GPR request at a time, and
`bp_be_pipe_mem.sv` holds `context_cache_dcache_active_r` until that load/store responds.
The FP path does not issue these D-cache requests; it uses the direct two-lane regfile scan path.

This makes the first performance conclusion unambiguous: dirty-mask tuning cannot remove the
dominant cost for a context that genuinely owns a broad register image. A material improvement
requires a bounded multiword/line context-copy service or a distinct context-store interface.
Do not attempt to increase GPR scan picks alone: the D-cache service interface still permits only
one active 64-bit request.

## Starting Point

- The current optimized path is ISD forwarding for resident context switches.
- The current implementation has a resident map for already-resident logical contexts. Resident misses are detected and stopped in simulation; save/restore is not implemented yet.
- The intended experiment is to evaluate two resident slots with more logical contexts. The actual area/fmax benefit is unverified; `BANYAN_PARITY.md` marks current synthesis/PPA comparison as future work.
- This plan is for a new phase of work after the repo is cleaned. Keep it separate from unverified I-cache abort experiments.

## Verified RTL Facts

These are grounded in the current code and constrain the implementation:

- `thread_id_width_p` is derived from `num_threads_p`, while `context_id_width_p` is derived from `num_contexts_p` in `bp_common_aviary_defines.svh`.
- ISD CTXT decode now preserves the target as `context_id_width_p` through the dispatch/reservation path. `bp_be_top.sv` translates logical context IDs to physical resident slots and stops nonresident targets in simulation until the save/restore FSM exists.
- Existing context resume metadata is physically indexed by `thread_id` in `bp_be_top.sv`: NPC, privilege mode, translation enable, and ASID.
- Full CSR state is physically resident too: `bp_be_csr_wrapper_mt.sv` instantiates one `bp_be_csr` per `num_threads_p` and muxes outputs by `current_thread_id_i`.
- `commit_pkt.ctxtsw` is the architectural commit indication for a context switch. It is generated by `bp_be_csr.sv` as `retire_pkt_cast_i.instret & retire_ctxtsw_v_i`.
- The integer and floating-point regfiles are physically indexed by `{thread_id, reg_addr}` in `bp_be_regfile_mt.sv` and have one write port. Restore must not collide with normal writeback or CSR `rpush`.
- The detector scoreboards are already thread-tagged by physical resident slot. That is correct for resident slots, but it does not by itself prove a victim slot is safe to evict.
- Normal D-cache requests are formed inside `bp_be_calculator/bp_be_pipe_mem.sv` from a pipeline reservation and then passed to `bp_be_dcache.sv`. `bp_be_top.sv` only exposes the lower cache-engine interface, so a context-cache memory engine is not a trivial top-level request mux.
- Normal memory operations enter the D-cache through the DMMU in `bp_be_calculator/bp_be_pipe_mem.sv`. A context-service path that wants physical backing addresses must either disable translation for its generated request or bypass/supply translation explicitly.
- Existing software can remotely write another resident slot through CSR `0x083`, but no remote-read or `rpull` path exists in the current RTL/tests.

Concrete code references:

- `bp_common_aviary_defines.svh:53-56`: `num_threads_p`, `thread_id_width_p`, `num_contexts_p`, and `context_id_width_p`.
- `bp_be_defines.svh:68-73`: dispatch packets carry physical `thread_id` and logical CTXT target as `context_id_width_p`.
- `bp_be_defines.svh:90-92`: reservation packets carry physical `thread_id` and logical CTXT target as `context_id_width_p`.
- `bp_be_defines.svh:267-274`: packet width macros account for both physical `thread_id_width_p` and logical `context_id_width_p`.
- `bp_common_core_if.svh:57-67`: FE context-switch command operand is explicitly a target hardware thread ID.
- `bp_fe_controller.sv:157-164`: FE redirects to `ctxtsw_thread_id_i` and writes that physical ID into branch metadata.
- `bp_fe_pc_gen.sv:86-91`: FE PC/predictor selection register is physical `thread_id_r`.
- `bp_fe_pc_gen.sv:180-206` and `240-269`: BTB/BHT arrays are selected by physical `thread_id_r`.
- `bp_be_csr.sv:251`: CTXT CSR writes are excluded from normal CSR writes through `~retire_ctxtsw_v_i`.
- `bp_be_csr.sv:326-334`: privilege and translation enable are sequential CSR state.
- `bp_be_csr.sv:467-490`: SATP and many privilege CSRs are normal CSR state.
- `bp_be_csr.sv:730-735`: memory translation info comes from CSR state, including SATP base PPN and ASID.
- `bp_be_csr.sv:756-771`: bootstrap CSRs `0x082` and `0x083` also encode target IDs with `thread_id_width_p`.
- `bp_be_csr_wrapper_mt.sv:108-119`: one CSR instance is generated per resident hardware thread.
- `bp_be_csr_wrapper_mt.sv:165-179`: CSR outputs and bootstrap side effects are selected from `current_thread_id_i`.
- `bp_be_calculator/bp_be_pipe_mem.sv:222-259`: normal D-cache packets are constructed from pipeline reservations inside the memory pipe.
- `bp_be_calculator/bp_be_pipe_mem.sv:134-185`: normal D-cache requests use DMMU lookup and `trans_info_cast_i.translation_en`.
- `bp_be_dcache.sv:837-838`: D-cache busy/ordered are internal state derived from cache pipeline/credits.
- `bp_be_dcache_decoder.sv`: `e_dcache_op_ld`/`e_dcache_op_sd` decode as doubleword load/store operations, so 64-bit context-image words match an existing D-cache operation size.
- `testing/mt_seed.h`: software seeding helpers derive `BP_TID_BITS` from `BP_NUM_THREADS`, so they also address physical slots today.

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

Keep existing `current_thread_id_lo` as the resident physical slot ID. Add a separate `context_id_width_p = BSG_SAFE_CLOG2(num_contexts_p)` and keep CTXT CSR targets at that width until the resident map translates them.

This requires updating the CTXT-specific path before truncation:

- scheduler CTXT target decode in `bp_be_scheduler.sv`
- dispatch packet CTXT target field in `bp_be_defines.svh`
- reservation packet CTXT target field in `bp_be_defines.svh`
- width macros for dispatch/reservation packets in `bp_be_defines.svh`
- calculator fast CTXT handoff fields in `bp_be_calculator_top.sv`
- pending CTXT target registers in `bp_be_top.sv`

Normal FE/BE thread ownership remains based on `resident_slot_id`.

Do not widen FE physical thread IDs. FE command and predictor state remain resident-slot based. Translate logical IDs before FE redirect.

### Fast Path: Resident Hit

If the target logical context is already resident:

1. Translate logical target ID to `resident_slot_id`.
2. Use the existing ISD-forwarding path.
3. Do not enter the context-cache FSM.
4. Preserve current performance counters and waveform expectations for two-context tests.

Verify resident-hit behavior before implementing resident misses. This catches width/plumbing regressions early.

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
5. Wait until the victim resident slot is safe to save.
6. Save the victim slot state to reserved cacheable memory.
7. Restore target logical context state into the victim slot.
8. Update resident map.
9. Launch the normal FE redirect using the restored resident slot.

The slow path must not use the current early FE sideband until restore is complete. Launching FE before restore would make the target stream use a resident slot whose regfile/context metadata still belongs to the victim.

### Context-Cache FSM

Use a serialized first implementation:

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

The exact `wait_drain` condition is a required design item, not an implementation detail. At minimum it must prove:

- no new issue from the FE queue
- no late writeback can still target the victim resident slot
- memory pipe is not busy and is ordered
- PTW/replay/resume paths are not injecting work for the victim slot
- detector dependency pipeline no longer contains live victim-slot entries that can write back later

### Saved State V1

Save and restore:

- integer registers `x1-x31`
- NPC / resume PC
- privilege mode
- translation enable
- ASID
- metadata needed to validate the context image

Do not save/restore in V1A:

- `x0`
- floating-point registers
- per-logical predictor state
- full CSR file except any fields explicitly added below

Design decision to verify before implementation:

- If V1 must pass address-space/privilege tests, it needs SATP and selected CSR state, not just ASID. Current translation information is derived from CSR state in `bp_be_csr.sv`, and full CSR state lives in per-resident-slot CSR instances.
- If V1A is only a GPR/NPC scaling prototype, tests must explicitly avoid SATP, privilege changes, FP state, and full CSR isolation across nonresident eviction.

Tests for V1A must avoid relying on the omitted state across nonresident evictions.

Practical V1 recommendation:

- V1A: GPR + NPC + existing resume metadata only. This validates logical-to-resident mapping, resident miss detection, and save/restore sequencing. Synthesis scaling remains a separate measurement.
- V1B: add SATP and the minimum CSR state required for address-space/privilege tests.

Do not claim support for Banyan-style different address spaces until V1B works.

### Backing Store

Use a reserved cacheable memory range:

```text
context_base + logical_context_id * context_stride + field_offset
```

Suggested layout:

- `0x000`: magic
- `0x008`: version
- `0x010`: logical context ID
- `0x018`: valid word
- `0x020`: NPC
- `0x028`: privilege / translation / ASID metadata
- `0x030`: SATP or reserved CSR metadata
- `0x040`: `x0`
- `0x048`: `x1`
- ...
- end of integer register area, rounded to a 512-byte stride

`testing/mt_context_image.h` defines this concrete V1A image format, and `mt_ctxtsw_context_cache_cooperative_image` verifies the stride, field offsets, and independent logical image slots without requiring transparent hardware eviction. Start with 64-bit word accesses because the existing D-cache supports doubleword load/store operations. The exact hardware service path is still a design item: a request through `bp_be_calculator/bp_be_pipe_mem.sv` must deal with DMMU translation, while a lower path near `bp_be_dcache` must supply physical tag/metadata correctly. Line-wide transfers can be a later optimization.

### Regfile Access

Extend `bp_be_regfile_mt` with a debug/service scan port or tightly scoped context-service port:

- one read per cycle for save
- one write per cycle for restore
- selected by `{resident_slot_id, reg_index}`
- active only when the scheduler is stalled/drained

Current `bp_be_regfile_mt` uses synchronous memories and one write port. The least invasive candidate based on current ports is:

- reuse an existing read port for save only while ISD is blocked
- reuse the existing write mux shape for restore, similar to CSR `rpush`
- give context-restore writes priority only after the drain condition proves no normal writeback/rpush collision is possible

Adding a dedicated service port remains a later optimization candidate, but it increases area and is not part of the first version.

### D-Cache Access

Add a context-engine load/store request path inside or adjacent to `bp_be_calculator/bp_be_pipe_mem.sv`, where normal D-cache packets are already constructed.

Do not start with a top-level LCE-side mux. At `bp_be_top.sv`, the interface is already below the load/store abstraction, after tag/data/stat memory arbitration and cache request metadata are involved.

V1 constraints:

- one outstanding context-engine request at a time
- no overlap with normal load/store issue
- no attempt to optimize miss latency yet
- waveform-visible state for request, response, current reg index, and target address
- service path must respect D-cache busy/ordered/credit behavior

Alternative implementation to consider before RTL edits:

- use existing software-visible stores/loads to initialize/check context memory images for a first test
- optionally use cooperative self-save/self-restore test code
- then replace the software-only image handling with the hardware context FSM once the saved-image format and tests are proven

This is especially useful because current bootstrap CSRs `0x082` and `0x083` are physical-slot addressed. Nonresident logical contexts need either:

- a memory image initialized by software before first switch, or
- new logical-context bootstrap CSRs, or
- widened versions of the existing bootstrap CSRs.

The memory image is the least invasive starting point.

Limitation: software cannot non-cooperatively save an arbitrary resident slot's GPRs today. CSR `0x083` is remote write only; no remote-read/`rpull` equivalent was found. Hardware regfile scan is still required for transparent eviction.

## Concrete Implementation Surfaces

### Parameter And Type Plumbing

Likely files:

- `bp_common_aviary_cfg_pkgdef.svh`: add `num_contexts` to the processor configuration struct if we want it to be a first-class config parameter.
- `bp_common_aviary_defines.svh`: derive `num_contexts_p` and `context_id_width_p`.
- `bp_be_defines.svh`: add logical CTXT target fields to dispatch/reservation packets and update packet width macros.
- `bp_be_scheduler.sv`: decode CTXT target into `context_id_width_p` while preserving issue packet `thread_id` as physical.
- `bp_be_calculator_top.sv`: carry logical CTXT target through reservation/fast handoff until `bp_be_top.sv` can translate it.
- `bp_be_top.sv`: own resident map, pending logical target, physical resident target, and slow-path FSM.

### FE Boundary

Keep FE physical:

- `fe_ctxtsw_thread_id_o`
- `bp_fe_cmd_pc_redirect_operands_s.context_switch_thread_id`
- branch metadata `thread_id`
- PC-gen predictor array selection

Logical IDs must never enter FE in this design. FE only needs the resident slot selected by the map.

### CSR Boundary

CSR `0x081` is the software-visible logical context ID. The read path now carries `current_context_id_i` from `bp_be_top.sv` through `bp_be_calculator_top.sv`, `bp_be_pipe_sys.sv`, and `bp_be_csr_wrapper_mt.sv` into `bp_be_csr.sv`, where CSR reads return the logical ID rather than the physical resident slot. Existing resident-only tests cover this as a no-regression path; a logical-ID-not-equal-physical-slot runtime check still needs the nonresident restore path.

CSR `0x082` and `0x083` currently seed physical slots. Options:

- keep them physical-only and use memory images for nonresident context initialization
- add new logical-image init CSRs
- widen/redefine them to use `context_id_width_p`

Keeping these CSRs physical-only avoids RTL changes to the existing bootstrap CSRs for the first resident-cache experiment, but it requires new tests that initialize logical context memory images directly.

### Drain Detection

Signals that are already available near `bp_be_top.sv` and must be evaluated:

- `hazard_v`
- `ordered_v`
- `mem_busy_lo`
- `mem_ordered_lo`
- `late_wb_v_lo`
- `late_wb_yumi_li`
- `late_wb_pkt.thread_id`
- `cmd_full_n_lo`, `cmd_full_r_lo`, `cmd_empty_n_lo`, `cmd_empty_r_lo`
- scheduler `ptw_busy_lo` is local today, so exposing a PTW-busy/drained signal may be necessary.

Verify the drain condition with waveform before save begins.

### Regfile Service

The least invasive candidate is to add service controls to `bp_be_regfile_mt` and connect them through `bp_be_scheduler`:

- service read enable/address/thread
- service read data valid/data, accounting for synchronous memory latency
- service write enable/address/thread/data
- arbitration against normal writeback and `rpush`

Because `bp_be_regfile_mt` has one write port, restore must occur only when normal writeback/rpush are inactive by construction.

### D-Cache Service

Do not start by muxing at the top-level LCE interface. Add a context-service request source where `bp_be_calculator/bp_be_pipe_mem.sv` currently constructs `bp_be_dcache_pkt_s`, or add an adjacent service path next to `bp_be_dcache` that still respects:

- DTLB/physical addressing choice for the reserved backing region
- cache busy/ordered state
- cache request credits
- one outstanding request at a time for V1

Open design point: the context image would be simplest with physical/cacheable backing addresses, but the current `bp_be_calculator/bp_be_pipe_mem.sv` path normally uses the DMMU. Choose between:

- generating a request with translation disabled or with a known direct-map address
- adding a lower physical request path near `bp_be_dcache`
- intentionally using virtual addresses and requiring valid translation state for the context engine

The third option has a concrete ordering risk for V1 because context restore may need to work before the target context's SATP/translation state is restored.

## Verification Plan

### Cleanup Checkpoint

Before implementing:

- archive or revert any unverified diffs
- revert failed experiments
- remove generated waveform/debug clutter
- verify both repos are clean except this planning document

### Build Checks

- `git diff --check`
- `git -C import/black-parrot diff --check`
- `make -j24 prep_lite`

### Resident-Hit Regression

Use existing two-context tests. Passing resident-hit tests must not enter the context-cache FSM:

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
- `mt_ctxtsw_context_cache_metadata`: verify NPC, privilege/translation metadata, and ASID/SATP behavior according to the chosen V1 scope.
- `mt_ctxtsw_context_cache_cooperative_image`: software initializes/checks logical context images in memory without requiring transparent hardware eviction.

Before these, add a narrow plumbing test:

- `mt_ctxtsw_logical_id_decode`: build with two resident slots and at least four logical contexts; write CTXT target `2` or `3`; verify waveform shows the full logical ID before resident-miss handling, not a truncated physical slot.

### Waveform Acceptance

Resident hit:

- no context-cache FSM activity
- sideband/ISD forwarding behaves like current optimized path
- no extra stalls beyond known resident-hit behavior

Resident miss:

- early FE sideband is suppressed
- no target logical context dispatches before restore completes
- `commit_pkt.ctxtsw` is observed before victim save begins
- drain condition is satisfied before first victim regfile read
- victim registers are saved with the old resident slot ID
- target registers are restored into the selected resident slot
- restored NPC/priv/translation/ASID metadata is visible before FE redirect
- resident map updates before FE redirect
- normal instruction issue remains blocked while context-cache FSM owns regfile/D-cache service ports

## Performance Reporting

Report resident-hit and resident-miss performance separately:

- resident-hit context-switch overhead
- resident-miss hot-L1 save/restore cycles
- resident-miss cold-cache behavior
- cycles spent in each FSM state

V1 resident misses serialize 31 register saves and 31 register restores with word accesses, plus metadata and D-cache service latency. That makes resident misses structurally slower than the current resident-hit path, but the exact cost is unmeasured until the service path exists.

## Explicitly Unverified Or Out Of Scope

- Area/fmax benefit from reducing resident slots after adding the resident map and context-cache FSM.
- Exact drain predicate for a victim resident slot.
- Exact D-cache service insertion point and translation/bypass mechanism.
- Resident-miss cycle cost.
- Minimum CSR subset for address-space/privilege tests.
- Predictor isolation beyond the resident physical slots.
- RTL build/simulation for this document revision; this pass is code-analysis and planning only.

## Risks And Open Questions

- Whether the cleanest regfile service path is a new port or a mux around existing read/write ports.
- Whether D-cache arbitration is easiest in `bp_be_calculator/bp_be_pipe_mem.sv` or in a small side engine next to `bp_be_dcache`.
- Exact drain condition required before saving the victim slot.
- How to initialize backing memory for never-before-resident logical contexts.
- Which CSR/translation state V1 must preserve.
- Whether synthesis is improved enough by reducing resident slots to two after adding the context-cache FSM and maps.
- Whether a software image prototype should precede the hardware save/restore FSM to prove image format and tests.
- Whether the D-cache service should bypass DMMU or use a direct-map virtual address.

## Commit Strategy

Use small commits:

1. Done: add `num_contexts_p` / `context_id_width_p` and CTXT logical-target plumbing with no behavior change for `num_contexts_p == num_threads_p`.
2. Done: add resident map and logical-to-resident translation for resident hits; verify existing resident tests.
3. Done: add resident-miss detection that reports an explicit unsupported/halt condition; verify target IDs above resident count are no longer truncated.
4. Done: add context image format and tests that initialize/check images without hardware eviction.
5. Done: add passive context-cache FSM skeleton with counters/waveform signals but no active save/restore. Verified with `git -C import/black-parrot diff --check -- bp_be/src/v/bp_be_top.sv`, `make -j24 prep_lite`, clean traced `mt_ctxtsw_smoke_test`, and clean traced `mt_regfile_test`.
6. Done: add explicit scheduler/calculator drain-ready observation signals and gate the passive FSM's `wait_drain -> save_regs` transition on the combined drain-safe condition. Verified with `git -C import/black-parrot diff --check`, `make -j24 prep_lite`, clean traced `mt_ctxtsw_smoke_test`, and clean traced `mt_regfile_test`.
7. In progress: add regfile scan save/restore support without D-cache traffic. Current checkpoint adds integer-regfile scan read/write plumbing and local shadow storage, verified not to disturb resident-hit smoke/regfile flows; it is not yet end-to-end exercised because nonresident switches still stop at the intentional simulation fatal before scan states run.
8. Add D-cache save path.
9. Add D-cache restore path.
10. Add resident-miss end-to-end tests.
11. Clean debug instrumentation and document measured costs.
