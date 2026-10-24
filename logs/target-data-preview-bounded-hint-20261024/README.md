This directory records a bounded-retirement experiment for best-effort D-cache preview hints. It keeps the normal queue-depth and oracle results separate from a diagnostic build that deliberately made the preview queue unavailable.

# Bounded hint investigation

The first diagnostic testbench used an SV `wait(aresetn)` before forcing `preview_ready_o` low. The standard Verilator flow rejected that construct with `%Error-NEEDTIMINGOPT` because this model is built without event timing; the build failed before the guest started, and no result was inferred from it (`forced-full.log`). The guardrail is to use the existing clocked testbench process style, clean the failed build artifacts, and rerun before interpreting the diagnostic.

## Normal and queue-unavailable gates

The isolated `experiment/target-data-preview-bounded-hint` branch changes only the full-queue behavior of the D-cache adapter. A `prefetch.r` request now retires even if UCE `preview_ready_o` is low, so the queue may drop a best-effort hint without replaying the issuing instruction. The wrapper still suppresses that retired hint's one-cycle-later D-cache metadata. The earlier accepted producer checkpoint is top-level `a3826e15` / BlackParrot `5b4f55b4d8be`.

After separate simulator and testing cleans, this normal clean traced gate passed with the test-specific guest marker, `CORE PASS`, `BSG PASS`, and host exit zero:

```sh
make -C testing run-mt_prefetch_queue_depth_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 SIM_DEFINES='BP_DCACHE_PREFETCH_ELS=5 BP_PREFETCH_AXI_BYPASS' VERILATOR_BUILD_JOBS=8 ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install
```

The closed `queue-depth.fst`/`.log` SHA-256 values are `0c44997eaff26a4fd60997acd23f6f240c9706708db76aae61da7e2bdeaaa40c`/`d6abf5a2c8765a795311535e4c792b9d91783061b8314ab4ca40befd55b80063`. The clock-sampled `queue-depth-wave.json` has 30 hint retirements, 30 enqueues/issues, zero drops, 81 ordinary accepts and 81 metadata events; its maximum queue occupancy is only one. The JSON hash is `aa6edb47b1da68d8121160a5e213b2318256ab45b7364a726ce0eee12d4a3365`.

The same normal model passed a clean traced 12-row `run-mt_context_preview_oracle_test`; all rows are identical to the prior producer checkpoint, and the guest and host pass. The closed `oracle.fst`/`.log` hashes are `bc9434ec9b2ce53a4b08084130f6b4639ea8a54f0ba552e459b80b6d5ea7eec6`/`e67ddc0b34a457c069047b7da3a510fe442d303eeadbbcef312e36153c7569c4`.

For the refusal path, `force-preview-full.patch` adds a temporary testbench-only `BP_TEST_PREVIEW_FULL` force of UCE `preview_ready_o=0` after reset. The patch was checked with `git apply --check`; its first handwritten hunk count was invalid and was corrected before any run. After separate cleans, the same queue-depth test with `BP_TEST_PREVIEW_FULL` passed its guest and host markers. The closed `forced-full.fst`/`forced-full-clocked.log` hashes are `251e1fecc135e8f649d226b88188cc3d0892a241b83496c29b13c10d2be52e66`/`1438b4962aa66b56a94fb7d91a1cdec99226addfa60215958eb686d636e864ce`. The clock-sampled `forced-full-wave.json` counts 30 hint retirements and 30 drops, zero queue enqueues/issues, and 91 ordinary accepts with 91 metadata events; its hash is `21ef75bd0930e6e5458ad3915d660541ce760cba73be8d0d65dcbf5205569dc4`. This directly exercises a permanently unavailable admission port, the same ready condition seen by the wrapper when the queue is full.

The diagnostic patch was removed, then separate simulator and testing cleans preceded a final `run-mt_ctxtsw_smoke_test` with the normal `BP_DCACHE_PREFETCH_ELS=5 BP_PREFETCH_AXI_BYPASS` defines, `NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1`. It passed the test-specific guest marker, core/host markers, and exit zero. The closed `final-smoke.fst`/`.log` hashes are `5197d7bca2a6cf3ecec4065274ceef40ac877b5418cc42d8baac905f9d382d74`/`54cf7e928cfcecd460f6bb9eef2bd7323c6d4c4ea15fcc4a9cf689742e5b37bb`. The testbench source has no remaining diff.
