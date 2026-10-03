# Linux futex handoff cost

This probe measures a realistic blocking ping-pong between two threads in one address space, both pinned to CPU 0. The sender publishes timing state, wakes the peer with `FUTEX_WAKE_PRIVATE`, and blocks with `FUTEX_WAIT_PRIVATE`; the receiver reads the physical cycle counter and `instret` immediately after its wait completes. Results contain 512 post-warm-up samples per direction.

| Direction | Median cycles | Median instructions | Cycles/instruction |
| --- | ---: | ---: | ---: |
| To main | 14,039 | 5,873 | 2.391 |
| To worker | 14,038 | 5,884 | 2.386 |

The interquartile cycle ranges are 10,623--14,182 and 10,594--14,220, reflecting whether the peer is fully asleep when the wake occurs. There were 14 setup/runtime minor faults and no major faults; measurement followed 64 warm-up handoffs.

The futex handoff is about 2.5x slower than the 5,496--5,595-cycle cooperative `sched_yield` handoff and retires about 2.4x as many instructions. Relative to the simulator's complete hot-ready-bitmap path, its median primitive cost is about 1,262x the 11.125-cycle resident handoff and 927x the 15.137-cycle nonresident handoff.

This supports a context-group design for application runtimes: a runtime can turn a cooperative block into a bitmap update and hardware handoff when another registered worker is ready, reserving futex/kernel entry for the case where the entire group has no runnable work or requires an external event.

The exact guest ELF SHA-256 is `e5671b8e19c30a66bcd67cc48ffe4fbb08380d5e3720e411f09d9859ecf01177`. The accepted board log SHA-256 is `a0bdbbb6c948ad8082a823a9d54e3bf60a2809ffb38b81fdbf10acacb01ad38e`. Guest SHA verification, probe PASS, exit zero, and `CORE[0] PASS` all succeeded.
