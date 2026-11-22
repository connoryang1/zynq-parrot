This review identifies which inactive CSR snapshot data is architecturally consumed and what an eventual integration must prove. The gates below are proposed, not executed. They preserve the tested masked-store preview and distinguish architectural equivalence from equality of an unused raw output.

## Exact consumer and redundant-mask hypothesis

At BP `bb575`, `bp_be_top.sv:235–236` declares four valid bits and four 1666-bit images in the production 2-thread/4-context configuration. Snapshot state has exactly one data read (`399`); valid has three reads (`370`, `384`, `396`). The wrapper `bp_be_csr_wrapper_mt.sv:274–281` broadcasts data/reset but qualifies restore enable by the chosen physical bank. `bp_be_csr.sv:189` casts the data; every one of its 26 CSR fields and privilege field is referenced only within `restore_v && !restore_reset` (`864–927`). The reset branch independently selects all-zero CSR words and M privilege, packed image `1666'd3`. SATP ASID WARL masking follows both branches (`930`) and must remain unchanged.

For an in-range target, define C=cache restore, R=resident initialization, V=valid[target], S=common live save data, M=raw memory image, P=the pre-existing lower-priority CSR next state. The consumed image is:

```
! (C | R) ? P : (C & !V) ? 1666'd3 : C ? M : S
```

Substituting `V ? M : 0` for M cannot change this consumed image: when C and !V, the reset branch wins; when !C, raw memory is unselected. Existing NPC/APC and physical-owner selection remain separate and unchanged. An invalid image's raw bits, including unknown or retained pre-reset bits, are consequently architectural don't-cares under this exact envelope. This is not permission to expose them as an architectural or debug readback.

The `0ed6f85` component contract explicitly returns zero on an invalid read. An unmasked candidate changes that raw-output contract even if the consumed image is equivalent. Its next discriminator must retain all valid bits and all 1666 consumed bits, compare reset/live/valid restore and prior-state hold, and exercise arbitrary invalid-memory contents. It must preserve source-owner independence and identical valid/write/reset behavior. The existing raw-output bit oracle cannot approve that change unchanged. This source argument identifies a potentially redundant gate; it neither assigns mapped LUTs to it nor predicts savings. Actual mapped cone/cell inspection and a matched one-change probe are needed to determine whether synthesis already removes it.

## Assertions before promotion

Check only after an asserted reset has been observed and after sequential/combinational settling; ignore no post-reset violation. Keep these as integration-test assertions or a bound ghost model, not extra production state:

- Assert `!(csr_snapshot_save_v_li && csr_snapshot_seed_v_li)` on every non-reset edge. Preserve exact decoder and common bank-selection bindings from exclusion proof `22982102…135d42`; reservation, retire, current, and save owners must vary independently in the gate.
- A store write must have an in-range selected address and the exact common save image. Save intent/address must match the old guarded ctxtsw write; seed intent/address must match the old guarded rebind-or-invalid NPC write. Neither an out-of-range save nor seed may change any valid bit or image.
- Reset must clear all valid bits and suppress writes; a written image becomes valid atomically on the same edge. A same-edge restore samples the old image/valid values, as the original nonblocking assignments do. Rebind, save, reset/write overlap, adjacent writes, and selected-address changes need explicit checks.
- Cache-restore consumption must imply an in-range virtual target and physical destination. Assert this before indexing the valid vector. A valid in-range read must equal the ghost old packed array; invalid in-range output must equal zero for exact `0ed6f85`. For an unmasked version, compare the qualified consumed image instead, retaining all other validity/address checks.
- Preserve resident initialization from the live save wire; preserve initialized resident NPC reseeding without CSR cloning; preserve APC-only writes, self-seed exclusions and all NPC/privilege/ASID bookkeeping. A shadow original full array can compare all valid images and the final qualified CSR next image without resetting the candidate's RAM.

The production component evidence covers 4 contexts ×1666 bits. Before claiming generic parameter support for this integration, add 1- and 3-context source-bound component cases: safe one-bit address width, zero-width avoidance, out-of-range IDs for 3 contexts, and no illegal index consumption. Generic dual-writer 1×65 evidence does not qualify those production-module corners.

## Minimal full-core regression ladder

Use one clean model with actual `NUM_THREADS=2 NUM_CONTEXTS=4`; resident-only elaboration is insufficient. Preserve current native/FPGA timing distinctions, static16KiB L2, ordinary L1 geometry, context ABI, trace profile and all retained controls. Require actual ELF/NBF hashes, test-specific PASS plus CORE/HOST terminal checks, native runtime bounds, closed traces and source ingestion. No command is authorized by this plan.

1. Run the existing checked full-core integrity and cold08 strict fixture to guard ordinary execution and unchanged retained full-line/observer plumbing.
2. `mt_context_csr_rebind_test`: initial inheritance, private MSCRATCH/SATP, ordinary resident NPC reseed, explicit rebind, and caller/target GPR preservation. `testing/Makefile:217` enforces the nonresident-capable topology even though this test principally uses resident target1.
3. `mt_umode_nonresident_sv39_data_handoff_test` and its shared base: cold logical context2 install, U-mode trap return, SATP/instruction/data translation, and return to logical0. This exercises the nonresident restore path; it is not a complete per-field CSR eviction oracle.
4. `mt_resident_reseed_irq_test` (shared fetch base) and `mt_protected_rpc_hardware_test`: pending-interrupt APC/PC correctness and protected descriptor/resident ownership. These cover the exceptional consumer controls intentionally left untouched by the patch.

These existing architectural programs do not independently check every bit of all26 CSR fields through repeated nonresident save/evict/restore. Retain the full1666-bit ghost-image/consumed-image integration miter above, including cold invalid restore, private context2/3 updates and eviction, instead of calling these programs exhaustive. Existing SATP WARL and CSR-isolation tests may supplement a failure localization; they do not replace the full-image gate.

## Actual source inclusion

The maintained TOP source list explicitly enumerates `bp_be_top.sv` at `cosim/black-parrot-example/Makefile.hardware:196`; add the new module there using the separate patch. `cosim/mk/Makefile.verilator` makes the model depend on VSOURCES and passes it to Verilator; `cosim/mk/Makefile.vivado` emits VSOURCES into the Tcl environment. A new file's presence alone is not inclusion evidence. Do not infer that a separate upstream VCS flist or automatic library search covers this module.

Before any integration acceptance, require the actual consumed-source inventory to contain the exact selected store and patched `bp_be_top`, while pinning the unchanged CSR engine/wrapper and source list. Check actual 1666-bit width, four contexts/two physical banks, unchanged17 geometry/profile constants, and all FPGA source-IP/final-BD/edit contexts if routing is later authorized. The new store adds no macro, CSR, policy, reset requirement, port latency, or ordinary cache geometry change.
