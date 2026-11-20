This analysis determines whether the first capture-enabled full-core replay test stopped because of a hardware/guest failure or its host trace-runtime bound. It maps the exact ELF to architectural retirement in the closed waveform. The retained timeout remains a failed/incomplete test run; forward progress does not substitute for complete test acceptance.

# Finding

The 120-second `BSG_TRACE_TIMEOUT_S` alarm expired while the guest was making normal progress through `post_replay_demand_stream()`. No RTL or benchmark-counter correction is justified by this run. Increase the host runtime allowance and repeat the exact program/model with a fresh simulated reset, retaining the native bound.

The runner's `next_pc=0x80007f10` and `expected_npc=0x80007f00` map to compressed NOPs inside the function at `0x800007c0..0x800087c0`, not a failure/status loop. The ELF contains 16,384 compressed NOPs followed by `ret`. The recorded `mcause=9`, `mepc=0x800087ca` and `mtvec=0x800087cc` identify the preceding expected supervisor ECALL and its trap handler; they do not identify the current execution point.

The streaming analyzer samples stable pre-edge values at actual `be.clk_i` rising edges, reusing the maintained `cache_overlap_vcd.rising_edges` parser rather than assuming a clock period. It finds exactly 17,900 retired instructions, matching the runner, including 15,264 instructions from the NOP stream. The last retired PC is `0x80007efe` at BE cycle 383,121. The trace ends at cycle 383,218, only 97 cycles later. Its final sixteen 1,000-cycle bins each retire 32–64 consecutive NOPs with monotonically increasing PCs; the longest commit gap anywhere in the stream is 658 cycles. This excludes a long terminal deadlock in the captured interval.

The phase-one through phase-five store instructions retire in program order; the phase-six store is not reached. Reaching this stream on the main path follows the phase-five replay accounting and target-function value checks. Neither the proposed counter-expectation failure nor a trap loop is supported by this evidence.

# Exact evidence and reproduction

`capture-on-replay-timeout-progress.json` preserves selected signal paths, phase-store retirement events, the last 128 commits, final snapshots and the final cycle bins. `timeout-analysis-hashes.json` binds the closed FST, exact ELF/NBF, parser and result. The archived ELF hashes identically to the original `riscv/bp-tests/mt_icache_replay_test.riscv` used for this diagnosis.

```sh
fst2vcd research/demand-capture-fullcore-20261120/capture-on-replay-timeout.fst \
  | python3 -B research/demand-capture-fullcore-20261120/analyze_timeout_progress.py \
    --output research/demand-capture-fullcore-20261120/capture-on-replay-timeout-progress.json
```

The fixed target has about 1,120 NOPs plus its remaining replay/fence checks after the last retirement. A 240-second retry preserves the test while giving more host-simulation margin; only its complete test-specific PASS and core/host gates can accept the new run. No FPGA result follows from this simulation diagnosis.
