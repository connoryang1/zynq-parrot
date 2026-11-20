This review checks whether the existing replay storage can provide real victim instruction capacity instead of duplicating new fills. It identifies a possible implementation that reuses current SRAM output retention without adding a full-line staging register or speculative memory traffic. This is a design review only; no victim RTL has been implemented or accepted.

# Decision

The approach is feasible in principle with **bounded ownership of the SRAM read outputs**. Merely tapping the raw Q signals is unsafe: a frontend read or recovery read can replace them halfway through the copy. The minimal safe control needs an old-victim tag read, precise replacement metadata, a short read-ownership token, beat-stream arbitration and a deferred recovery rule. Its complete execution cost and routed fit remain open.

The current four-mode program supplies no evidence that it needs victim capacity: it consumes no side-only line and warms fewer instruction lines than ordinary L1 can hold. A new victim policy should therefore be evaluated against broader natural instruction pressure under the full-burst wrapper; changing these benchmark addresses to force a win would not establish application value.

# Existing mechanisms that can be reused

`bp_fe_icache.sv` already has a physical-tagged 32-entry, four-bank/eight-way store, a registered one-beat input, per-entry full-line beat validity, normal-MMU-gated lookup, uncached bypass and accepted-fence invalidation. Side hits execute directly and do not install another ordinary-cache tag, so an evicted line can remain useful in the side store without a swap-back protocol.

The normal replacement way is `hit_or_repl_way` on the metadata cycle after accepted request. Invalid ways have priority, so a cached miss whose TV valid-way vector is not full needs no victim admission. The ordinary tag SRAM Q cannot simply be assumed to remain associated with that metadata: the next frontend lookup may already have read another set. Read the selected old physical tag under ownership, then latch only tag/set/way and validity.

The banked data SRAM path already supports `e_cache_data_mem_read`, selecting every bank's piece of a chosen way and producing a complete line through `data_mem_o`. Each bank uses `latch_last_read_p=1`; the BaseJump implementation explicitly retains its previous synchronous read output across writes. These existing output latches can hold the old victim while new refill writes update the underlying SRAM. A read followed by a no-read settle/latch cycle makes ownership and read/write collision boundaries explicit.

Do **not** rely on UCE `dirty_data_r` as free storage. Although a full-line register exists in generic UCE source, the instruction cache has no dirty writeback and that register may currently be optimized away. Activating it would add precisely the 512-bit staging the proposal is intended to avoid. Stream from the held raw bank outputs instead.

# Proposed bounded cache-local flow

1. On an accepted ordinary cached miss with all TV ways valid, arm a potential-victim token containing the miss set. Do not admit uncached requests, fences, speculative lookup-only work or invalid-way replacements.
2. At the matching metadata cycle latch the exact replacement way. Under explicit read ownership, issue an old-tag read and an existing-style full-line SRAM read of that same set/way. If the old tag is invalid, release ownership and skip admission. Snapshot arbitration must hold an early arriving normal refill tag/data write until these reads have safely captured the old contents.
3. After the synchronous read/last-read latch boundary, retain only small victim tag/set/way metadata and a beat counter. Stream the old line's physical words into the existing registered replay input, in aligned beat order. Parameterize the count by `block_width_p/fill_width_p`: this matrix needs eight 64-bit beats; a 128-bit-fill configuration needs four.
4. Once the last old-data payload has entered the existing packet register, release raw-Q ownership. Ordinary refill **writes** can overlap streaming after the old read latch is stable. Every data **read**, including a queued frontend lookup and `do_recover`, must wait until the last payload is captured. If a very short response completes meanwhile, hold `e_recover` and perform its postponed reread before returning to normal readiness; silently skipping recovery would leave stale frontend SRAM metadata/data.
5. Preserve the existing full-line publication rule. Abort or accepted `fence.i` cancels both the victim token and queued publication from that epoch. Partial entries remain invisible. A completed victim is physically unique only after the ordinary incoming tag actually replaces it; an aborted pre-replacement snapshot may merely duplicate an ordinary line and must not be counted as extra capacity.

Victim-only mode must disable new-fill duplication; admitting both policies into the same store would refill it with copies of the incoming ordinary lines and defeat the capacity isolation. Keep the existing demand-copy mode as a separate control. Any combination with trained replay must likewise be an explicit comparison rather than an implicit admission-policy change.

For the real eight-way/64-bit-bank layout, select the appropriate raw bank word using the latched victim way plus stream word index. Avoid an unnecessary 512-bit barrel-rotation datapath if a narrow 64/128-bit selection suffices. The existing `data_mem_o` rotation uses `data_mem_pkt_way_r`, which is currently updated every cycle: unrelated incoming packets can change it. Either pin the rotation selector under ownership or use the latched victim selector directly; leaving that selector live would copy wrong words despite stable raw Q.

# Arbitration, correctness and area risks

- **Shared input starvation:** ordinary replay beats and victim beats use the same registered side-store input. Specify bounded arbitration. Giving replay unlimited priority can hold frontend read ownership indefinitely; giving victim priority must backpressure the existing replay ready/valid handshake correctly. Do not acknowledge and drop an incoming replay beat accidentally.
- **Immediate responses:** correctness cannot depend on 40 or 200 synthetic ticks. A zero/short-latency response can reach the SRAM before snapshot completion. Hold only the conflicting initial read/write boundaries and preserve the complete ordinary refill/critical/last handshake.
- **Abort and fence:** a partial old victim, an already registered final beat and a new invalidation can coincide. Fence must win all publication metadata. Releasing raw-Q ownership after abort must not leave a late stream beat able to republish stale code.
- **Already queued frontend work:** gating new `yumi_o` alone is insufficient. A TL request accepted at the miss boundary and the existing recovery state can still request a new SRAM read. The read exclusion and eventual recovery must be explicit; avoid reintroducing the historical UCE/SRAM combinational-ready cycles.
- **Admission/replacement interpretation:** this is all-valid-victim admission, not the selected prefix from replay training. It changes retained contents and replacement policy even at identical capacity. Keep that distinction in comparisons. The existing hash still provides eight ways per bank, not arbitrary fully associative 32-line retention.
- **Physical area/timing:** existing storage is reused, but narrow word selection, selected-tag handling and read/response arbitration add muxes/control/fanout. The accepted FPGA route has very little slice headroom. A source-level lack of a new 512-bit array does not prove area neutrality; an early routed fit gate is required after correctness, before any board performance claim.

# Required gates before a performance experiment

A directed cache test should force a valid ordinary replacement and verify that the evicted old physical line executes from the side store after its main-cache tag has been replaced, while the incoming line and all other main ways remain correct. Invalid-way fills must not train victim admission. Exercise every replacement way, all words, eight-beat and four-beat configurations, repeated bank collisions, source-buffer replacement, and a victim already resident in the side store.

Test raw-Q stability while normal refill writes update the same SRAM rows. Then deliberately attempt a queued frontend read and `do_recover` during every stream beat; they must wait and subsequently execute correctly. Sweep immediate/short responses, critical-first/rotated packet stress, abort before the snapshot, abort during the stream, abort with the last payload registered, accepted fence at each boundary, and incoming replay backpressure. Assert eventual ownership release and unchanged ordinary demand results. Keep timing/overhead counters for the full miss and complete transaction, rather than counting only saved local fills.

Finally use a complete full-burst core model with representative instruction/data demand and the exact same workload in baseline, same-capacity victim and replay modes. Count admitted valid victims, completed entries, side-only consumed lines, unused replacements and added demand/redirect stalls. Only a successful routed FPGA implementation and matched complete Linux execution can establish physical application value.

# Prior evidence

No implemented true I-cache victim-admission experiment was found in the maintained research ledger, context-resume plan or retained experiment READMEs. The earlier shadow/retained-line proposals copy incoming fills or preserve context first-use lines; they are different policies. Existing larger-L2 and data-victim investigations already show that restoring local warmth can fail to improve complete Linux handoff. They justify measuring the complete endpoint here, not assuming that more retained instruction capacity necessarily helps it.
