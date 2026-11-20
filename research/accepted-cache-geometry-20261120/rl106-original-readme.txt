This directory tests whether L2 retention, rather than hint generation, limits early context-resume data previews. It compares the same four completed physical hints and 4 KiB interference stream in clean 8 KiB and 16 KiB full-top simulations, then verifies a named 16 KiB FPGA configuration. The result is architectural evidence about retention; it is not yet a Linux or FPGA performance result.

# L2 capacity and retention experiment

## Result

- The clean 8 KiB model has two banks, 32 sets per bank, two ways, and 64-byte lines. After four completed target hints and the fixed 64-line interference stream, all four target demands issue new DMA reads. `8k-target-events-fresh.txt` records the four hint-time reads and four later demand-time reads.
- The clean 16 KiB model differs only in using 64 sets per bank. Its four target demands still reach the L2 controller, but none issues a DMA read. `16k-target-events.txt` therefore proves that all four early fills survived the same gap traffic.
- The outcome is consistent with conflict/replacement pressure from the already resident program image plus the 4 KiB stream. Merely doubling the original 4 KiB cache to 8 KiB is insufficient; 16 KiB separates the stream from the target sets in this experiment.
- A named `e_bp_unicore_zynqparrot_prefetch16k_cfg` endpoint inherits the accepted four-context/four-slot configuration and changes only `l2_sets` from 16 to 64 per bank. A fresh static-config build elaborates `l2_sets_p=0x40`, and the maintained `mt_prefetch_hint_test` reaches its guest marker, `CORE PASS`, and `BSG PASS`. The project checker accepts the run; the known DPI finalization assertion occurs only afterward.

## Exact scope

The directed capacity arms ran in the isolated historical worktree `/dev/shm/zp-linux-l2-tag-probe` at top `c8157859` and BlackParrot `be1967914`. Both used the same early-only test ELF (`dc1f63f...2208`), `NUM_THREADS=2`, `NUM_CONTEXTS=10`, `TRACE=1`, the two-bank and pipelined-memory defines, and a 1,000 ms native target limit. The 8 KiB arm set `BP_L2_SETS=32`; the 16 KiB arm set `BP_L2_SETS=64`.

The capacity command, after separately completing both simulator and testing clean targets, was:

```sh
env DEFINES='BP_ZYNQ_PREFETCH_TWO_BANKS BP_AXI_MEM_PIPELINED BP_L2_SETS=<32-or-64>' \
  make -C testing run-mt_physical_preview_gap_test \
  SIM_DIR="$PWD/cosim/black-parrot-example/verilator" \
  NUM_THREADS=2 NUM_CONTEXTS=10 TRACE=1 TARGET_RUNTIME_MS=1000 \
  ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install
```

The named static endpoint was built in the active integration worktree from pre-change top `68b7e916` and BlackParrot `174f2787a`. The testing wrapper cannot directly run a named CFG because it always forwards dynamic context dimensions, so the test ELF was rebuilt first and the simulator was then cleaned, built, and run directly with `CFG=e_bp_unicore_zynqparrot_prefetch16k_cfg`. The final build uses the current `processor.u.unicore` hierarchy without a configuration-specific host define; the generated trace source records `l2_sets_p=0x40`. The exact ELF is `a399e350...428ee`.

## Evidence and hashes

- 8 KiB events: `90587a52...a0f`; compressed waveform: `9b196400...b0e8`; build log: `3f575f7a...6043`; run log: `8fc1ef55...07d4`.
- 16 KiB events: `d3187df0...988c`; compressed waveform: `7e532d21...0cf`; build log: `900bbbb5...1cc7`; run log: `090f8157...7bd`.
- Final static 16 KiB build: `1c541d5b...8bdf`; compressed waveform: `ce5b07cd...7c39`; run log: `6b558c39...e816`; ELF: `a399e350...428ee`; simulator: `79170778...42e`.
- Known-good dynamic control after the hierarchy correction: build `b78d2603...463f`; compressed waveform `eca3294b...665`; run `872bc290...78e2`.

`invalid-stale-model-target-events.txt` is deliberately retained as rejected evidence. The first nominal 8 KiB attempt reused an October 30 simulator executable because the model cache key did not include `BP_L2_SETS`; its event trace must not be interpreted as an 8 KiB result. The accepted arms removed the simulator executable itself before rebuilding, verified fresh timestamps, checked the build define, and extracted the elaborated parameter.

## Workflow notes

Two initial directed-build attempts failed before simulation because the historical worktree-local cross compiler and specs were absent. Binding `ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install` fixed both paths. The named static build then exposed a stale timeout-reporter hierarchy path. Inspection showed both current dynamic and named models use the same `processor.u.unicore` wrapper, so the host reporter was corrected unconditionally and both configurations were rebuilt cleanly and passed. The historical test source was restored byte-for-byte to its retained late-reissue version (`d06bab7d...e7180`) after evidence capture.

The final host checks pass 15 simulator-verdict tests and all 126 discovered Linux tests. The unrelated isolated `cosim/tests/test_axi_mem_pipelined.py` suite does not build with the current repository Verilator because two existing `mem_els_p-1` width-expansion warnings are fatal; it runs zero cases and is not evidence about this configuration. Its failure was left separate rather than mixing an AXI-model cleanup into the retention candidate.

## Decision

The next bounded experiment is a routed PYNQ-Z2 implementation of the exact named 16 KiB endpoint. If it fits and meets timing, repeat the existing one-line early-data Linux A/B protocol on that bitstream. If it cannot route, raw capacity is not a practical fix on this device and the next architecture should be a small protected preview-retention structure rather than further timing changes to the existing 4 KiB L2.
