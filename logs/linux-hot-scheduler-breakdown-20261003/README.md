This experiment decomposes the hot Linux `sched_yield` handoff floor on the exact qualified BlackParrot FPGA image. It distinguishes syscall entry and exit, scheduler work with no competing user thread, and a verified same-address-space handoff between two CPU-pinned threads.

# Hot Linux scheduler baseline decomposition

The FPGA image is top `680cdf149f003a808bb9322c334f1d039af89a66`, BlackParrot `518d2fca78d5cf6aaa68af717e2a3b2ba7be936f`, and bitstream SHA-256 `b8742813c52ac980eca34a2eaab4779adac605e3c90bf7c3819f1cd162460de4`. The Linux shell NBF SHA-256 is `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`; the probe ELF SHA-256 is `8525add026c7a19b7be7512b1d96bc07300ca71d579413c1f2d7a33acbad1fd1`.

Each condition has 512 recorded physical-cycle samples after 64 warmups. The task was pinned to CPU 0. The no-peer yield phase ran before the second user thread existed; an occasional kernel task or interrupt is still possible, so the median is the meaningful bound.

| Measured path | Median cycles |
| --- | ---: |
| Two physical counter reads | 1 |
| `gettid` syscall | 623 |
| `sched_yield` with no competing user thread | 3,357 |
| Verified handoff to main | 5,595 |
| Verified handoff to worker | 5,496 |

After the one-cycle measurement cost, a minimal syscall costs about 622 cycles. Entering the yield scheduler path adds another 2,734 cycles even without another runnable user thread. Selecting and switching to the alternate same-mm thread adds 2,238 cycles toward main and 2,139 toward worker. Independent 100,000-resample bootstrap intervals for the latter differences are recorded in `analysis.json`.

These differences bound subsystems rather than attributing individual kernel instructions. In particular, the handoff delta includes task selection, `switch_to`, and returning through the alternate thread. A faster architectural register swap can remove at most this roughly 2.2k-cycle portion from the ordinary `sched_yield` path; it cannot remove the roughly 3.36k cycles already present in a no-peer yield.

The result supports a two-level design. Linux should schedule and account for a registered context group at coarse granularity, while a userspace instruction or hardware stall event selects a ready hardware context inside that group without entering Linux. Linux remains responsible for time slices, page faults, blocking I/O, signals, migration, and cases where no registered context is ready. This can make frequent cooperative or latency-hiding handoffs redundant as Linux context switches, while a small kernel-only `switch_to` optimization cannot.

The run passed guest ELF hash verification, the probe marker, process exit zero, 13 minor faults within the bound of 16, zero major faults, and `CORE[0] PASS`. The guest then powered off cleanly; the physical board was powered down after evidence collection.
