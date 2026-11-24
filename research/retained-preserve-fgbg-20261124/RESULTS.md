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
