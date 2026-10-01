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

The nominal four-resident candidate failed PYNQ-Z2 detail placement in job
`20261001T022140Z-b994f1bf`. Synthesis reported 56,937 slice LUTs against
53,200 available. After physical LUT combining, 57,993 combined LUTs and
1,527 control sets required 11,947 slices, while only 11,191 were available.
The candidate was therefore 756 available slices over the packing limit and
never reached routing or timing analysis. The later define-propagation audit
described below shows that this job also compiled the narrow path despite its
full-line endpoint name; it is evidence about four resident banks, not an FPGA
full-line implementation.

The nominal three-resident full-line endpoint failed detail placement by 17
slices: job `20261001T033357Z-f89a76dd` needed 11,230 slices with 11,213
available. `Area_ExploreWithRemap` and `Area_ExploreSequential` retries on the
same synthesized checkpoint were worse at 11,500 and 11,360 required slices.
A later narrow-endpoint build, `20261001T063657Z-f05fb1e1`, produced the exact
same synthesis checksum (`ca95e229`), utilization, control-set count, and
17-slice failure. This exposed a build-plumbing error: Make exported
`BP_PREFETCH_FULL_LINE` into Tcl, but the IP-packaging flow did not attach it
to the BlackParrot source fileset. The earlier FPGA job therefore built the
narrow path despite its endpoint name. The simulator ablation remains valid
because Verilator receives the define directly; no FPGA full-line fit claim
is retained.

## Three-resident narrow-path candidate

The optimized 16-byte side-buffer path benefits directly from the added
resident bank. With the same pipelined 40-cycle memory model and 120 nodes,
serial narrow prefetch takes 6,827 cycles while three-resident hardware
switching takes 2,292 cycles, a 2.98x speedup. The hardware result is 19.10
cycles per node versus 56.89 cycles per node for serial prefetch.

A closed 33-node trace measures 697 cycles. It contains 33 accepted hints,
33 UCE reads, and 33 AXI reads, reaches three outstanding requests at both
interfaces, and has no ordinary fallback reads. All 36 committed resident
switches reach the first target-context dispatch in two cycles. This shows
that the third resident context supplies useful memory overlap without
lengthening the resident handoff in simulation. It also shows why the narrow
side buffer should remain in the performance endpoint: the corresponding
three-resident full-line result is 4,455 cycles for 120 nodes.

The trace and machine-readable audit are retained locally under
`reverted-no-fe-fifo/trace-k3-m3-t3-lat40-narrow/`. The exact narrow FPGA
endpoint fails placement by 17 slices, so the third resident bank does not fit
in the current PYNQ-Z2 design. It never reaches routing or timing analysis, and
no clock-frequency preservation claim is made.

## Concurrent fill-buffer installation

The retained implementation gives every outstanding full-line request its own
64-byte response buffer and forwards the requested 16-byte sector to the
D-cache as soon as those two response beats arrive. Complete lines drain
through the existing L1 victim-selection and write path in the background.
Victim selection and invalidation still lock cache metadata, but the eight
data writes no longer prevent a later detached hint from being admitted or
issued. The existing SRAM handshakes arbitrate a returning critical sector or
cache access against a background fill write, so this does not add an L1 data
write port.

Buffering alone was insufficient: the first prototype took 4,505 cycles for
the 120-node, three-resident run, slightly worse than the 4,455-cycle direct
installer. Allowing new hint admission during background fill changes the
same run to 2,542 cycles. That is 1,913 cycles (42.9%) faster than direct
installation and only 250 cycles (10.9%) slower than the specialized narrow
path's 2,292 cycles. The matching serial full-line-prefetch run is 6,743
cycles, so three-stream hardware switching is 2.65x faster.

A closed 33-node trace takes 802 cycles and accounts for all work: 33 accepted
hints become 33 full-line UCE reads and 33 AXI reads, both interfaces reach
four outstanding transactions, and there are no ordinary fallback reads.
Twenty-seven of the 33 hint allocations and issues occur while the installer
is in its fill state. This directly establishes that later memory requests
overlap installation of prior lines; the improvement is not caused by omitted
nodes, early benchmark completion, or a demand fallback path.

The clean-to-dirty, same-set conflict, response-before-demand, and dirty-victim
directed cases all pass with the new buffering. The narrow 120-node control
also reproduces exactly 2,292 cycles. Trace evidence is retained under
`fill-buffer-concurrent/trace-k3-m3-n33/`. FPGA fit remains a separate gate:
ten 64-byte response buffers add storage even though the L1 keeps one physical
write port.
