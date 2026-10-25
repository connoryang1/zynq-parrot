This directory records a supervisor-mode translation probe for the proposed Linux data-preview hook. It separates a guest PASS and closed simulator trace from the maintained harness status so a missing registration cannot be mistaken for a hardware failure or an accepted full gate.

# S-mode SUM probe

The first clean traced `run-mt_smode_prefetch_sum_test` built and ran the new guest. It printed `[BSG-PASS] S-mode SUM-gated user-data prefetch`, `CORE PASS`, and `BSG PASS`, flushed `dump.fst`, and the simulator returned zero. The Make target nevertheless exited 2 because `testing/check_run.py` did not yet list the new test name in `TEST_MARKERS`; argparse rejected its `--test` argument. This is a harness registration mismatch, not evidence about preview issuance. The guardrail is to register a test in both the Makefile and transcript checker before treating the maintained target as accepted, then rerun the target after the correction.

## Accepted long- and short-SUM controls

The test enters S-mode with S-only code and stack mappings and a user-readable 4 KiB Sv39 data leaf. An ordinary load primes that leaf's DTLB entry. The first `prefetch.r` targets `user_data + 64` while `SUM` is set; the second targets `user_data + 128` with `SUM` clear. The test checks the three ordinary load values and traps, while the closed waveform establishes hint issue and side-buffer consumption. The source, Makefile target, and transcript checker now register the test.

After separate simulator and testing cleans, run:

```sh
make -C testing run-mt_smode_prefetch_sum_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 SIM_DEFINES='BP_DCACHE_PREFETCH_ELS=5 BP_PREFETCH_AXI_BYPASS' VERILATOR_BUILD_JOBS=8 ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install
```

The registered long-window control passed the test-specific guest marker, `CORE PASS`, `BSG PASS`, `VALID RUN`, and host exit zero. Its ELF/NBF hashes are `125b15bd4e1ce248ec735f5285ed17cbe046cdc0b2b18ac829265a14114c344c`/`84a0dbb68c3ae3de26dcd343922375fcd80d6b3ed3c9ca3565210c024365bc8b`. Its closed `registered-run.fst`/`.log` hashes are `10b3153686754bbd334969df30c9be47cd0dbc72097730893f2ce9608539296d`/`fd343aa4aad697f5c1c92743f38ef6fe958c0744b4de72c05b82f9c1cf6a7084`. `registered-wave.json` counts one preview enqueue/forward issue at physical `0x8000a040`, two 64-bit reply beats, one D-cache side-buffer hit at `0x8000a040`, and 381 ordinary request/metadata pairs; its hash is `b2ad0f569927f140bd3c035039eba8171897745fedf09c42dae48f9c07bff689`. The `SUM`-cleared line at physical `0x8000a080` did not enqueue.

The short-window variant changes the instruction order so `csrc sstatus,t0` follows the permitted `prefetch.r` immediately; `SUM` is restored only before the later demand. The ELF disassembly confirms the adjacent `ori zero,a1,1` / `csrc sstatus,t0` instructions. After separate clean commands, the same maintained test passed with guest and host markers and exit zero. Its ELF/NBF hashes are `2398dd1bedd54f53c22a52f545273dc641ad58ec58ff770ee58e263146ca9e75`/`2932ba42ff0c4787ae8ed5e1f326ca19a016713f6ddccea112330eb78f202fab`; the closed `short-window.fst`/`.log` hashes are `5dc3570801ab0372f59234d53c43eb884c64f4c4ccf28ac5b590369f7f989cd9`/`2172d4a797661e54475a674f19c5cd63e16d6974d3816d97e64fea94ebb65e7d`. `short-window-wave.json` again records one enqueue/issue and one side-buffer hit at `0x8000a040`, no request for the `SUM`-cleared line, and 381 ordinary request/metadata pairs; its hash is `a20b8b53cf5e8e485a6ebb660b3b487a7fcae5a01edb684f44e987fb176436e5`.

The known-good `run-mt_ctxtsw_smoke_test` passed after the shared `check_run.py` edit, with test-specific marker, `CORE PASS`, `BSG PASS`, `VALID RUN`, and exit zero. Its closed FST/log hashes are `01840fb3595f62d3ed63c301fe0301744c043b5709924c27e8afb64670c8fff4`/`40c9722b19486153d5a54704a9490517059fa641e2f97fcd464930a7f9298b5d`.

This proves a translated same-mm S-mode hint can issue and be consumed when its user leaf is already in the DTLB, even if `SUM` is cleared in the following instruction. BlackParrot's prefetch path intentionally drops DTLB misses without a page walk, so this result does not establish coverage after a Linux address-space switch or for a target page absent from the DTLB. No kernel registration, scheduler hook, task/mm generation handling, routed implementation of the final bounded-hint RTL, or Linux latency gain is claimed.
