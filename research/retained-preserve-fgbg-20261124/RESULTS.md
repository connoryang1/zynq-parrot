This file summarizes the measured results of the per-task retained-line experiment: native RTL simulation of the mechanism, and FPGA/Linux application measurements on the routed candidate. It separates mechanism evidence (simulation) from complete-application evidence (board) and records exact identities, so each number can be traced to its raw log.

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
