This directory establishes the physical relationship among BlackParrot core cycles, Linux monotonic time, and timer interrupts on the accepted 18 MHz FPGA image. It preserves two terminal-complete fresh-boot calibrations plus a same-boot diagnostic that exposed an unsupported cross-process hardware-context relaunch.

# Linux timer calibration

## Root cause

The historical Linux NBF writes `1` to CLINT `mtimesel` at `0x308000`, selecting a clock made by toggling after every eight core cycles. Its rising edge therefore advances `mtime` once per 16 core cycles. The embedded device tree declares `timebase-frequency = <10000000>`, even though the accepted routed core clock is 17.998 MHz and the resulting `mtime` clock is about 1.124875 MHz. OpenSBI independently reports 50 MHz.

That mismatch makes Linux monotonic intervals about 8.89 times too small. Direct CSR `0xcc0` cycle deltas remain valid, but the mismatch also stretches the real Linux tick period by the same factor and suppresses normal timer-interrupt overhead.

`tools/patch_linux_nbf_timer.py` corrects both operational facts in one NBF: it selects the dedicated routed 8 MHz real-time clock (`mtimesel=2`) and changes the embedded DTB declaration to 8 MHz. The physically tested corrected shell NBF has SHA-256 `feb2ea6a9c25e06809b1d6f38c95276c2b5640df75d013bae9ca7059da930cb4`; it differs from the accepted historical shell NBF only in that selector write and one aligned DTB override word.

## Fresh-boot board results

Both accepted runs used bitstream SHA-256 `2ab6ec08860d07fe627ef079090a76c0604e1d6b40d4003fa9f5dd3a1fc8488b` and guest ELF SHA-256 `e62165fadea93925860848bb7642ec2a83c1d10ff38ab6404ec26b48480dcd72`. Each passed warmup, every requested sample, checksum validation, native exit zero, `[REQUEST-BENCH] PASS`, `CORE[0] PASS`, and runner exit zero.

| Fresh-boot workload | Samples | Median cycles | Median Linux time | Median cycles/time |
|---|---:|---:|---:|---:|
| 4,096 requests per stream | 64 | 860,962 | 47.934 ms | 17.958 MHz |
| 256 requests per stream, no-tick cluster | 13 | 40,368 | 2.336 ms | 17.28 MHz |
| 256 requests per stream, one-tick cluster | 48 | 60,853.5 | 3.481 ms | 17.48 MHz |

The long run's 17.958 MHz ratio is 0.22% below the routed 17.998 MHz clock. This is expected because the wall-clock interval contains the two `clock_gettime` calls while the nested cycle interval excludes them.

The short run's two main clusters are separated by 20,485.5 cycles, or 1.138 ms. We attribute that separation to one ordinary Linux timer interrupt: the kernel is configured for 250 Hz, the samples straddle the corresponding 4 ms boundaries, and the resulting model predicts the independent long run. At 18 MHz, this inferred timer service consumes about 28.46% of the core under a continuously running task, predicting a steady-state inflation of `1/(1-0.2846) = 1.398x`. The corrected 4,096-request median is 1.409x the historical 611,074.5-cycle quiet-timer median, only 0.8% above that prediction. Almost all of the cycle increase is normal Linux tick work that the old timer configuration accidentally suppressed.

## Same-boot diagnostic

The six-mode command in `all-modes-then-relaunch-stall.log` completed all 144 rows and printed `[REQUEST-BENCH] PASS`. Its medians were 1,161,444.5 cycles for Linux threads, 1,092,115.5 for batched prefetch/load, 891,949.5 for resident demand handoff, 868,273 for resident prefetch/yield/load, 809,619 for sequential assembly, and 801,847.5 for interleaved assembly.

A second benchmark process in that same boot then stalled during its first hardware-handoff warmup. The run was interrupted and the board was power-cycled, so it is retained only as diagnostic evidence after the completed six-mode prefix. The likely mechanism is that logical context 1 retained the first process's address-space CSRs while the new process reseeded only its PC and argument registers; this cross-process lifecycle case is not covered by the accepted same-process relaunch fix.

## Reproduction

Create the corrected shell image from the exact historical shell NBF:

```sh
python3 tools/patch_linux_nbf_timer.py \
  linux-tests/out/linux-shell.nbf linux-tests/out/linux-shell-timer8.nbf
sha256sum linux-tests/out/linux-shell-timer8.nbf
```

Run `python3 -m unittest tools.test_patch_linux_nbf_timer` to check that the selector and embedded DTB frequency change together. Board runs must follow the serialized runner and recovery procedure in the FPGA synthesis skill.
