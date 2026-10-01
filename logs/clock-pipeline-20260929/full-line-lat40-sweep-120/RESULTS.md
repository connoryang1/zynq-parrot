This report evaluates context-based latency hiding without the specialized 16-byte D-cache side-buffer return path. It compares identical pointer-chasing work under a synthetic 40-cycle memory service and records which conclusions are transport-matched.

# Full-line prefetch and resident-context scaling

All rows traverse 120 nodes from the same generated graph and pass checksum,
cursor, count, guest, and host checks. Detached hints fetch complete 64-byte
lines and install them in L1. The hardware configuration provides ten request
slots and ten logical contexts; the resident-bank count varies as shown.

| Schedule | Streams | Resident banks | Cycles | Cycles/node | Versus serial full-line prefetch |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ordinary blocking demand | 2 serial partitions | 2 | 82,401 | 686.675 | — |
| Serial full-line prefetch | 2 serial partitions | 2 | 8,857 | 73.808 | 1.00x |
| Hardware switching | 2 | 2 | 5,536 | 46.133 | 1.60x |
| Hardware switching | 3 | 2 | 4,483 | 37.358 | 1.98x |
| Hardware switching | 3 | 3 | 4,455 | 37.125 | 1.99x |
| Hardware switching | 4 | 2 | 78,780 | 656.500 | 0.11x |
| Hardware switching | 4 | 4 | 3,940 | 32.833 | 2.25x |

The serial full-line-prefetch row is the primary baseline because it uses the
same detached direct-AXI transport as the interleaved hardware schedules but
waits on one dependent stream at a time. Ordinary demand traverses the legacy
blocking bridge and therefore includes a transport difference; its 82,401
cycles are a system baseline rather than isolated evidence for context
switching.

Three streams improve on two even with only two resident banks. Making the
third context resident saves only 28 cycles because its state movement is
largely hidden behind memory service in this schedule. Four streams on two
banks collapse because nonresident context-state traffic overlaps full-line
replies; the safe advisory installer drops such replies rather than delaying
ordinary traffic, and later demands fall back to the slow ordinary path. Four
resident banks remove that interaction and produce the best result.

The trace-qualified 32-node checks reinforce this interpretation. Two resident
streams take 1,532 cycles, admit 32 full-line prefetches, reach two outstanding
requests, and complete every one of 34 handoffs in two cycles. Four resident
streams take 1,146 cycles, admit the same 32 full-line prefetches, reach four
outstanding requests, issue no ordinary line read, and complete all 36
handoffs in two cycles. Neither trace contains an I-cache miss. The original
16-byte/two-resident configuration also reproduces its prior 931-cycle result,
so the selectable full-line path does not regress the default mode.

All three directed detached-response protocol cases pass in full-line mode at
the same 40-cycle setting. The static FPGA candidate is
`e_bp_unicore_zynqparrot_prefetch10_t4_full_line_cfg`; routed fit and timing are
required before treating four resident banks as a PYNQ-Z2 result.

The exact four-resident candidate failed PYNQ-Z2 detail placement in job
`20261001T022140Z-b994f1bf`. Synthesis reported 56,937 slice LUTs against
53,200 available. After physical LUT combining, 57,993 combined LUTs and
1,527 control sets required 11,947 slices, while only 11,191 were available.
The candidate was therefore 756 available slices over the packing limit and
never reached routing or timing analysis. A three-resident full-line endpoint
is the next fit experiment because its simulated handoff latency is still two
cycles and it retains the three-stream 4,455-cycle result.
