This experiment adds a table-free demand-populated control for the existing 32-entry instruction replay store. It copies completed cached demand refill beats into the same physical storage without issuing speculative reads, so future workload measurements can distinguish extra retained capacity from replay traffic. The feature is disabled by default and has standalone traced simulation evidence only; it is not an accepted FPGA optimization or a measured speedup.

# Exact source and mechanism

BlackParrot branch `experiment/demand-retained-resume-capacity`, commit `ffc9bd764`, starts at accepted `684e5d8bc`. Only `bp_fe_icache.sv`, `bp_fe_top.sv`, and `bp_uce.sv` changed in that commit.

The new `replay_buffer_demand_capture_p` parameter defaults to zero. Full-design opt-in uses `BP_ICACHE_REPLAY_DEMAND_CAPTURE` at the existing FE cache instance. A request token qualifies only an accepted ordinary cached miss; uncached replies and unsolicited writes cannot train the store. Capture observes `data_mem_pkt_yumi_o` rather than changing it, so SRAM arbitration remains in charge. Normal UCE refill write packets now include the physical address already used to derive their ordinary tag/index.

An accepted first demand beat starts a fresh publication epoch. This is independent of beat zero: the normal reverse pump returns critical-first wrapped sequences, such as 2,3,0,1. Every beat must belong to the new epoch before the line can hit. An abort suppresses both new capture beats and a demand beat already pending in the registered publication stage. Accepted `fence.i` retains its existing priority over the buffer valid bits and pending packet.

Captured lines use the unchanged four-bank/eight-way allocation and replacement policy and remain duplicates of ordinary cache contents until that ordinary copy is displaced. Cache/MMU hit priority, permission/translation checks, uncached bypass and architectural SRAM writes are unchanged. The opt-in is restricted to the noncoherent instruction replay store.

This **all-demand admission policy differs from a selected-prefix retention policy**. Same physical capacity alone does not match contents or replacement behavior; a workload comparison must preserve that distinction. It may reduce speculative traffic, replace useful selected lines with irrelevant demand history, or do nothing when ordinary cache contents survive. No performance assumption is accepted here.

# Directed validation

Run from the top worktree:

```sh
python3 testing/rtl/run_icache_demand_capture.py \
  --out research/demand-capture-20261120-final
MAKEFLAGS=VM_PARALLEL_BUILDS=0 python3 testing/rtl/run_icache_replay_buffer.py \
  --out research/demand-capture-default-replay-20261120
MAKEFLAGS=VM_PARALLEL_BUILDS=0 python3 testing/rtl/run_uce_icache_replay.py \
  --side-buffer --out research/demand-capture-uce-side-confirmed-20261120
MAKEFLAGS=VM_PARALLEL_BUILDS=0 python3 testing/rtl/run_uce_icache_replay.py \
  --out research/demand-capture-uce-installer-confirmed-20261120
```

The demand test cleanly elaborates both parameter zero and parameter one with exactly 32 replay entries. Both pass:

- All eight ordinary SRAM execution words match the refill input.
- Only the enabled control learns from ordinary cached fills with no replay controller, address table or trigger.
- After clearing only the ordinary tags, enabled captured data execute correctly while the disabled control emits an ordinary miss.
- Four accepted 128-bit beats, including critical-first 2,3,0,1, publish only when the whole line is present.
- A final beat held valid while a frontend SRAM read denies its handshake does not publish until accepted.
- Aborted partial fills remain invisible, and a new rotated refill cannot combine stale partial-generation beats.
- Abort between final SRAM acceptance and registered side publication suppresses that pending publication.
- Uncached responses and writes without an accepted cached request do not train capture.
- Accepted fence invalidates the captured copy; the existing replay register also cannot republish a pending beat across that same fence.
- Thirty-two learned entries fit, while a thirty-third replaces only the expected bank entry.

`disabled/` and `enabled/` each retain `build-command.json`, build/run logs, a closed FST and `verification.json` with exact source/dependency and executable/trace hashes. Generated C++ models and object files are ignored through `research/.gitignore`; they are reproducible build outputs, not acceptance evidence.

The unchanged replay-buffer regression passes partial-line exclusion, residency queries, streaming fill, execution-word selection, fence invalidation, 32-entry capacity and same-bank replacement. The UCE test additionally checks all eight ordinary response-beat physical addresses across aligned and unaligned-request normal fills, before its existing detached replay tests. UCE final run manifests separately bind the exact latest test stimulus and RTL. These are standalone protocol gates, not full-core, FPGA timing/area or Linux execution acceptance.

# Harness corrections and retained failures

The first new wrapper copied the older replay-only test's two-way geometry, which has 256-bit SRAM banks and 128-bit fills. That geometry cannot perform the ordinary refill being tested: the fill-to-bank expansion width becomes zero. The capture-disabled ordinary-word check failed, so this was identified before attributing behavior to the feature. `../demand-capture-20261120/disabled/` retains that excluded build/run/FST; the corrected wrapper uses the real eight-way, 64-bit-bank geometry.

The next disabled run passed ordinary execution, eviction, rotation, stalls and aborts but failed its post-fence main-cache miss check. The synthetic wrapper had declared a fence complete without sweeping the ordinary tags, which the old replay-only test had never populated. The corrected wrapper now performs the four-set ordinary tag/stat invalidation sweep before completion. The original failure remains in `../demand-capture-20261120-correct-geometry/disabled/`, including a separate diagnostic FST. Neither failed run is feature evidence.

Verilator precompiled headers consumed about 105 MiB per initial build on the nearly full host disk. Only those disposable generated `.gch` files were removed; source, executable, logs and closed traces were preserved. The new demand runner passes `VM_PARALLEL_BUILDS=0` explicitly to avoid those headers; the older directed runners receive the same Make setting through the environment. This changes host build packaging, not simulated behavior.

Canonical nested `.git` files were verified before reusing `external/basejump_stl`, `external/HardFloat` and `external/bedrock`, whose revisions match the recorded gitlinks exactly. The uninitialized Linux source worktree's nested directories initially caused read-only `git rev-parse` to discover the parent repository; that output was rejected. Local dependency symlinks used for the directed builds were explicitly excluded from the RTL commit. After the coordinator's full-model source elaboration completed, each symlink was replaced with a proper clean local Git worktree at its exact recorded revision; all recorded directed-test input hashes remain unchanged, and the BlackParrot worktree is clean at `ffc9bd764`.

The added UCE unaligned-request stimulus initially rotated its wire data according to the request offset and failed the legacy installer's data check. The pump's actual `widest_beat_size` mask is one whole line in this wrapper: the response starts at aligned beat zero, while the requested sector is marked critical separately. Restoring aligned wire payload order fixes that stimulus; the failed run remains in `../demand-capture-uce-installer-final-20261120/`. The direct cache unit's 2,3,0,1 packet test is a generic publication-order stress, not evidence that this exact UCE configuration emits that rotation.
