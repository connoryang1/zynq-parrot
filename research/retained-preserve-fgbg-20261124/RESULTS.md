This file summarizes the measured results of the per-task retained-line experiment: native RTL simulation of the mechanism, and FPGA/Linux application measurements on the routed candidate. It separates mechanism evidence (simulation) from complete-application evidence (board) and records exact identities, so each number can be traced to its raw log.

# Address record/replay: larger-L2 baseline (simulation, 2026-11-26)

The address-replay design (see WORK_LOG, 2026-11-25 onward) stores line addresses instead of line data. Its storage is about 8.5 KiB: a 256-entry code table (~1.1 KiB), four 256-entry data slots (~4.4 KiB) and 2x24 fill buffers (3 KiB). The matched baseline spends that area on L2 instead. Set counts must be powers of two, so it doubles the 16 KiB simulated L2 to 32 KiB, which is more than the replay storage. Native full-core simulation, `e_bp_unicore_zynqparrot_prefetch16k_cfg`, delay 160, cycles per round (3 measured rounds after 1 warmup), runs `l2x2-*` (`run_l2x2_base.sh`):

| benchmark | 16 KiB L2, no replay | 32 KiB L2, no replay | warm reference (32 KiB) |
|---|---|---|---|
| single-direction foreground switch-in + work | 95.9k | 95.8k | 7.9k |
| single-direction background turn | 380.1k | 380.1k | — |
| ping-pong switch-in (per side) | 59.9k | 59.9k | 6.2k |
| ping-pong whole round | 600.7k | 600.6k | — |

Doubling the L2 changes nothing: each background turn (64 KiB scan plus 48 KiB of code) flushes a 32 KiB L2 as completely as a 16 KiB one. Replay on the 16 KiB L2 (fix13 RTL, BP `32d44f8df`+`1862708bc`, 24 in flight, hold, code on the direct path; runs `h13-*`/`pp13-*`):

| benchmark | trigger | switch-in | whole round | speedup vs cold |
|---|---|---|---|---|
| single-direction | wake, code then data | 30.2k | 409.4k | 1.163x |
| single-direction | wake, both lanes at once | 32.5k | 413.2k | 1.152x |
| single-direction | early, code then data | 26.4k | 411.9k | 1.156x |
| single-direction | early, both lanes at once | 16.7k | 401.2k | 1.186x |
| single-direction | wake, data only / code only | 56.1k / 85.9k | 436.2k / 463.3k | 1.091x / 1.027x |
| ping-pong | wake | 11.3k / 12.2k | 502.5k | 1.195x |
| ping-pong | early | 8.6k / 8.8k | 511.4k | 1.175x |

Earlier replay numbers (22.7k single-direction wake) came from RTL with a frontend bug that assembled instructions from unrelated fetches (WORK_LOG, 2026-11-26) and are superseded.

The fix13 numbers are unchanged on BP `d70ec851e` (fix14, runs `f14-*`). That fix stops replay replies from taking the L1 data port from an ordinary eviction (WORK_LOG, 2026-11-27). The race did not fire in these runs, so every cycle count is identical.

Demand cap (`BP_REPLAY_DEMAND_CAP`, BP `18e3e8d00`): while either cache has an ordinary miss outstanding, at most N replay reads stay in flight. Single-direction foreground / whole round, in thousands of cycles. Caps 4 and 16 use runs `c13-*`; cap 8 uses runs `f14c8-*` on fix14, because its early code-then-data cell exposed the race above:

| cap | wake, code then data | early, code then data | early, both lanes |
|---|---|---|---|
| none (24) | 30.2 / 409.4 | 26.4 / 411.9 | 16.7 / 401.2 |
| 16 | 29.7 / 408.5 | 14.6 / 401.0 | 17.2 / 402.4 |
| 8 | 23.2 / 405.7 | 22.4 / 409.1 | 23.4 / 409.6 |
| 4 | 23.3 / 408.1 | 19.6 / 404.9 | 16.3 / 400.5 |

Ping-pong whole rounds stay at 500–512k for every cap. The cap only moves cycles between the incoming and outgoing programs. The whole round stays within 400–412k, so it does not remove the outgoing program's cost, and it stays off by default.

## Replay at near-warm switch cost (BP `f5ddc8552`, 2026-11-27)

`tools/evlog_attr.py` uses a zero-perturbation event log of fills, installs, first uses and evictions. It showed that after fix14 almost every remaining foreground miss was a replayed line evicted before use. In early mode, the replay finished about 55k cycles before the switch. Pseudo-LRU then treats the replayed lines, which nothing has used yet, as old. Two installer changes close the gap: fast scan (`BP_REPLAY_FAST_SCAN`, a one-cycle duplicate scan that cuts an install from about 33 to about 17 locked cycles) and protect-until-first-use (`BP_REPLAY_PROTECT`, one bit per L1 way). Results are from runs `fp18-*` (no markers, delay 160, 3 measured rounds), with cold and warm references measured in the same build:

| benchmark | trigger | switch-in (warm) | whole round | speedup (ideal) | share of ideal gain |
|---|---|---|---|---|---|
| single-direction | early, both lanes | 9.0k (8.0k) | 387.8k | 1.228x (1.229x) | 100% |
| single-direction | early, code then data | 9.0k | 389.3k | 1.223x | 99% |
| single-direction | wake, code then data / both lanes | 13.7k / 13.5k | 393.9k / 393.1k | 1.209x / 1.212x | 93% / 94% |
| ping-pong | wake | 9.2k / 9.9k (6.5k / 6.1k) | 494.1k | 1.216x (1.217x) | 99.9% |
| ping-pong | early | 7.9k / 7.5k | 502.3k | 1.197x | 92% |

Ablation: protect alone (`p19`) reaches the same early switch-in, 9.0k. The outgoing program still pays 5–7k per turn for install lock time, and wake stays at 17.5k. Chaining back-to-back installs (`BP_REPLAY_CHAIN`, `fpc20`) brings ping-pong to 100.3% / 93.3% but leaves single-direction unchanged, so it stays optional.

Limitations, measured:
- The remaining early-mode gap, about 1k cycles, is 6 code lines per switch. They fall outside the recorded footprint, because a 258-line code footprint plus helper code exceeds the 256-entry I table.
- Wake mode installs about 370 lines inside the foreground window. At about 17 locked cycles per I install, that costs about 4.4k cycles of fetch freeze. This is the wake gap.
- Ping-pong early still charges the running side for install lock time (about 9k per round).

## Final replay configuration across memory latency (BP `8ae6263c9`)

The final configuration combines fast scan, protect, chaining (`BP_REPLAY_CHAIN`) and skipping the I-cache installer drain (`BP_REPLAY_ICACHE_NODRAIN`). Runs are `fpn21` at delay 160, and `fn100`/`fn240` with cold and warm references from the same build. All 24 runs pass. Each cell gives switch-in (warm) and the share of the ideal whole-round gain:

| benchmark / trigger | delay 100 | delay 160 | delay 240 |
|---|---|---|---|
| single-direction, early, both lanes | 8.7k (8.0k), 96% | 9.2k (8.0k), 102% | 9.4k (8.0k), 101% |
| single-direction, early, code then data | 8.8k, 99% | 8.9k, 99% | 9.5k, 105% |
| single-direction, wake | 12.1–12.2k, 91–92% | 12.4–12.6k, 90–95% | 13.2–13.4k, 96–97% |
| ping-pong, wake | 9.3k / 9.6k (6.4k / 6.1k), 99% | 8.7k / 9.2k, 102% | 8.5k / 9.1k (6.7k / 6.1k), 105% |
| ping-pong, early | 7.0k / 7.1k, 91% | 7.3k / 7.6k, 94% | 8.3k / 7.3k, 97% |

Shares above 100% mean the replay also trimmed misses the outgoing program would have taken in the off reference. With a code footprint that fits the 256-entry I table (`FG_CODE_KIB=7`, runs `fit18`, fast scan + protect), early switch-in is 8.3k vs 7.7k warm (99.5%).

# Final configuration (best measured)

Image top `7997d361c` / BlackParrot `a7b509f40`: 1536+1536 retained lines (96 KiB I + 96 KiB D) in 256 sets, per-way shadow-tag filter on both lanes, preserve-on-capture-toggle control, single-thread prefetch16k core, HP0 response delay 160 (about 200-cycle DRAM). Job `20261125T071606Z-7997d361c`: WNS +0.909 ns, WHS +0.035 ns, 49,971 LUT, 133.5/140 BRAM. Kernel29 with patch 0030 (kernel-gated capture) and the timer64 fix. Sessions `board-s15-c1536i-kgate` and `board-s16-c1536i-kgate`; whole-transaction speedup, off cells with no extra system calls:

| workload (bg 64 KiB scan) | off | I only | D only | both | fg latency (both) |
|---|---|---|---|---|---|
| scan 12 KiB | 1.00x | 1.569x [1.550, 1.709] | 1.040x [1.027, 1.053] | 1.812x [1.757, 1.846] / 1.781x [1.701, 1.855] | 2.61x / 2.59x |
| chase 32 KiB | 1.00x | 1.692x [1.648, 1.762] | 1.039x [1.005, 1.066] | 1.791x [1.737, 1.819] / 1.794x [1.752, 1.891] | 2.84x / 2.78x |
| lookup 32 KiB | 1.00x | 1.657x [1.620, 1.785] | 1.037x [1.010, 1.077] | 1.728x [1.687, 1.792] / 1.748x [1.715, 1.820] | 2.43x / 2.52x |

## Equal-area baseline (largest L2 that fits, no store)

The baseline spends BRAM on L2 capacity instead of the store: 512 L2 sets (128 KiB), no retained lines, delay 160. It's job `20261125T193733Z-d2ed33b7a`, top `d2ed33b7a`: WNS +0.591 ns, 43,492 LUT, 114.5/140 BRAM, against 133.5 for the retention image. A 256 KiB L2 would not fit. Earlier "128 KiB"/"256 KiB" images (s21/s22) were invalid, because Vivado never received `BP_ZP_L2_SETS` and they used the default 16 KiB L2 (85.5 BRAM). This baseline was checked through the effective-define line and the BRAM delta. Session `board-s26-l2-128k-baseline` runs off A/A cells, which are flat (0.997–1.016x). The comparison below is on absolute cycles per loop against the retention image's joint-k cells (s15/s16/s23–s25 medians):

| workload | 128 KiB L2 whole | retention whole | speedup | 128 KiB L2 fg latency | retention fg latency | speedup |
|---|---|---|---|---|---|---|
| scan 12 KiB, bg 64 KiB | 725k | 555k | 1.31x | 276k | 141k | 1.96x |
| chase 32 KiB, bg 64 KiB | 658k | 518k | 1.27x | 238k | 109k | 2.18x |
| lookup 32 KiB, bg 64 KiB | 667k | 542k | 1.23x | 241k | 132k | 1.82x |
| scan 12 KiB, bg 256 KiB | 1,618k | 1,520k | 1.06x | 305k | 182k | 1.68x |

The larger L2 recovers about a quarter of the off-cell time, mostly in the background and the switch path. Retention still wins clearly on foreground latency, 1.7–2.2x, and modestly on throughput. The throughput margin shrinks to 1.06x once the background no longer fits in either structure. The retention image uses 19 more BRAM tiles than this baseline, so the comparison favours the baseline's area.

Retaining the background too (`both`, s23) gives 1.884x whole [1.870, 1.918] against the same chip with retention off, the best throughput point, but foreground latency drops to 2.34x (joint 2.70x in the same boot).

## Memory-latency sensitivity (HP0 delay 300, about 340-cycle DRAM)

Same RTL and kernel, only `BP_AXI_RESPONSE_DELAY` 160 → 300. Top `03b676f3b`, job `20261125T090903Z-03b676f3b`: WNS +0.036 ns, WHS +0.023 ns, 50,057 LUT, 133.5/140 BRAM, bit `e10971e708d13edc443c71b6c6ff6ff3a8301ebbe142ab862c4dfccc5f01ee41`. Session `board-s18-c1536i-d300-kgate`. The first attempt, `board-s17`, hit the intermittent boot hang at kernel time 6 s; there was no output for 900 s, then recovery ran. The 300 delay is one point in a sweep, not the headline. About 340 cycles matches a 2–3 GHz core behind a loaded DRAM controller. 200 cycles is the conservative point.

| workload (bg 64 KiB scan) | delay | I only | D only | both | fg latency (both) | off cycles/loop |
|---|---|---|---|---|---|---|
| scan 12 KiB | 160 | 1.569x | 1.040x | 1.812x | 2.61x | 998k |
| scan 12 KiB | 300 | 2.111x [2.022, 2.147] | 1.077x [1.010, 1.101] | 2.230x [2.178, 2.402] | 3.50x | 1937k |
| chase 32 KiB | 160 | | | 1.791x | 2.84x | 915k |
| chase 32 KiB | 300 | | | 2.292x [2.244, 2.521] | 4.13x | 1836k |
| lookup 32 KiB | 160 | | | 1.728x | 2.43x | 938k |
| lookup 32 KiB | 300 | | | 2.268x [2.161, 2.403] | 3.64x | 1862k |
| scan 32 KiB | 160 | | | 1.666x | 2.00x | 1116k |
| scan 32 KiB | 300 | | | 2.127x [2.078, 2.247] | 2.71x | 2177k |

The off baseline roughly doubles, but the retained (on) configuration slows only about 1.5–1.6x, because retained hits are served from on-chip BRAM. The speedup therefore grows with memory latency. A delay-0 floor point has not been built, because of host disk space.

# Headline (1024 lines per side, kernel-gated capture)

Image top `464bfe1f4` / BlackParrot `6b3598d3d` (64 KiB I + 64 KiB D retained, 128 sets, per-way shadow filter), job `20261125T024513Z-464bfe1f4`: WNS +0.388 ns, WHS +0.036 ns, 48,383 LUT, 116.5 BRAM, bit `678eacb92acf495bc04173222e3fca360f8ac1a7144bdd7ef5c076f594e86970`. Kernel29 plus patch 0030, timer64 fix. Sessions `board-s11-c1024-kgate` and `board-s12-c1024-kgate`. Whole-transaction speedup, off cells with no extra system calls:

| workload (bg 64 KiB scan) | off | I only | D only | both |
|---|---|---|---|---|
| scan 12 KiB | 1.00x | 1.516x [1.495, 1.592] | 1.051x [1.026, 1.077] | 1.692x [1.591, 1.770] / 1.653x [1.628, 1.663] |
| chase 32 KiB | 1.00x | 1.644x [1.639, 1.752] | 1.039x [1.003, 1.078] | 1.714x [1.673, 1.771] / 1.704x [1.625, 1.746] |
| lookup 32 KiB | 1.00x | 1.623x [1.609, 1.663] | 1.033x [1.012, 1.058] | 1.671x [1.605, 1.774] / 1.649x [1.625, 1.792] |

Foreground wake-to-done latency improves 2.2–2.7x with both lanes. Foreground-size sweep (both lanes, scan): 12 KiB 1.692x, 32 KiB 1.536x, 48 KiB 1.531x, 64 KiB 1.463x. Instruction retention carries most of the gain. The retained lines are dominated by the Linux futex/scheduler switch path, which only kernel-switch-time gating captures fully.

# Capacity ceiling: 1536 lines per side (96 KiB I + 96 KiB D)

Image top `9709edeaa` (256 sets, 6-way), job `20261125T050849Z-9709edeaa`: WNS +0.726 ns, WHS +0.023 ns, 48,904 LUT, 133.5/140 BRAM (the device's BRAM limit), bit `c7b9bff89432314ebecd87ea0a83552917b358aec3e68754d6f4fcde9325fd11`. Kernel-gated, sessions `board-s13-c1536-kgate` (two cases, then an errant controller write ended it) and `board-s14-c1536-kgate`:

| workload (bg 64 KiB scan) | off | I only | D only | both | fg latency (both) |
|---|---|---|---|---|---|
| scan 12 KiB | 1.00x | 1.588x [1.563, 1.680] | 1.036x [1.015, 1.115] | 1.744x [1.715, 1.840] | 2.51x |
| chase 32 KiB | 1.00x | | | 1.793x [1.753, 1.880] | 2.92x |
| lookup 32 KiB | 1.00x | | | 1.733x [1.680, 1.799] | 2.59x |

Foreground size (both lanes, scan): 12 KiB 1.744x, 32 KiB 1.679x, 64 KiB 1.596x, 96 KiB 1.448x.

Capacity scaling (kernel-gated, both lanes, whole):

| lines per side | scan 12 KiB | chase 32 KiB | lookup 32 KiB |
|---|---|---|---|
| 768 | 1.579x | 1.624x | 1.559x |
| 1024 | 1.692x / 1.653x | 1.714x / 1.704x | 1.671x / 1.649x |
| 1536 | 1.744x | 1.793x | 1.733x |

# FPGA/Linux application results

Image: top `1eb904204` / BlackParrot `13c71ade6`, single-thread `prefetch16k` (16 KiB L2), 256+256 retained lines in 64 sets, HP0 response delay 160 (about 200-cycle DRAM latency), observer off. Routed job `20261124T201838Z-1eb904204`: WNS +0.763 ns, WHS +0.018 ns, 47,493 LUT, 94.5 BRAM. Bitstream SHA-256 `83f559229d560a62ff868f7c5d6606d008464461578b3a0fe586a687aa753553`. Linux: kernel29 with the timer64 firmware fix (NBF `5e6343cf…`), FCLK0 set to 50 MHz (core 20 MHz), controller `6caf` with the stdin EOF fix.

Benchmark: `linux-tests/scheduler_retained_fgbg_benchmark.c`. A foreground process runs one request per turn over its working set; a background process scans 64 KiB per turn; they alternate through a futex. Off and on cells issue identical `prctl` calls (mask 0 vs the policy mask), alternate in ABBA order, and are checked by checksums. Speedups are medians of per-repeat paired off/on ratios with min/max in brackets. "Whole" is the complete fg+bg transaction time; "fg latency" is background yield → foreground request complete.

Session `board-s03` (48 loops, 8 warmup, 4 repeats, fg 12 KiB):

| foreground | policy | whole | fg latency | fg request |
|---|---|---|---|---|
| scan | D only | 1.041x [1.019, 1.058] | 1.124x | 1.627x |
| scan | I only | 1.149x [1.147, 1.205] | 1.195x | 0.829x |
| scan | joint | 1.231x [1.207, 1.326] | 1.485x | 1.634x |
| chase | joint | 1.210x [1.181, 1.239] | 1.368x | 1.229x |
| lookup | joint | 1.220x [1.174, 1.255] | 1.386x | 1.065x |

Session `board-s04` (independent boot, same settings):

| foreground | policy | whole | fg latency | fg request |
|---|---|---|---|---|
| scan 12 KiB | joint (replication) | 1.243x [1.227, 1.297] | 1.487x | 1.778x |
| scan 12 KiB | I capture also during bg (`iall`) | 1.047x [1.026, 1.075] | 1.027x | 1.032x |
| scan 12 KiB | joint, I capture also during bg | 1.101x [1.085, 1.140] | 1.151x | 1.428x |
| chase 12 KiB | joint, I capture also during bg | 1.069x [1.037, 1.098] | 1.095x | 1.444x |
| parse 12 KiB | joint | 1.179x [1.175, 1.210] | 1.252x | 1.062x |
| scan 4 KiB | joint | 1.286x [1.256, 1.339] | 1.718x | 4.036x |
| scan 8 KiB | joint | 1.238x [1.211, 1.277] | 1.484x | 1.661x |
| scan 16 KiB | joint | 1.202x [1.163, 1.250] | 1.318x | 1.167x |

Per-task gating is essential on both lanes: letting the background capture instructions loses most of the gain. The gain shrinks as the foreground grows because foreground lines and captured kernel lines share the 256-line store; a 768-line-per-side candidate (top `143aa29eb`) is building for a capacity sweep.

Session `board-s05` (third boot): scan D 1.025x [1.013, 1.073], scan I 1.153x [1.126, 1.169], chase joint 1.235x [1.207, 1.342], lookup joint 1.194x [1.176, 1.220]. Background size with a 12 KiB scan foreground and joint retention: 32 KiB 1.268x [1.220, 1.356], 64 KiB 1.231/1.243x, 128 KiB 1.180x [1.146, 1.218] whole. Foreground latency stays about 1.4x; the whole-transaction gain shrinks as the background's share of time grows.

## Larger store: 768 lines per side (48 KiB I + 48 KiB D)

Image top `143aa29eb` (same RTL, 768+768 lines in 128 sets), job `20261124T231154Z-143aa29eb`: WNS +0.630 ns, WHS +0.013 ns, 48,338 LUT, 110.5 BRAM, bit `a871edc404563bff5da776738cbcc019b3ec9ab80d218424b45ca024861a7c9d`. Sessions `board-s07-c768` and `board-s08-c768` (`board-s06-c768` hit the intermittent transfer stall and recovered; no data).

| foreground (bg 64 KiB scan) | policy | whole | fg latency | fg request |
|---|---|---|---|---|
| scan 12 KiB | joint | 1.631x [1.542, 1.655] / 1.656x [1.597, 1.671] | 2.35x / 2.52x | 2.21x / 2.93x |
| scan 12 KiB | I only | 1.448x [1.377, 1.472] | 1.650x | 1.028x |
| scan 12 KiB | D only | 1.072x [1.047, 1.090] | 1.190x | 1.662x |
| scan 16 KiB | joint | 1.587x [1.557, 1.664] | 2.279x | 2.314x |
| scan 24 KiB | joint | 1.530x [1.494, 1.600] | 1.967x | 1.607x |
| scan 32 KiB | joint | 1.522x [1.447, 1.540] | 1.773x | 1.377x |
| scan 32 KiB | I only | 1.373x [1.365, 1.457] | 1.490x | 1.015x |
| scan 32 KiB | D only | 1.070x [1.057, 1.131] | 1.112x | 1.283x |
| scan 48 KiB | joint | 1.404x [1.377, 1.502] | 1.506x | 1.188x |
| chase 32 KiB | joint | 1.555x [1.510, 1.566] / 1.528x [1.513, 1.624] | 2.20x / 2.20x | 1.77x / 2.26x |
| lookup 32 KiB | joint | 1.551x [1.483, 1.627] | 2.202x | 1.813x |
| parse 32 KiB | joint | 1.441x [1.393, 1.470] | 1.483x | 1.281x |

Capacity matters even for a 12 KiB foreground (joint 1.23x → 1.63–1.66x): the store must hold the kernel switch path's code and data as well as the foreground's lines, and the instruction side carries most of the gain. A 1024-line-per-side build (top `f8dc8313e`) is next.

## Kernel-gated capture (no per-turn system calls)

Kernel patch `kernel-gate/0030-retained-owner.patch` on kernel29 (built in a copy of the kernel29 tree with the same banner; NBF SHA-256 in `kernel-gate/nbf.sha256`, with the timer64 fix). `prctl(PR_BP_RETAINED_OWNER, enable, capture)` registers the calling task. `context_switch()` writes CSR 0x5c2 with capture on when switching to the owner and capture off when switching away, without changing lane enables. Policies with `-k` register the foreground once per on cell; off cells make no extra system calls, so this is the cleaner baseline.

768-line image, session `board-s09-c768-kgate`:

| foreground (bg 64 KiB scan) | policy | whole | fg latency | fg request |
|---|---|---|---|---|
| scan 12 KiB | joint, kernel-gated | 1.579x [1.520, 1.653] | 2.180x | 1.860x |
| scan 12 KiB | joint, userspace-gated (same boot) | 1.656x [1.614, 1.734] | 2.554x | 2.484x |
| scan 12 KiB | I only, kernel-gated | 1.527x [1.502, 1.608] | 1.899x | 1.527x |
| scan 12 KiB | D only, kernel-gated | 1.031x [0.993, 1.051] | 1.068x | 1.082x |
| scan 32 KiB | joint, kernel-gated | 1.478x [1.437, 1.561] | 1.694x | 1.389x |
| chase 32 KiB | joint, kernel-gated | 1.624x [1.585, 1.647] | 2.307x | 2.236x |
| lookup 32 KiB | joint, kernel-gated | 1.559x [1.513, 1.611] | 2.186x | 2.078x |

The retained configurations run at the same absolute speed under either gating (about 620k vs 625k cycles/loop for scan 12 KiB). The userspace ratio is higher only because its off cell also pays two prctl calls per turn. Kernel gating needs no application changes and improves the instruction-only case (1.53x vs 1.45x).

For comparison, the old global always-capture policy on the deployed image measured 0.913x (D) and 0.898x (joint) on scan 32 KiB.

Interpretation (supported by the data, not separately traced): the instruction gain comes mostly from retained kernel code on the futex wake/switch path, which both tasks execute. That's why I-only improves the whole transaction more than the foreground's own request.

Known limitation: the intermittent Linux console stall (OpenSBI self-deadlock on the kernel stack pointer) also occurs on this fresh, single-thread image; session `board-s01` hit it during guest transfer. The 22-command transfer used since then has not stalled. Every accepted case completed with checksums, normal exit and `CORE PASS`.

# Native RTL simulation (mechanism)

Full black-parrot-example Verilator model, same RTL, bare metal. See `d160-*` directories.

- Foreground/background scans, delay 160: gated D capture gives 4.3–4.9x foreground speedup for 4–16 KiB, about 45 cycles per retained line vs about 211 from DRAM; the old always-capture policy gives 0.99x.
- 12 KiB code + 12 KiB data: D 1.75x, I 1.76x, joint 5.49x foreground; warm-cache ceiling 12.2x.
- Modeled kernel switch path: userspace-gated joint 1.81x, kernel-gated joint 3.68x foreground (warm ceiling 12.5x).
- The single-thread configuration is cycle-identical to the two-thread core on these programs.
- A restore walker that pushes retained lines into L1 at resume (branch `wip/retained-restore-walker-20261124`) did not help: the L1 installer needs an exclusive cache lock and drops lines whenever a demand request is resident. The I-side install path also corrupted instruction state in retained builds.
