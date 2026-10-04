# Matched Linux/context-group work scaling on physical FPGA

This experiment tests the scheduling-bypass model with useful work inside the
timed loop. One statically linked Linux process first alternates two pthreads
pinned to CPU 0 using an atomic turn word plus `sched_yield`. The same ELF then
runs the same stackless dependent-integer work function between general
ready-bitmap selections of a resident hardware context and a nonresident one.

Each row is the median of 64 windows. A window contains 64 round trips: 128
handoffs and 128 identical calls to the work function. Eight preceding windows
warm each mode. Final accumulators prove that every requested loop iteration ran
in both Linux threads and all four hardware source/peer paths.

| Work iterations | Measured work cycles/call | Linux cycles/handoff | Resident cycles/handoff | Speedup | Nonresident cycles/handoff | Speedup |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 9.11 | 5,845.87 | 29.10 | 200.89x | 34.10 | 171.43x |
| 16 | 61.11 | 5,872.18 | 81.09 | 72.42x | 86.09 | 68.21x |
| 64 | 205.11 | 6,047.21 | 225.09 | 26.87x | 230.09 | 26.28x |
| 256 | 781.11 | 6,622.46 | 801.09 | 8.27x | 806.09 | 8.22x |
| 1,024 | 3,085.11 | 9,101.23 | 3,215.37 | 2.83x | 3,219.68 | 2.83x |
| 4,096 | 12,584.44 | 18,847.50 | 12,651.69 | 1.49x | 12,654.70 | 1.49x |

The simple additive model is supported. It predicts each path by adding the
standalone incremental work cost to that path's zero-work median. Across the
five nonzero levels, observed resident speedup differs from that prediction by
at most 1.93%. At 3,085 work cycles it predicts 2.87x and observes 2.83x; at
12,584 cycles it predicts 1.46x and observes 1.49x. The paired benchmark's
additive thresholds are about 5,788 incremental cycles for at least 2x and
11,604 cycles for at least 1.5x on the resident path.

The matched zero-work Linux row is 5.42% above the earlier 5,545.5-cycle mean,
and the hardware rows are above the isolated selector result. Both differences
come from this benchmark's shared function call, loop, atomics, and timing
boundaries. The scaling comparison uses its own zero-work row for each path, so
fixed boundary costs remain consistent across work levels instead of mixing
measurement boundaries.

The resident/nonresident difference is five cycles through the first four
levels. Once useful work reaches 3,085 cycles, their total-speedup difference is
below 0.14%; at 12,584 cycles it is below 0.03%. More resident banks therefore
matter most for extremely fine-grained handoffs, while bypassing Linux remains
valuable with thousands of cycles of work between handoffs.

The accepted physical run covers 49,152 timed handoffs per path, checks the
ready word and context-private state, records zero resident retries and one
recovered nonresident-peer LR/SC failure, completes with four minor and zero
major faults, exits zero, and reaches `CORE[0] PASS`. The exact accepted ELF is
`95daa65a98151423cbcacac9655111a9e76034edaab9c9ea81c7ef2e323ad236`.
The loaded qualified bitstream is
`9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf`.

The first board attempt expired the control program's ten-minute watchdog while
uploading the uncompressed 784 KiB static ELF and never executed it. Its raw log
and status are retained as `transfer-timeout.*`. The accepted retry compressed
the transport payload, extended only the host control watchdog, power-cycled the
board, passed the 91-second readiness gate, and reloaded the exact overlay. None
of those host-side changes enter a timed guest window.

This is a compute-only scaling test. It does not claim behavior for page faults,
blocking I/O, cache-cold work, signals, or group preemption. The zero-work
hardware rows include a shared work-function call and C benchmark-loop overhead;
the isolated selector measurements remain 17.074 resident and 22.090
nonresident cycles.

Reproduce the analysis with:

```sh
python3 -B logs/linux-context-group-work-scaling-20261003/analyze.py \
  > logs/linux-context-group-work-scaling-20261003/analysis.stdout
cmp logs/linux-context-group-work-scaling-20261003/analysis.json \
  logs/linux-context-group-work-scaling-20261003/analysis.stdout
```

The ELF was built from the repository root with:

```sh
/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  -O2 -static -pthread -Wall -Wextra -Werror -ffixed-s11 \
  -mcmodel=medany -mno-relax -Wl,--no-relax \
  -march=rv64imafdc_zicsr_zifencei_zbb -mabi=lp64d \
  -DBP_NUM_THREADS=2 -DBP_NUM_CONTEXTS=10 \
  -o logs/linux-context-group-work-scaling-20261003/context_group_work_scaling \
  logs/linux-context-group-work-scaling-20261003/context_group_work_scaling.c
```
