This evidence reruns the Nano lookup comparison on the physical PYNQ-Z2 with the exact BlackParrot revision used by the accepted simulator study. It supersedes the performance interpretation of the older `c50b8571` FPGA run, whose overlay predates adjacent-word preservation, late-busy hint replay, and the final context-switch interlocks.

# Exact-RTL Nano FPGA comparison

## Result

Every row below is one reset-separated physical-board invocation of the same final ELF. Each lookup visits eleven useful nodes; lower bounds, checksums, step counts, the guest marker, `CORE PASS`, host `BSG PASS`, and native exit zero all pass. Lower cycles are better.

| N | Serial demand | Serial prefetch | Fixed batch | Hardware contexts | Direct C++20 coroutine |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 1,555 (70.682/node) | 878 (39.909/node) | 574 (26.091/node) | 603 (27.409/node) | 1,351 (61.409/node) |
| 3 | 2,309 (69.970/node) | 1,329 (40.273/node) | 731 (22.152/node) | 986 (29.879/node) | 1,988 (60.242/node) |
| 4 | 3,062 (69.591/node) | 1,727 (39.250/node) | 872 (19.818/node) | 1,340 (30.455/node) | 2,616 (59.455/node) |
| 5 | 3,839 (69.800/node) | 2,169 (39.436/node) | 1,039 (18.891/node) | 1,720 (31.273/node) | 3,270 (59.455/node) |

The N=5 final-image repetitions are:

| Schedule | Samples | Median cycles | Median cycles/node |
| --- | --- | ---: | ---: |
| Serial demand | 3,839 / 3,830 / 3,827 | 3,830 | 69.636 |
| Serial prefetch | 2,169 / 2,165 / 2,177 | 2,169 | 39.436 |
| Fixed batch | 1,039 / 1,035 / 1,035 | 1,035 | 18.818 |
| Hardware contexts | 1,720 / 1,720 / 1,720 | 1,720 | 31.273 |
| Direct C++20 coroutine | 3,270 / 3,270 / 3,270 | 3,270 | 59.455 |
| Switch-only | 751 / 751 / 751 | 751 | 12.517 per complete handoff |

Thus batch and hardware beat both serial controls at every tested N. At N=5, batch is 1.662x faster than hardware, hardware is 1.261x faster than serial prefetch and 2.227x faster than serial demand, and hardware is 1.901x faster than the direct coroutine. N=2 minimizes hardware cycles/node because both contexts are resident; larger N improves the explicit batch while adding nonresident hardware handoffs.

## Cycle attribution

A separately compiled `NANO_PREWARM_MEASURED` diagnostic makes the measured paths resident before executing the unchanged timed body at N=5:

| Schedule | Cold cycles | Prewarmed cycles | Cold minus prewarmed |
| --- | ---: | ---: | ---: |
| Serial prefetch | 2,169 | 1,356 | 813 |
| Fixed batch | 1,039 | 1,035 | 4 |
| Hardware contexts | 1,720 | 1,721 | -1 |
| Direct coroutine | 3,270 | 3,270 | 0 |

Batch, hardware, and the coroutine therefore hide the physical memory latency; serial prefetch exposes about 14.8 cycles per useful node. The hardware switch-only control performs 60 complete handoffs in 751 cycles, or 12.517 cycles per handoff. Hardware minus switch-only is 969 cycles, close to the 1,035-cycle batch total; this is a descriptive bound rather than a mechanical subtraction because switching and memory work overlap.

A separate `NANO_DIAGNOSTIC_INSTRET` build partitions the single-context modes. Its extra counter instructions move totals by at most five cycles:

| Schedule | Diagnostic cycles | Retired instructions | No-retirement cycles |
| --- | ---: | ---: | ---: |
| Fixed batch | 1,040 | 896 | 144 |
| Serial prefetch | 2,177 | 1,108 | 1,069 |
| Direct coroutine | 3,275 | 3,018 | 257 |

The direct coroutine is consequently instruction-bound, not failing to interleave memory: it retires 54.9 instructions/node versus 16.3 for batch. Moving `half`/`middle` computation after resumption and bypassing the checked terminal FIFO reduce the exact-overlay N=5 direct coroutine from 3,502 to 3,270 cycles, but compiler-generated frame/state transitions remain too expensive to beat the 39.4-cycle serial-prefetch path on this core.

## Why the earlier FPGA result was wrong for the final RTL

The older qualified overlay used BlackParrot `c50b85719863443ba69de1bc2fd6575ca0b9e0a7`. The exact simulator and this overlay use `6c79a42107a3857e63b6f47bc2468fe4599c5bff`, which adds, among other changes:

- `4f56fba7d`: preserve the unconsumed adjacent 8-byte word of a 16-byte hint;
- `d4c20786d`: replay hints suppressed by a late cache-busy condition;
- `ee522c10c` and `6c79a4210`: drain and settle context-switch boundaries correctly.

On the stale ten-slot overlay, N=5 demand/prefetch/batch/hardware/direct-coroutine took 3,829/2,667/3,920/4,341/5,280 cycles. Demand is unchanged on the exact overlay, while batch and hardware fall to 1,035 and 1,720 median cycles. The previous 60--80 cycle/node interleaved result was therefore a stale-RTL artifact, not the cost of correctly operating hardware contexts.

## Identities and limits

- Routed top / BlackParrot: `65f30750705c94aba27125ba764c0aa3cc4ddc98` / `6c79a42107a3857e63b6f47bc2468fe4599c5bff`.
- Static configuration: `e_bp_unicore_zynqparrot_prefetch5_cfg`, two resident banks, ten logical contexts, five detached-prefetch slots.
- Package / bitstream SHA-256: `3cd8592cbfd53baa9824c720e8a71fe0668ca0f176a0d0498a998e62194d71b9` / `8f703740dd235940ed09f15bf13e33032b7a54ceb79d2ade5a880c169b91cc13`.
- Routed timing: WNS/TNS `+0.431/0 ns`, WHS/THS `+0.025/0 ns`.
- Utilization: 50,125 LUTs, 28,002 registers, 85.5 BRAM tiles, and 11 DSPs.
- Final normal ELF SHA-256: `30567bad4c1bae114cca49ed4f0efb3f5a77d86150aa639708f40c1ac473f658`.
- Board runner SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.

The retained final ELF and disassembly pin the code actually run. The two accounting flags are disabled in every headline image. A later default-Makefile rebuild used a different installed startup object, so whole-ELF byte identity is not claimed; the benchmark coroutine actors, direct scheduler, and timed-window functions retain the same sizes. `SHA256SUMS` covers the retained ELF, disassembly, base NBF, selector-patched images, identities, results, and raw transcripts.

This route has only five prefetch slots, so N=2--5 is the capacity-qualified sweep. It proves the expected physical ordering and explains the old reversal, but an exact ten-slot route is still required before replacing the previous N=6--10 platform rows. No physical AXI waveform was collected; hot/cold timing, `instret`, switch-only, and the exact-RTL A/B account for the observed totals without assigning individual no-retirement cycles to a specific downstream bus stage.
