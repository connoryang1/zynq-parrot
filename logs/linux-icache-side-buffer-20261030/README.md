This directory records why live L1-I installation was retired and the first verified detached-buffer replacement. It contains the decisive FPGA controls plus focused and full-core simulation transcripts; no Linux speedup or physical side-buffer acceptance is claimed yet.

# Detached Linux instruction replay checkpoint

## Physical discriminator

The timing-clean atomic installer still panics with the exact one-line Linux image (`board-atomic-prefix1-panic.log`, SHA-256 `ce9e3e59...0c8d`). Changing only the replay target from scheduler line `0x8023d480` to valid, unrelated kernel-entry line `0x80200000` still corrupts `__schedule` (`board-safe-line-panic.log`, SHA-256 `87002700...a306`). Changing the configured count to zero while retaining the same firmware/table layout reaches `/bin/sh`, prints `COUNT0_SHELL_OK`, and shuts down with core/runner PASS (`board-count0-shell.log`, SHA-256 `75064f53...9f15`).

These controls rule out the original target address, queue depth, table layout, and firmware setup. Active slow-path replacement of any live instruction-cache line is the common cause.

## Detached-buffer implementation gates

- `python3 testing/rtl/run_icache_replay_buffer.py --out /dev/shm/icache-replay-buffer-r4` passes partial-line exclusion, all eight 64-bit words, and `fence.i` invalidation. Transcript SHA-256: `a2ea38ee...72933`.
- `python3 testing/rtl/run_uce_icache_side.py --out /dev/shm/uce-icache-side-r4` passes four-beat completed-line retirement with no cache-array lock or live tag/data/stat write, and cancels a partially transferred line across invalidation without stranding the UCE. Transcript SHA-256: `a6bbaadc...34f6`.
- `python3 testing/rtl/run_uce_prefetch.py --out /dev/shm/uce-prefetch-side-regression-r1` preserves the ten-slot D-cache UCE regression. Transcript SHA-256: `e0881960...aec2`.
- A clean `make -C testing run-mt_icache_replay_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=8` reaches the exact guest marker, `CORE PASS`, and host `BSG PASS`; the harness classifies the known final GPIO teardown exception as `VALID RUN`. Raw transcript SHA-256: `dee1682b...d5c`.
- The disarmed `mt_ctxtsw_smoke_test` independently reaches its exact guest marker, core PASS, and host PASS on the same clean model.

The buffer has 16 fully tagged 64-byte entries. Data is organized as eight 64-bit word banks so fetches do not multiplex every 512-bit line. An entry becomes visible only after all four 128-bit response beats arrive, ordinary MMU/cacheability checks still authorize every fetch, and an accepted instruction invalidation clears all entries.

## Remaining acceptance

The current result proves the replacement architecture in simulation, not on Linux hardware. It still requires a routed fit/timing result, a fresh-boot one-line FPGA shell gate, an enabled prefix that reaches the shell, and a matched fresh-boot replay-enabled/disabled cycle comparison.

## First route and timing repair

The first immutable route (`20261030T192527Z-4a0d49c2`, top `4a0d49c2`, BlackParrot `9d622c99e`) fit at 50,113 LUTs (94.20%) but failed signoff setup timing: WNS/TNS were -0.284/-0.879 ns over seven endpoints, while hold was clean at +0.023 ns. The farm wrapper incorrectly labelled the completed artifact PASS, so it is explicitly rejected for deployment. The critical path ended at replay beat-valid state and included a 744-load binary selected-slot net; associative allocation from the incoming UCE packet had extended an already long backend-to-frontend control path.

The repair registers advisory packets for one cycle before associative allocation. It still accepts one packet per cycle by retiring the previous packet while accepting the next. Post-change evidence is:

- focused detached buffer: four consecutive beats accepted, partial lines hidden, all eight words correct, and invalidation clears the entry (`e605c4d9...f1fea`);
- UCE instruction side: four-beat retirement, no live-array writes/lock, and fence cancellation (`a6bbaadc...34f6`);
- ten-slot D-cache prefetch regression unchanged (`e0881960...aec2`);
- clean full-core replay reaches the exact guest marker, core PASS, and host PASS (`6f244f03...43ecd`; build `48655e85...b385`).

These tests validate throughput and function, but the registered repair still needs a fresh timing-clean route before board use.
