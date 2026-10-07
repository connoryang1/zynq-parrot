# Banked full-line pipeline reconstruction

This artifact reconstructs the committed banked full-line prefetch path at top
commit `03955af9`, BlackParrot commit `259b8858`, and subsystem commit
`f9762c5b`. The benchmark uses three resident threads, ten logical contexts,
ten prefetch slots, 33 dependent nodes, and the pipelined synthetic memory
model with a nominal 40-cycle address-to-first-beat delay.

Two wrappers were measured with the same ELF and guest configuration:

| Wrapper | HP0 width | Beats/line | Cycles | Installer median | Installer max |
| --- | ---: | ---: | ---: | ---: | ---: |
| `black-parrot-minimal-example` | 32 bits | 16 | 802 | 19 | 21 |
| `black-parrot-example` | 64 bits | 8 | 805 | 19 | 25 |

The 64-bit waveform accounts for 33 accepted hints, 33 issued requests, 33
AXI bursts, 264 response beats, and 33 unique tag publications. Address to
first response beat is 40 cycles for 32 of 33 requests and 47 cycles for one;
each burst then takes exactly seven cycles from first to final beat. Allocation
to tag publication has an 84-cycle median and 118-cycle maximum. One install
held an accepted tag-write handshake for two cycles, so the trace contains 34
raw tag-write handshakes but 33 unique publications. The repeated write is
idempotent in this passing workload, but it is a real contention symptom and
should not be counted as another completed line.

The near-identical 802/805 totals show that this workload is not limited by
the external beat width. Cutting each line from sixteen beats to eight saves
transport time, but cache installation and request scheduling overlap that
transport and remain on the critical path. The banked storage also does not
shorten the installer state sequence: its 32-bit distribution is exactly the
same as the earlier concurrent flat-buffer trace. The previously recorded
771-cycle result and claim that four slots preserve throughput do not reproduce:
ten slots take 802 cycles in the minimal wrapper, while the broken four-slot
path takes 2,241.

The retained four-slot waveform now explains that slowdown. All 33 intended
hint addresses reach the UCE, but only 31 allocate a slot. The hints for CPU
lines `0x8001d000` and `0x8000e700`, both issued by stream/thread 2, each make
two attempts while all four slots are occupied. Neither attempt is accepted
or counted by `prefetch_drop`; nevertheless, the hint instructions retire 4.5
cycles after their final visible attempt. The same two lines are the only
ordinary demand fills in the trace.

The minimal wrapper services each missed 64-byte line as sixteen serialized
32-bit reads. The first fallback spans 676 cycles from its first address to its
final response, and the second spans 670. Their 1,346-cycle sum accounts for
93.5% of the 1,439-cycle gap between four and ten slots. The allocation stream
has corresponding 700- and 716-cycle holes. Four slots are occupied for only
223 of 2,241 cycles (10.0%), so average saturation is not the problem: two
short capacity conflicts escape the intended replay path and trigger very
expensive serialized fallbacks. Those ordinary credits also cause four
otherwise accepted completed prefetches to enter the installer drop state;
27 of 31 accepted hints publish tags.

This changes the interpretation of the four-slot result. It demonstrates a
broken end-to-end hint-backpressure path, not that four slots are inherently
too shallow. A correct implementation must keep the hint architectural
operation from retiring until the UCE accepts it, or hold rejected hints in a
pending queue. It should also prevent a demand fallback from converting a
full-line miss into sixteen serialized word requests. Fixing either mechanism
is likely much more valuable than adding slots, although the 19-cycle installer
still limits whole-footprint Linux replay independently.

The replay/retirement bug is fixed at BlackParrot commit `d4c20786d`. The
memory pipe now carries a bit recording that a hint was suppressed because the
D-cache became busy after dispatch and turns that condition into the same
architectural replay used for a rejected cache request. The exact four-slot
workload then falls from 2,241 to 900 cycles:

| Configuration | Cycles | Accepted hints | Ordinary AXI requests | Installer drops |
| --- | ---: | ---: | ---: | ---: |
| Broken four slots, minimal 32-bit | 2,241 | 31/33 | 32 (two serialized lines) | 4 |
| Fixed three slots, minimal 32-bit | 1,106 | 33/33 | 0 | 0 |
| Fixed four slots, minimal 32-bit | 900 | 33/33 | 0 | 0 |
| Fixed five slots, minimal 32-bit | 802 | 33/33 | 0 | 0 |
| Ten-slot control, minimal 32-bit | 802 | 33/33 | 0 | 0 |
| Fixed four slots, FPGA-facing 64-bit | 905 | 33/33 | 0 | 0 |
| Fixed five slots, FPGA-facing 64-bit | 805 | 33/33 | 0 | 0 |
| Ten-slot control, FPGA-facing 64-bit | 805 | 33/33 | 0 | 0 |

The fix recovers 1,341 cycles, or 93.2% of the broken path's 1,439-cycle
excess over ten slots. The remaining 98 cycles make fixed four slots 12.2%
slower than ten slots. This is genuine queue pressure: the four slots are full
for 312 of 901 sampled cycles (34.6%), and the memory pipe records 41 replay
cycles, but every hint eventually allocates and no demand fallback occurs.
Four slots are therefore a viable small synthetic endpoint after correct
backpressure, while the larger Linux design remains limited by installation
rate and useful-before-demand timing.

The FPGA-facing wrapper independently confirms the residual's source. Fixed
four-slot execution is 905 cycles there, 100 above its 805-cycle ten-slot
control. Changing from the minimal 32-bit path to the FPGA-facing 64-bit path
changes the fixed result by only five cycles and the ten-slot result by three.
Both fixed wrappers accept 33/33 hints and issue 33 prefetch AXI requests with
no ordinary fallback. The approximately 100-cycle residual is therefore
queue/replay scheduling overhead rather than external beat width.

The fixed three-slot run locates the queue-depth knee. It completes in 1,106
cycles with all 33 hints accepted and allocated, 33 nonzero-ID prefetch line
requests, and no ordinary fallback or installer drop. The three entries are
occupied for 724 of 1,107 sampled cycles (65.4%); the memory pipe spends 90
cycles replaying hints and the D-cache contributes 74 prefetch-replay cycles.
By comparison, four slots are full for 312 of 901 samples (34.6%) and record
41 memory-pipe replay cycles. The fourth slot therefore absorbs requests while
the other three await response or installation instead of merely adding one
more simultaneous stream.

Adding that fourth slot saves 206 cycles, an 18.6% reduction from the
three-slot runtime and 67.8% of its excess over ten slots. The fifth slot saves
the remaining 98 cycles, or 10.9% of the four-slot runtime: five and ten slots
both take exactly 802 cycles. The equality survives full accounting. Five
slots accept and allocate all 33 hints, issue 33 nonzero-ID line requests, and
have no ordinary fallback or installer drop. They are full for only 74 of 803
samples (9.2%), with 35 visible hint-request cycles, 19 memory-pipe replay
cycles, and two D-cache prefetch-replay cycles.

For this exact three-stream, 40-cycle synthetic workload, five slots are the
minimum measured depth that reproduces ten-slot runtime. Three are correct but
frequently saturated, four retain a 98-cycle retry penalty, and slots six
through ten cannot improve the measured total. This is a workload-specific
queue result rather than a physical-DDR sizing rule.

The FPGA-facing 64-bit wrapper independently reproduces the five-slot knee:
four/five/ten slots take 905/805/805 cycles. Its five-slot trace accepts and
allocates all 33 hints, issues 33 nonzero-ID prefetch lines, and has no ordinary
request or installer drop. The table is full for 73 of 806 samples (9.1%),
with 34 visible hint-request cycles, 28 memory-pipe replay cycles, and one
D-cache prefetch-replay cycle. The five-slot wrapper delta is the same three
cycles as the ten-slot wrapper delta (802 to 805), confirming that the smaller
table preserves the ten-slot schedule through the FPGA-facing interface.

The exact five-slot design was subsequently routed for the PYNQ-Z2 at top
commit `4e527cad1` and BlackParrot commit `d4c20786d`. The ordinary synthesis
strategy could not fit: after optimization it required 53,448 logic LUTs on a
53,200-LUT device. Reusing the established `Flow_AreaOptimized_high` synthesis
and `Area_Explore` implementation strategies reduced the placed design to
46,349 logic LUTs (87.12%) and 49,303 total slice LUTs (92.67%). The routed
design has zero failed, unrouted, or partially routed nets and zero node
overlaps. Timing signs off with 0.263 ns setup slack and 0.021 ns hold slack,
with no failing setup or hold endpoints. Bitstream generation and local package
verification both pass; the package SHA-256 is
`07de6afb133990998135da3fc26ae70e26386cb99564a964d5b34506f67c6e5c` and
the bitstream SHA-256 is
`933777e636853c0a6e9c6cb6d068778b4a49209510d16e49226c63bcbb6793ea`.

This establishes that the simulated five-slot knee is physically implementable
at the selected 20 MHz AXI clock without deleting the late-busy replay fix. It
does not yet establish physical-DDR performance: the verified package still
needs to be loaded and the matched 2/3/4/10-stream benchmark rerun on the board.

Run `python3 analyze.py` to regenerate the minimal-wrapper `results.json`, and
`python3 analyze_main64.py` to regenerate `results-main64.json`. The retained
filtered VCDs contain only the request, response, publication, commit, and
clock signals used by the analyzers. Both traces use synthetic memory rather
than physical DDR. The 64-bit run printed guest and host pass markers before a
pre-existing Verilator DPI finalization assertion made the process exit
nonzero; the measured guest result and waveform precede that assertion.
Run `python3 analyze_queue_depth.py` to regenerate
`results-queue-depth.json` and verify the exact missing hints, fallbacks, queue
occupancy, installer drops, and ten-slot comparison. The four-slot trace also
reaches checked guest, core, and host pass markers before the same finalization
assertion.
Run `python3 analyze_queue_fix.py` to regenerate `results-queue-fix.json` from
the fixed waveform and require 33 accepted/allocated hints, 33 nonzero-ID AXI
prefetch requests, zero ordinary requests, and zero installer drops.
`python3 analyze_queue_fix_main64.py` applies the same gates to the FPGA-facing
trace and regenerates `results-queue-fix-main64.json`.
`python3 analyze_queue_fix_k3.py` regenerates `results-queue-fix-k3.json` and
verifies the three-slot point, including retry counts, occupancy, and the
three/four/ten-slot comparison.
`python3 analyze_queue_fix_k5.py` applies the same complete-accounting gates to
the five-slot point and verifies its cycle equality with the ten-slot control.
`python3 analyze_queue_fix_k5_main64.py` verifies the corresponding five-slot
equality and complete accounting through the FPGA-facing 64-bit wrapper.
