This analysis checks that the demand-copy feature actually trains and publishes lines during the matched full-core controls. It separates mechanism engagement from extra unique capacity and from prefetch benefit. It also identifies the minimal wrapper's serialized word transport so its memory-latency sweep cannot be mistaken for a cache-line DRAM projection.

# Engagement is proven; useful extra capacity is absent here

The exact `on40` FSTs expose `replay_buffer_demand_capture_p=1`. Sampling stable values before actual BE rising edges gives:

| Existing control | CSR-commit window | Whole-run cached misses | Accepted copied beats | Complete publication epochs | Complete prefix lines at timed begin | Consumed side-only fetches, whole run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold | 5,544 | 39 | 312 | 39 | 0 | 0 |
| Target warm | 807 | 39 | 312 | 39 | 7 | 0 |
| Source warm | 1,474 | 39 | 312 | 39 | 7 | 0 |
| Switch only | 721 | 32 | 256 | 32 | 0 | 0 |

All accepted capture beats become registered writes. Each line has eight 64-bit beats in this full-core configuration; the earlier standalone unit used four 128-bit beats. Every captured physical line matches its accepted cached-miss address, every capture observes the ordinary data handshake, and no side hit overlaps an ordinary-cache hit. No provenance issue is detected in any of the four traces.

In the two warm modes, all seven prefix lines (`0x80001000` through `0x80001180`) are complete in the side store at timing start, yet all 50 timed prefix fetches use the ordinary cache path. There are no timed prefix misses or side-only fetches. This distinguishes a mechanism with no useful extra capacity in this workload from a disabled mechanism or aborted/partial publication. In the cold mode the 50 ordinary-path prefix fetches include normal refill/critical forwarding, so they should not all be described as already-warm L1 hits.

The raw 32-line store is **not 32 guaranteed additional unique lines**. New-fill admission first duplicates the ordinary cache's copy. The current controls execute only 39 ordinary instruction-miss epochs (32 for switch-only), have at most 27 completed side entries at once, and never consume a line available only in the side store. These results support retaining the feature as a noncorruption/capacity control; they establish no speedup and do not bound its value under a larger natural instruction footprint. They do not support changing the benchmark's address placement to manufacture a gain.

`capture-engagement-summary.json` binds the exact ELF/FST/parser inputs and all four per-mode `capture-engagement.json` files. Timing boundaries are retired global-cycle CSR reads at the exact archived ELF's PCs `0x8000040c` and `0x80000414`. Their commit-bounded lengths happen to match the reported benchmark lengths here; the analysis does not redefine a general counter or context-switch latency metric.

# The latency factor is serialized AXI-Lite word service

The `on40` cold-mode waveform contains exactly **128 accepted AXI AR requests** inside that 5,544-cycle window. Every request has `ARLEN=0`, `ARSIZE=2` (one four-byte word), and the eight touched 64-byte lines each require sixteen requests. The memory responder and BE clocks share the exact same VCD signal identifier. Maximum outstanding AR across the whole run is one, even though the memory model has four queue slots. Every timed request has exactly 40 ticks from accepted AR to first offered R and to accepted last R, with no protocol issue.

The independently checked `on200` cold trace has the same 128 one-word requests over the same eight logical lines, maximum outstanding count one, and verified identical BE/AXI clock. Every AR-to-first-R and AR-to-last-R interval is exactly 200 ticks; its closed CSR window is 26,024 cycles. The two detailed per-mode transport JSON files retain their distinct raw simulated DRAM base addresses without confusing those with architectural instruction addresses.

This matches the source: `cosim/black-parrot-minimal-example/v/top_zynq.sv` connects the ordinary AXI-Lite master to HP0 with zero ARLEN and four-byte ARSIZE, while `bp_axil_master.sv` supports one outgoing request. `bp_nonsynth_axi_mem_pipelined.sv` correctly applies its fixed first-response latency to **each accepted AR**, rather than to each whole cache line. The BE and memory responder both use the same `aclk`.

Consequently the observed cold change from 5,544 at configured latency 40 to 26,024 at latency 200 is `128 * (200 - 40) = 20,480` cycles of serialized word service. It is not a sixteenfold clock ratio, a measured physical DRAM penalty, or a whole-line first-response sweep. The minimal wrapper data remain conditional functional/capacity controls. A defensible line-latency sensitivity experiment should use the full-burst `cosim/black-parrot-example` path (whose cache-to-AXI adapter sets burst length from the cache line width), preserve identical bandwidth/pacing and complete execution boundaries, and verify its actual AR/R shape before interpretation.

The detailed transport results are `on40/mode0/axi-word-service.json` and `on200/mode0/axi-word-service.json`; `tools/analyze_axi_word_service_vcd.py` counts accepted handshakes at the verified clock and binds them to the same architectural CSR window.

# Reproduction

For each closed mode FST:

```sh
fst2vcd research/resume-retention-matrix-20261120/on40/mode1/dump.fst \
  | python3 -B tools/analyze_icache_demand_capture_vcd.py \
    --output research/resume-retention-matrix-20261120/on40/mode1/capture-engagement.json
fst2vcd research/resume-retention-matrix-20261120/on40/mode0/dump.fst \
  | python3 -B tools/analyze_axi_word_service_vcd.py \
    --output research/resume-retention-matrix-20261120/on40/mode0/axi-word-service.json
```

The parsers check signal presence, actual clock identity where required, accepted transactions, full beat masks and closed timing windows. No RTL, guest source, address table or board state was changed by this analysis. No Linux or FPGA performance result follows from it.
