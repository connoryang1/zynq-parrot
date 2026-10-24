This directory records the first live full-core producer for the independent D-cache data-preview queue. It distinguishes request-level transport evidence from context-switch speedup and retains exact commands and closed traces for the isolated simulator checkpoint.

# Translated hint adapter

The isolated branch `experiment/target-data-preview-producer` starts at top-level `4961bae8` and BlackParrot `007fadc6e0fcec13777a3421b385483907651768`. `bp_unicore_lite.sv` now sends D-cache `e_cache_prefetch` requests, whose address is already translated and checked by the D-cache, to the UCE physical preview port. It returns the queue-ready handshake to the D-cache and discards exactly the hint's one-cycle-later metadata; ordinary requests and their delayed metadata still use the architectural UCE port. The preview cancel input remains low, so this is a same-address-space transport stage, not a task or address-space lifecycle interface.

The simulator and testing directories were cleaned in separate completed commands before the first build. The clean traced oracle command was:

```sh
make -C testing run-mt_context_preview_oracle_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=8 ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install
```

It passed all 12 guest rows, the test-specific marker, `CORE PASS`, `BSG PASS`, and host exit zero. Its 12 measured cycle values are identical to the tied-off-queue checkpoint: `0x244, 0x223, 0x151, 0x22c, 0x205, 0x21c, 0x151, 0x224, 0x205, 0x21c, 0x179, 0x224`. This is functional transport evidence, not a timing gain. The closed `adapter-oracle.fst`, `adapter-oracle.log`, `adapter-build.log`, and `adapter-prog.nbf` have SHA-256 `b79728dbf91adaf9c286108968f46b850fce0487bb0f5b5b9b99946de92e41fc`, `efe0dc64ec67c517fe07cf19714ec2d6644134028ee1a1ded31109e5f4aa4b66`, `2a364852ab385011c2e07ec0690f4eed294fc10f69c1caa87c4c408a6fbf3b55`, and `6c0e6655671b1c07553787fecf6e8c3dcbf473395f7bd34fd47c848db58f3eda` respectively.

`analyze_adapter_wave.py` streams the closed FST through `fst2vcd`, samples at rising edges of the D-cache UCE clock, and excludes the time-zero initialization sample. `adapter-oracle-wave.json` records 21 preview requests, accepts, enqueues, dequeues, and forward issues; 1,059 ordinary accepts and 1,059 forwarded metadata events; and a maximum live queue occupancy of one. The standalone UCE test in `logs/target-data-preview-lane-sim-20261024/` covers the full-queue case. The 42 prefetch response samples are beat-level handshakes, not 42 completed requests. No issue-to-demand or side-buffer consumption attribution has been extracted from this trace.

The same built simulator also passed:

```sh
make -C testing run-mt_ctxtsw_smoke_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 SIM_DEFINES='BP_DCACHE_PREFETCH_ELS=5 BP_PREFETCH_AXI_BYPASS' VERILATOR_BUILD_JOBS=8 ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install
make -C testing run-mt_umode_prefetch_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 SIM_DEFINES='BP_DCACHE_PREFETCH_ELS=5 BP_PREFETCH_AXI_BYPASS' VERILATOR_BUILD_JOBS=8 ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install
```

Both had their test-specific guest markers, `CORE PASS`, `BSG PASS`, host exit zero, and closed FSTs. The smoke log/FST SHA-256 values are `7556544dc8c9626bdc8c272f1804c8cc85a5a803aa20977873ccb8bc11a705c3`/`ec9510340d0fbe3f338e49ffa679d60afd1e965adf3e0680b7fb5dc87d3f77d8`. The U-mode prefetch log/FST values are `fc77921e8e88bc3243fac9a9f4fdf68e22988cdfd92f4e3b263627861f89a4ee`/`2ed2ee926a4123f3bea577381cd10e7744ded136f87c4fd0921308136475e2f8`.

The U-mode trace records one permitted preview request/accept/enqueue and 397 ordinary accepts with 397 forwarded metadata events. That permitted queued hint was removed when the immediately following demand caught it; no preview forward issue or response occurred in this test. Thus this gate supports translated admission and nonfaulting denial, while the oracle trace supplies actual preview issue evidence. The oracle and U-mode JSON summaries hash to `357f69c835d7724da9330f983d3724392f18b02fe1b0812707cc243c0a60c0e6` and `0383734c7840654daf5da5c0dfc8cb298b83386d44ec84eb676e79f7182641a8`.

The oracle hints are issued by a target-context helper before it yields back to the source. This checkpoint does not select a target Linux task, translate a different task's virtual address, cancel work on task/mm reuse, route on the FPGA, or establish a one-way Linux speedup.
