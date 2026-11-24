This directory tests why ordinary full-line I/D retention slowed complete Linux applications, and whether a per-task retention policy with a realistic memory latency produces a defensible application speedup. It holds the diagnosis, the RTL/software changes, native full-model simulation results and the board-session driver. Simulation results here are mechanism evidence, not FPGA/Linux application results.

# Diagnosis of the accepted negative result

The accepted cohort04 scan visit and pilot (`fpga-artifacts/context-resume/kernel29-timer64-fix-20261123/{r0-scan,pilot}`) show retention *hurting* complete applications on the 32 KiB image (median WHOLE, off/on):

| workload | corpus | I-only | D-only | joint |
|---|---|---|---|---|
| scan | 32 KiB | 1.001x | 0.913x | 0.898x |
| scan | 128 KiB | 0.986x | 0.846x | 0.839x |
| lookup | 32 KiB | 0.988x | 0.953x | 0.953x |
| regex | 32 KiB | 1.003x | 0.975x | 0.975x |

The D penalty scales with corpus size at about 40 cycles per touched line. Source inspection explains why this is structural rather than a defect:

1. CSR `0x5c2` enable/capture bits are global, and every control write clears both stores (`bp_unicore_lite.sv`). "Ordinary" capture therefore records the most recent demand fills of whichever process is running. In a two-process ping-pong where each working set exceeds the 16 KiB D store, the store holds the peer's lines when a process resumes, so hits are rare. Meanwhile every miss pays a serial lookup and every fill a capture insert.
2. Software cannot keep one task's lines while another runs: a per-switch policy write would clear the store.
3. D coherence is conservative: every store instruction retires all retained lines in its set, so kernel/stack stores around a context switch collaterally erase much of the store.
4. On this board a DRAM miss costs only about 41 core cycles (the core runs at 20 MHz). A retained refill (serial tag scan, eight word reads, eight fill beats) saves little even when it hits. The native ideal-hit check interval was only 1.5% shorter (`WORK_LOG` 2026-11-22, capacity population cost).

# Changes (branch `experiment/retained-preserve-capture-20261124`)

BlackParrot (`/home/coyang/bp-retained-preserve-20261124`, from `1e7aa2fdc`):

- `bp_unicore_lite.sv`: a `0x5c2` write clears the stores only when a lane *enable* changes. Capture-only toggles preserve the payload, so the running task can capture and a background task can run with capture off. Correctness never relied on these clears: D mutations still invalidate, and cache maintenance (including `fence.i`) still clears.
- `bp_retained_line_store.sv` (D lane only): a distributed shadow of `{valid, tag}` mirrors every tag-RAM write and is a superset of epoch-valid lines. A store invalidates its set only if it may match a published line, or if any store operation or held response is in flight (unchanged conservative path). A lookup with no shadow match answers miss in one cycle instead of scanning ways.

Top (`/home/coyang/zynq-parrot-retained-preserve-20261124`, from `a44c03bb7`): default `BP_RETAINED_SETS=64` (4-way at 256 lines, so a 4 KiB-page-colored foreground working set cannot collide in a 1-way store) and `BP_AXI_RESPONSE_DELAY=160`. The latter uses the existing validated common-HP0 response delay, giving roughly 200-cycle DRAM latency: 100 ns at 2 GHz, a conventional emulation choice for a low-clock FPGA prototype. The delay applies identically to the off and on policies.

# Benchmarks

- `testing/rtl/retained_fgbg_benchmark.c`: bare-metal foreground (small set) / background (64 KiB polluter) scans under off, the old always-capture policy, and gated capture. Run with `run_native.sh <label> <delay> <sets>` on the full black-parrot-example native model (built in `/run/user/1001` because `/` is full).
- `linux-tests/scheduler_retained_fgbg_benchmark.c`: Linux futex ping-pong between a latency-critical foreground request and a background polluter. Off cells issue the same two `prctl` calls per turn with mask 0, so only the hardware policy differs. It reports whole transaction cycles, foreground request cycles and wake-to-complete latency.
- `board_session.py`: one serialized board session (power cycle, overlay, FCLK0 50 MHz, RAM-backed timer64 NBF `5e6343cf`, EOF-fixed controller `6caf`, guest transfer, cases, full recovery).

# Status

See `RESULTS.md` once measurements exist. No FPGA image with these changes has been built yet: the 32 KiB design is at 13,299/13,300 slices, and the host root filesystem currently has under 1 GB free.
