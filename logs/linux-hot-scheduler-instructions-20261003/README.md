# Hot Linux scheduler retired-instruction breakdown

This is the retired-instruction counterpart to `logs/linux-hot-scheduler-breakdown-20261003`. Both probes use 512 post-warm-up samples, one CPU, two threads in one address space, and the same handoff structure.

| Path | Median instructions | Matched median cycles | Cycles/instruction |
| --- | ---: | ---: | ---: |
| `gettid` syscall | 256 | 623 | 2.434 |
| `sched_yield`, no user peer | 1,512 | 3,357 | 2.220 |
| Handoff to main | 2,429 | 5,595 | 2.303 |
| Handoff to worker | 2,436 | 5,496 | 2.256 |

The general yield path executes about 1,512 instructions before it transfers useful work to another user context. Selecting and transferring to the peer adds about 920.5 instructions and 2,188.5 cycles on average. The stable roughly 2.2--2.3 cycles per retired instruction across the paths shows that the 5.5k-cycle handoff is not primarily one isolated memory stall. It is a large hot instruction path with normal pipeline and cache costs layered on top.

This constrains optimization strategy. Cache restoration can lower cycles per instruction and reduce post-resume misses, but it cannot make the existing scheduler path approach tens of cycles. At an idealized one cycle per retired instruction, the measured handoff would still need roughly 2,430 cycles. Reaching the 11.1--15.1-cycle ready-bitmap hardware path therefore requires bypassing most general scheduler work through a registered context group or a similarly narrow primitive.

Using the average 5,545.5-cycle Linux handoff, the isolated speedup depends on useful work between handoffs. Replacing it with the 11.125-cycle resident bitmap path gives 6.47x total speedup when workers hand off every 1,000 useful cycles, 2.10x at 5,000 cycles, 1.55x at 10,000 cycles, and 1.14x at 40,000 cycles. These values exclude any additional benefit from avoiding post-switch cache disruption.

The exact guest ELF SHA-256 is `a1199a266dd74e9c78b744fe72d452746759e43bede46a2b4b80bd86aa1c5ec2`. The accepted `board.log` SHA-256 is `06fd6d0c782dba655dc9333d656ff9ff056030a69b7b3220cd24e528ebac148e`. The guest reported the probe PASS, exit zero, no major faults, and `CORE[0] PASS` during shutdown.
