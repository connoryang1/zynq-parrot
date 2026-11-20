This gate tests whether a complete, checked ordinary-lookup trace can support an honest L1-D reuse/capacity analysis across context switches. It reuses an immutable existing full-burst simulator; it introduces no RTL, explicit prefetch, replay address table, or cache-policy change. The first case failed its trace-size bound, so this directory contains a diagnostic failure, **not accepted capacity or execution-performance evidence**.

The program allocates four private immutable lookup tables before seeding a serialized four-logical-context ring on two resident slots. Each actor executes eight warm and eight timed requests; each request performs the unchanged header's 64 generated hash lookups (56 successful and eight absent keys). A single initialized aligned 64-bit configuration word selects a 1 KiB or 32 KiB table per actor. The proposed larger case must reuse exactly the first ELF. No 32 KiB run has been executed.

Each request stores CSR `0xcc0` begin/end timestamps in memory. The global timed interval includes all 32 timed requests, 32 context handoffs, and the per-request metadata/checksum writes. All printing and independent expected-total checks occur after timing. The access audit must include all cached references, including setup, stacks and metadata, while reporting target-table reads separately. Allocation bytes denote table storage, not a guarantee that every byte is read in every request.

The selected FFC simulator's L1-D is **32 KiB**, source and waveform confirmed: 64 sets × eight ways × 64-byte lines (`sets_p=64`, `assoc_p=8`, `block_width_p=512`). This is distinct from the historical 8/16 KiB **L2** capacity experiments. Four 1 KiB tables fit in nominal L1-D capacity; four 32 KiB tables exceed it, but actual replacement/reuse must come from full accesses and actual tag writes, never a miss-only reconstructed trace. Any future capacity replay would remain a conditional fixed-access control, not Linux or FPGA performance.

The `one-kib/session.json` binds the source snapshots, compiler command, exact ELF/NBF, model, runtime log and stopped trace. Important identities:

| Artifact | SHA256 |
|---|---|
| Immutable full-burst capture-off40 model | `85505d381643fca1a118c9e5d6930468e9bcce736ebfd0a926fb36419064af8b` |
| First ELF | `cc97e23db7f56f59dd25be41b7e179d8643078fdee9d71e96d1ab3597216c204` |
| Patched 1 KiB NBF | `3d81205d5f49b5978e2a9451c961c4304ce6c2373b52e0982f57f24823f987e1` |
| Runtime log | `ab2226288bb603fb6698ee088abf088630c116b222005dbb19fce3ecda4121d3` |
| Stopped, truncated FST | `cd7332774dccc5e3e2d3e8f7edde4dc5832562b6a719cc470896fef685d23e11` |

The model source is BlackParrot `ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57`, with full-burst transport, capture disabled and 40 memory-model first-response ticks per accepted AR. These are simulator conditions; there was no FPGA session or model build.

The first run stopped after 288.91 seconds with `SIGXFSZ` (exit `-25`) when `dump.fst` reached exactly 157,286,400 bytes (150 MiB). It had not printed the post-check custom marker, CORE PASS or host BSG PASS. The unchanged archived `testing/check_run.py` rejected the transcript. No target-region metadata or complete timing result is accepted. The original failed manifest uses the key `closed_fst`; that key means only that the process had stopped and the file was hashed, **not** that the FST was properly finalized. The runner now calls it `stopped_fst` and retains the acceptance-log hash even on rejection. The archived original runner remains unchanged for reproducibility.

The independent access auditor first validated the old retained 24 MiB FFC trace: 4,742 accepted cached accesses, 4,639 normal hits, 103 misses, 103 tag publications, 824 refill beats, and 103 complete refills. Actual synchronous tag-read outputs matched throughout. That old trace contains no actual evictions, so it validates extraction but supplies no capacity curve. The audit samples D-cache/UCE on their actual clock edge (inverted from BE), and retired CSR labels on the BE edge. The failed new FST may be used only to localize execution progress if its truncated blocks are readable. Expansion to 32 KiB remains gated on a complete first case and accepted full-access validation.

A bounded 60-second parsing diagnostic read a **prefix** of the failed trace through global cycle 273,358. Begin/end retired-label counts were 3/3 for each of logical actors 0, 1 and 2, and 3/2 for actor 3. The last observed retired PC `0x80000c64` was in actor 3's lookup probe loop (resident slot 0); nearby retired PCs were advancing within that loop. This establishes progress through more than two warm rounds in the inspected prefix. The parser deliberately stopped at its time bound, so this is neither the final waveform state nor proof against a later stall. It supplies no accepted complete-request or capacity measurement.
