This derives full-burst and retained-publication timing from the three matched closed SP traces. It separates the memory-interface response from completion through the retained-prefetch path. These are simulated cycle counts, with no FPGA memory calibration or application speedup implied.

All arms use the same cold08 program, static16KiB L2, ordinary32KiB L1I/D, and1280 retained64-byte lines per side. The opaque HP0 stream auditors and strict full-payload/SRAM/counter checks pass. `path-timing.json` binds the exact closed evidence and derives publication intervals from accepted advisory and publication timestamps using the observed50000-FST-tick AXI clock period.

The FST timebase is1ps, so the observed AXI/core clock is20MHz. The compiled testbench separately requests a2500000ps real-time-clock period (0.4MHz), while the FPGA configuration requests8MHz for that clock. CSR0xcc0 is the core-wide counter incremented on core clock edges, independent of context save/restore. These bare-metal correctness and HP0 cycle observations therefore do not establish matched Linux timer/scheduling behavior or real-time FPGA performance.

| Added response age | AR→first accepted word | AR→accepted full8-word line | I advisory admission→publication | D advisory admission→publication |
|---:|---:|---:|---:|---:|
|0|1|8|101|76|
|40|41|48|181|156|
|200|201|208|501|476|

Each of648 read bursts has eight accepted words with one cycle between words; each arm also has487 completed write responses. All response ages equal the configured setting, with no observed shim stalls. Positive-delay queues peak at eight read words and one write response; the fixture observes one read and one write outstanding, which is its coverage rather than a platform concurrency limit.

The retained-publication interval includes upstream/cache/retained-path work beyond one HP0 burst. Its observed increase is twice the added response age in this fixture; this table alone does not establish which dependency contributes that extra wait or predict application gain. The earlier64-line pipeline audit is separate evidence and must not substitute its85/68-cycle native publication endpoints for the present101/76 endpoints.

Native FPGA request-to-first/full-line and prefetch-publication timing remain unmeasured here. Historical41-cycle architectural load-to-use timing is a different endpoint. Configured40/200 controls apply equally to demand I/D, prefetch and B returns; they model memory sensitivity while preserving observed burst bandwidth, rather than charging a delay separately to every word.
