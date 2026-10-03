This experiment measures direct user-mode BlackParrot context handoffs on the same qualified FPGA image used for the Linux scheduler decomposition. It also records and fixes a logical-context-width bug in the Linux ring benchmark so the remote-register seed format matches the ten-context endpoint.

# Direct user handoff versus Linux scheduling

The exact image is top `680cdf149f003a808bb9322c334f1d039af89a66`, BlackParrot `518d2fca78d5cf6aaa68af717e2a3b2ba7be936f`, and bitstream SHA-256 `b8742813c52ac980eca34a2eaab4779adac605e3c90bf7c3819f1cd162460de4`. The Linux shell NBF SHA-256 is `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`; the final ten-context probe ELF SHA-256 is `9706d0fa29a9bee28500d6183261c88129d37ff9cf1f0f5626bcbe351c2fffea`.

The probe ran 128 aggregates of 256 handoffs for each mode, or 65,536 timed handoffs total. It retained normal Linux interrupts and validated the source context, source `s11`, target context, seeded target `s11`, peer completion count, peer syscall result, native exit zero, and `CORE[0] PASS`.

| Path | Median cycles per handoff | Linux/direct ratio, using 5,496–5,595-cycle Linux handoffs |
| --- | ---: | ---: |
| Direct resident context | 5.109 | 1,076–1,095× |
| Direct nonresident context | 9.160 | 600–611× |
| Linux same-mm thread | 5,496–5,595 | 1× |

Resident aggregates were 1,308 cycles in 127 of 128 samples. One aggregate took 68,064 cycles, consistent with asynchronous Linux work interrupting the ring; this run did not trace the interrupt. All nonresident aggregates were 2,345–2,348 cycles. The stable medians demonstrate that direct U-mode handoff already bypasses the measured 3,357-cycle no-peer scheduler floor. The isolated tail is also consistent with Linux retaining coarse preemption control.

## Configuration bug found and fixed

CSR `0x802` encodes the register address above a variable-width logical-context field. The old benchmark hardcoded `register << 41`, which is correct for four contexts because the context field is two bits wide. The qualified endpoint has ten contexts, requiring four context bits and `register << 43`.

Both the 128-sample and original seven-sample shapes reproduced the same failure before the fix: the resident peer completed every handoff and syscall but observed seeded `s11=0` instead of `0x2468ace0`. The corrected benchmark uses `testing/mt_seed.h`, is compiled with `BP_NUM_CONTEXTS=10`, and passes. The default four-context build also compiles and retains its original encoding.

This was a test-software encoding error rather than an RTL register-restoration failure. The failed transcripts are retained because they show why endpoint-specific logical-context width must be part of the userspace ABI.

## Architectural implication

The fast operation needed to make frequent Linux switches redundant already exists and works from user mode within a Linux process. The remaining implementation work is primarily control and integration: Linux must allocate and reclaim hardware-context IDs, restrict one process from targeting another process's contexts, initialize inherited architectural state, expose ready/waiting transitions, and retain responsibility for interrupts, faults, blocking I/O, accounting, and coarse time slices.

The direct ring is a hot assembly microbenchmark. It does not include runtime selection policy, readiness bookkeeping, context registration, or separate-address-space behavior; those are the next costs that a prototype context-group ABI must measure.
