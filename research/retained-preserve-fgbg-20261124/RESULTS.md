This file summarizes the measured results of the per-task retained-line experiment: native RTL simulation of the mechanism, and FPGA/Linux application measurements on the routed candidate. It separates mechanism evidence (simulation) from complete-application evidence (board) and records exact identities, so each number can be traced to its raw log.

# Final configuration (best measured)

Image top `7997d361c` / BlackParrot `a7b509f40`: 1536+1536 retained lines (96 KiB I + 96 KiB D) in 256 sets, per-way shadow-tag filter on both lanes, preserve-on-capture-toggle control, single-thread prefetch16k core, HP0 response delay 160 (about 200-cycle DRAM). Job `20261125T071606Z-7997d361c`: WNS +0.909 ns, WHS +0.035 ns, 49,971 LUT, 133.5/140 BRAM. Kernel29 with patch 0030 (kernel-gated capture) and the timer64 fix. Sessions `board-s15-c1536i-kgate` and `board-s16-c1536i-kgate`; whole-transaction speedup, off cells with no extra system calls:

| workload (bg 64 KiB scan) | off | I only | D only | both | fg latency (both) |
|---|---|---|---|---|---|
| scan 12 KiB | 1.00x | 1.569x [1.550, 1.709] | 1.040x [1.027, 1.053] | 1.812x [1.757, 1.846] / 1.781x [1.701, 1.855] | 2.61x / 2.59x |
| chase 32 KiB | 1.00x | 1.692x [1.648, 1.762] | 1.039x [1.005, 1.066] | 1.791x [1.737, 1.819] / 1.794x [1.752, 1.891] | 2.84x / 2.78x |
| lookup 32 KiB | 1.00x | 1.657x [1.620, 1.785] | 1.037x [1.010, 1.077] | 1.728x [1.687, 1.792] / 1.748x [1.715, 1.820] | 2.43x / 2.52x |

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
