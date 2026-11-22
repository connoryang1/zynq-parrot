R7 job20261122T003339Z-eb7d39013 used TOPeb7d390134a0025331a2366a979a774263b146d5/BP8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c and the actually packaged canonical backend68d1dd0c…cbea6. Synthesis succeeded; detailed placement failed with Place30-487 before routing. ROOT's terminal receipt records worker/vendor absence and no identity, feedback-cut or budget violations; a later, separately closed read-only optimized-DCP query returned0, preserved DCP identity and had no physical or synthesis operations. This curation launches no tools and preserves earlier failures rather than superseding their outcomes.

| Stage/fact | R5b | R7 |
|---|---:|---:|
| Synthesized adjusted LUT |56,251|54,617|
| Synthesized FF |33,071|31,011|
| Synthesized BRAM tiles |140|140|
| Detailed-placement combined LUT |58,801|57,154|
| Detailed-placement total LUT instances |68,193|66,496|
| Detailed-placement FF |33,077|31,022|
| Detailed-placement control sets |1,437|1,181|
| Required remaining slices |11,715|11,275|
| Available remaining slices |10,893|10,871|
| Remaining packing gap |822|404|

These are corresponding reported stages, not interchangeable resource metrics. R7 synthesis is1,634 adjusted LUTs/2,060FF lower, and its actual placement gap is418 smaller; varying placement occupancy/control sets/LUT combining prevent conversion of that gap into a hard required LUT-saving count. Both1792-line cases fail placement, so neither establishes maximum usable physical capacity. BRAM is fully allocated; raw bits, simulation correctness and standalone inference do not prove an implementation fits or meets20MHz.

All six actual child features are exactly retained_buffer1,I1792,D1792,sets256,retained-use-observe1,response-delay0. Each side configures114,688B=112KiB of full64B payload,229,376B=224KiB total, separately from ordinary L1I/D64sets×8ways×64B=32KiB each and ordinary L2one slice×two banks×64sets/bank×2ways×64B=16KiB. All three recorded generated package copies select static-prefetch16k; bound source inheritance supplies associativity/block sizes. The clock wizard requests20MHz from the separately recorded PS50MHz upstream clock; this is configuration intent, not routed timing closure. Eight synthesis workers and sparse-source1 are recorded. Historical f744/f091 four-KiB L2 or custom one-bank application models are separate baselines and are not pooled here.

The **optimized DCP**, not the placement failure database or old R5b synthesis query, reports54,170 adjusted LUTs=50,253logic+3,917memory,31,011FF and140BRAM. Its focused reports give retained store1,097LUT/2,211FF/56BRAM (969logic+128memory), D-UCE2,779LUT/2,998FF and I-UCE3,011LUT/2,839FF. The CPU core37,516LUT/17,782FF/77BRAM includes ordinary caches and must not be added to its descendants. Likewise named groups and retained-store/UCE buffers are attributions, not causal savings from removing a feature.

Canonical D epoch mapping appears as24RAM64M parents/96RAMD64E leaves; these describe the same distributed storage, not additive primitive counts. Its epoch-storage/access name group has9FF rather than the earlier2048-cell FF array; those9 include access/control state and are not proof of a nine-bit epoch store. Retained payload maps25RAMB36+2RAMB18 per side (26tiles), tags2RAMB36 per side, totaling52payload+4tag=56tiles. Primitive names show512 prefetched-install output FF per UCE and1,536 retained capture/hit/pending-data FF per UCE (2,048 line-buffer FF per lane altogether); the backend independently also has512 capture+512 response FF per lane. This identifies real storage/control costs but does not establish that snapshots can be removed without ownership, timing or correctness changes.

The prelaunch R7 budgets remain exactly2.5GiB work cap with1GiB work-volume floor,384MiB evidence cap with3GiB HOME floor,512MiB `/dev/shm` floor and10,800s deadline. Remaining allocations were charged to their own volumes; no postlaunch extension is introduced here. R6's earlier1.5GiB operational scratch stop, R5b placement failure, failed full-backend Xsim elaborations and successful narrower compositional gates remain distinct historical evidence. External synthesized DCP74cf4433…93766 (78,469,324B) and optimized DCP3606b688…57ef (23,218,998B) are retained unchanged outside Git; exact hashes and original immutable paths are in `bindings.json`.
