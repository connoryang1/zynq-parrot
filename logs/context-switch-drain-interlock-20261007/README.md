# Context-switch drain interlock fast-path control

BlackParrot `ee522c10c` prevents CSR 0x800 context switches from issuing while ordinary local memory work is busy or unordered. This control reruns the dedicated context-switch overhead benchmark with no pending memory work.

The exact result remains 5.13 resident cycles per switch, 9.26 nonresident cycles per switch, and a 4.13-cycle nonresident increment. Guest `CORE PASS`, host `BSG PASS`, and the maintained `VALID RUN` check all pass. The final DPI-GPIO assertion occurs after both pass markers and is the simulator harness's known teardown behavior.

This proves the interlock adds no measurable cycle to the ordinary switch fast path. It does not substitute for the pending physical-board test of the store-followed-by-switch failure. Exact revisions, command, transcript, and transcript hash are retained here.

## Store-bearing handoff control

A matched benchmark executes 256 resident and 256 nonresident handoffs in each condition. The pure/single-store pairs are 5.14/6.15 resident cycles and 9.14/11.15 nonresident cycles. The immediately preceding RTL gives the exact same single-store numbers, proving that the interlock adds no delay after one ordinary hot store.

With four consecutive hot stores immediately before every handoff, the fixed RTL measures 12.11 resident and 16.11 nonresident cycles, or 6.97 cycles above its respective pure ring. The pre-fix RTL measures 9.14 and 14.14 cycles. The interlock therefore adds 2.97 resident and 1.97 nonresident cycles in the burst that needs protection. This is far smaller than inserting eight unconditional NOPs and occurs only while real local memory work remains. Completion state, all store sinks, guest, host, and maintained harness checks pass on both revisions.

## Pre-fix FPGA control

The exact 20 MHz pre-fix image (`a16a9532` / `4f56fba7d`, bitstream
`e041ad3bcc0b2619c348e4bf19ea209a628586fe8bc5b839e95535d01215512b`)
ran the reviewed FPGA NBF three times after an explicit overlay reload and
remote hash verification. All three cycle rows are identical: 5.10/9.14 pure
resident/nonresident, 6.15/11.15 after one hot store, and 9.14/14.14 after four
hot stores. Every run passes benchmark state, core, host, cleanup, and bounded
runtime checks. This closely reproduces the pre-fix simulator and supplies the
physical half of the pending matched-image A/B.

Across the six pre-fix pure, single-store, and four-store resident/nonresident rows, simulation matches the FPGA exactly in five rows and differs by only 0.04 cycle in the sixth. The empirical maximum error is therefore 0.04 cycle for this benchmark. Subject to the fixed route preserving the same implementation behavior, the simulator predicts 12.11 resident and 16.11 nonresident cycles for four-store handoffs on the fixed FPGA image. This narrow empirical error is a benchmark-specific prediction interval, not a general simulator-accuracy claim.

## Fixed routed image

The exact fixed design (`c43549d3` / `ee522c10c`) synthesizes to 52,144
slice LUTs, 20 fewer than the matched pre-fix design, with unchanged counts of
27,967 registers, 85.5 BRAM tiles, and 11 DSPs. The drain interlock therefore
has no measurable storage or memory cost. Its first `Area_Explore` route was
fully routed but failed signoff at WNS/TNS `-0.377/-24.827 ns` across 166
endpoints. This exposed an artifact-only launcher bug that marked a build PASS
without checking WNS; commit `aed30e72` adds an explicit nonnegative-WNS gate,
and the job's retained status was corrected to FAIL.

Aggressive post-route physical optimization changed eight cells or nets without
adding or removing cells and recovered 0.397 ns. The final signoff is WNS/TNS
`+0.020/0 ns` and WHS/THS `+0.023/0 ns`, with all 85,104 routable nets fully
routed and zero routing errors. DRC and bit generation pass. The verified
package SHA-256 is
`a198efa2d65547a48fe620f921383ce37c43931f2e14f071c094d67a11effcbe`;
its bitstream SHA-256 is
`4106c05355a356413bdb8dbdfe3aa65dc7d6c25ca7224189cab156fc55310ba0`.
Exact reports and artifacts are retained in
`logs/fpga/20261007T085800Z-c43549d3-postroute-physopt/`.

A repeated post-route physical-optimization pass is a documented no-op once
WNS and WHS are nonnegative: Vivado skipped every optimization and reproduced
`+0.020/+0.023 ns`. An independent `AggressiveExplore` route from the identical
placed checkpoint instead reaches WNS/TNS `+0.198/0 ns` and WHS/THS
`+0.023/0 ns`, with all 85,098 routable nets complete and zero routing errors.
This raises the setup margin by 0.178 ns (9.9x) and the timing-derived ceiling
from 20.008 to 20.080 MHz without changing RTL or placement. DRC and bitgen
pass. The preferred verified package SHA-256 is
`e541d1e8994c3e3deac89c4617b313bd3dfdf5b49056e50645560c148368e3b6`;
its bitstream SHA-256 is
`9d6c4eb5e90f85ddc225c08d6fd930b1e405cf45cd15ae59e17c1356e052c29b`.
Exact reports and artifacts are retained in
`logs/fpga/20261007T131845Z-c43549d3-aggressive-route/`.

## Fixed-image physical validation

The preferred timing-clean image was staged, hash-verified, loaded, and run
against real DDR. Three store-handoff repetitions are identical. Resident
pure/single-store/four-store handoffs measure 5.10/6.15/12.11 cycles and the
nonresident cases measure 9.14/11.15/16.11 cycles. The four-store values match
the simulator prediction exactly; the only simulation-to-board difference in
the six rows is the already observed 0.04-cycle pure-resident control. This
accepts the drain interlock for the store-bearing failure it was designed to
prevent.

The interlock has a measurable sustained cost when a detached prefetch is
immediately followed by a resident switch. Fixed-image two-, three-, and
four-stream runs take 19,262, 21,823, and 22,723 cycles, versus 17,978, 21,178,
and 22,288 before the interlock. The +1,284/+645/+435-cycle pattern is
consistent with one added drain cycle per resident handoff: every handoff for
two streams, roughly half for three, and roughly one third for four. Against
the matched demand references, the fixed image still achieves 3.119x, 2.749x,
and 2.644x speedups. These are one physical sample per point; the earlier
matrix was cycle-stable, but the result is not presented as a new variance
study.

## Remaining ten-stream correctness failure

The fixed image does not pass the full zero-gap ten-stream workload. A fresh
load traps at illegal PC 0 with `ra=0`; the diagnostic state is `epc=0`,
`cause=2`, `tval=0`, `sp=0x80082fb0`, `a0=0x12978`, `a3=1`, and `a4=0`.
Fresh seven- and eight-instruction terminal-gap controls also fail, so the
interlock did not merely shift the old timing boundary by one cycle.

Three additional runs each reload and hash-verify the preferred overlay before
executing the exact zero-gap image. All three reach `CORE FAIL` at precisely
`minstret=2,348`; only the host's asynchronous starting sample varies. Two
fresh trap-reporting runs likewise reproduce `epc=0`, `cause=2`, `tval=0`,
`ra=0`, `sp=0x80082fb0`, `a3=1`, and `a4=0`, and both stop at
`minstret=2,362`. Their measured-cycle value `a0` differs by only four cycles
(`0x12979` versus `0x1297d`). The architectural endpoint is therefore
deterministic across fresh FPGA configuration and DRAM allocation, rather than
an intermittent warm-state or marginal-timing failure.

The physical controls sharply localize the trigger:

- no successor hints passes in 74,925 cycles;
- prime-only hints pass in 74,718 cycles;
- hints from logical context 4 alone fail;
- hints from five tested contexts excluding context 4 pass in 58,232 cycles.

The last pair rejects a general five-slot capacity or aggregate request-count
explanation. With only context 4 issuing hints, 64, 96, 112, and 120 nodes per
stream pass at 30,317, 55,151, 64,023, and 68,647 cycles, while 124 nodes per
stream fail. Thus the current physical boundary is between 120 and 124
context-4 iterations.

An alternating fresh-overlay repeat confirms that boundary. Two additional
120-step runs pass at 68,592 and 68,620 cycles, giving a three-sample range of
55 cycles or 0.080% with the original 68,647-cycle sample. The interleaved two
124-step runs both fail at exactly `minstret=2,552`. Pass/fail therefore follows
the four added context-4 successors independently of test order and modest DDR
runtime variation; the boundary is not a probabilistic latency threshold.

An exact retained-waveform comparison corrects the initial set analysis. The
four context-4 hint destinations still map to sets 22, 28, 32, and 12, but the
four additional iterations also execute 40 ordinary demand nodes from all ten
contexts. Two newly admitted demand nodes map directly to the saved stack
line's set 62: context 9 iteration 121 at `0x8000df80` and context 8 iteration
123 at `0x80020f80`. Both miss in the 124-step simulator. They correlate with
the physical boundary, but they do not cause the stack eviction in either
tested simulator model: the stack line has already been evicted by the earlier
`0x80014f80` request before iterations 121 and 123 execute.

The exact board NBFs pass the current simulator in 86,468 and 89,284 cycles.
They accept exactly 240 and 248 detached prefetch words, with zero cycles in
which a side-buffer write overlaps a live write-buffer entry, write-buffer
input, or write-buffer snoop match. In both traces, the saved stack line is
marked dirty, evicted once through way 1, captured with the correct saved
`ra=0x800002f6` and `s0=0xa`, and sent as an eight-word writeback. Both final
saved-`ra` loads then miss L1 and refill the correct line from backing memory;
the 120-step refill hits way 5 and the 124-step refill hits way 7. Full traces,
selected events, source, and analysis are retained under
`stack-slot-diagnostics/context4-sim-120-124/`.

A second exact 124-step run uses the pipelined AXI memory model with a fixed
40-cycle read latency and four outstanding reads. It also passes, accepts all
248 prefetch words, and evicts the saved stack line through way 1 on the same
`0x80014f80` request. Its eight accepted writeback beats are
`0, 0, 0xb4569, 0x80000c58, 0x800002f6, 0xa, 0x4d8, 0x4d8`; the epilogue then
misses and refills `ra=0x800002f6` in way 7. Memory latency and request overlap
therefore do not move the victim event to the two late set-62 demands. This
corrects the late-eviction explanation: the physical transition remains tied
to the four added iterations, but no tested simulation reproduces the stage
that loses the saved word. The latency model takes 788,788 cycles, so it is a
timing/order stress model rather than a calibrated model of the board's total
runtime. The waveform and extracted UCE events are under
`stack-slot-diagnostics/context4-axi-latency/`.

The ordinary AXI-lite adapter is single-outstanding: it cannot accept another
ordinary request until the prior read or write response can enter its
one-entry return FIFO. The prefetch bypass shares only the read-address
channel and uses distinct nonzero IDs. A deliberate ordinary write/read
reordering hole is therefore not present in this path, although a physical
status, victim-data, or memory-persistence fault remains possible.

A new isolated dirty-eviction sweep now covers every one of the 64 D-cache
sets. For each set it dirties all eight words of one line, applies sixteen
same-set misses, and reloads the target. All 64 reloads take more than ten
cycles, confirming displacement rather than a surviving cache hit, and all
512 words compare correctly in the simulator. The matching FPGA-CRT NBF passes
both simulation and the physical FPGA. On the board, `set_mask=0`,
`set62_word_mask=0`, and `slow_reload_mask=0xffffffffffffffff`: all 64 targets
were displaced and all 512 words survived. This establishes that the ordinary
routed writeback/refill path, including set 62, works without context switches
or sustained hints. The NBF, source, hashes, and result are under
`dirty-eviction-integrity/`.

Three fresh controls locate the failure after the worker and final handoff.
Successor-only hints fail while prime-only hints pass. A memory fence before
the final switch still fails. Loading `ra` from the saved stack slot twice also
returns zero twice. At the trap, `a0` already contains the measured physical
cycle delta, an operation performed only after `hardware_worker` returns; `sp`
is `0x80082fb0`, after the epilogue has reloaded the saved words and incremented
the stack pointer. The saved `ra` slot was at `0x80082fa0`. Thus the worker and
context-0 return completed, and the later `ld ra,0(sp)` supplied zero before the
final `ret`. This corrects the earlier interpretation that context 0 itself was
restored with a zero architectural `ra`.

The remaining fault is therefore a corrupted or mis-serviced stack reload
after sustained successor prefetching. The side buffer compares the complete
physical 16-byte sector address, so a simple truncated-tag alias is excluded by
RTL inspection. A diagnostic that independently suppresses each of the four
context-4 hints newly introduced between 120 and 124 iterations has been built;
board transfer remains pending. Those four successor addresses map to D-cache
sets 22, 28, 32, and 12, while the failing stack line maps to set 62. Two
ordinary demand nodes from the same four iterations do map to set 62, but the
simple and 40-cycle simulations both evict the stack line much earlier. A
physical replacement-order difference remains possible; the available traces
do not establish it.

A matched stack reporter and address matrix are hash-pinned in
`stack-slot-diagnostics/`. The preferred `recover` image preserves the original
main layout, wrapper address, stores, and execution through the first failing
load. If that load returns zero, it moves the reporting stack by 4 KiB and
prints the saved `ra`, adjacent saved `s0`, and two known caller words from the
same line. Three conventional-return variants move the saved pair by 16 bytes,
64 bytes, or 4 KiB, distinguishing sector, set, and tag dependence. A clean
simulator rebuild validates the reporter: all results pass in 23,972 cycles and
the four words are exactly `0x800003c4`, `0xa`, `0x500`, and `0x500`. This is an
instrumentation control only; the simulator still does not reproduce the
physical fault. The retained waveform further shows that the final `ra` load at
cycle 688,261 is an ordinary L1 hit in one-hot way `0x2`: `cache_load_hit=1`,
`prefetch_buffer_hit=0`, `load_req=0`, and returned data `0x800003c4`. The
adjacent saved and caller words hit the same line on the following cycles. Thus
the correct path does not consult the side buffer or DDR at the epilogue; the
physical image must diverge by losing the line, corrupting it, or selecting the
wrong L1 data/way.

The physical matrix now proves that the corruption follows D-cache set 62.
The recovery reporter reads zero for all four known words in the original
line: saved `ra`, saved `s0`, and both caller configuration words. Moving the
saved pair by 16 bytes within the line still traps at PC zero. Moving it by 4
KiB to a different tag in the same set fails twice at `minstret=2,348`, in
76,128 and 76,135 cycles. Moving it by 64 bytes into set 61 passes twice in
76,122 and 76,123 cycles. In those passing runs, `main`'s original set-62
`nodes` local still prints zero, independently confirming loss of the original
line while the relocated return-critical words survive. The set-61/set-62
split is independent of run order and changes only the wrapper's matched stack
displacement/restoration. Exact transcripts and hashes are under
`stack-slot-diagnostics/physical-matrix/`.

A focused RTL audit also excludes the dormant full-line
prefetch installer as the eviction source: `prefetch_install_begin` is tied to
zero, and the active `e_cache_data_mem_prefetch` operation is acknowledged by
the side buffer before the ordinary data-SRAM request path. It asserts no L1
data, tag, or status SRAM write. The residual fault must therefore involve the
ordinary L1/write-buffer path or FPGA-specific state corruption, rather than
prefetch replacement metadata invalidating the stack line. An
uncached or external readback remains useful if the reporter shows that the
cacheable words are zero.

The retained waveform independently checks this invariant over the measured
ten-stream traversal. The D-cache accepts exactly 2,560 detached data commands,
equal to ten streams times 128 nodes times two returned words. All 2,560 use
`e_cache_data_mem_prefetch`; it accepts zero tag commands and zero status
commands. `prefetch_install_begin` remains zero and the install state remains
idle throughout the window. The filtered VCD, analyzer, transcript, and their
hashes are retained beside the reporter waveform.

The prologue write path is equally specific. The saved `ra` store to
`0x80082fa0` and saved `s0` store to `0x80082fa8` both hit one-hot L1 way
`0x2` (way 1). Each is accepted by the write buffer and written to its SRAM
bank in the same cycle with mask `0xff`, carrying `0x800003c4` and `0xa`.
Across the complete measured window, 44 write-buffer entries drain. Four touch
other words of this stack line, but the two saved-word addresses are each
written exactly once and never after the initial pair. The passing simulator
therefore neither leaves these prologue stores pending nor overwrites them
during traversal. A physical failure still could diverge in this path; the
recovery reporter is the decisive board observation.

The preferred routed checkpoint also keeps advisory and authoritative storage
physically separate. Vivado maps the side-buffer data to 55 distributed
`RAM32M` roots in 55 distinct SLICEM locations. The D-cache maps its eight data
banks to eight `RAMB36E1` blocks, its tag array to three `RAMB36E1` blocks, and
its status array to one `RAMB18E1` block. No side-buffer storage location is
shared with an L1 primitive. This excludes synthesis merging or physical RAM
sharing as a route for a side-buffer write to modify the stack BRAM. The exact
checkpoint query, primitive inventory, locations, transcript, and hashes are
retained in `stack-slot-diagnostics/routed-storage/`.

Storage-boundary timing is not marginal on that route. The worst selected
side-buffer paths have `+14.783/+0.262 ns` setup/hold slack into the distributed
RAM and `+12.285/+1.232 ns` out. The L1 data BRAM has `+2.491/+0.196 ns` into
storage and `+36.273/+0.630 ns` out. All directions close, and none is the
design's global setup or hold critical path. A deterministic context-4 step
threshold is therefore unlikely to come from marginal timing at either memory
boundary.

A complete-calculator-drain control reused `register_seed_ready_i` for every
context switch. It passes the ten-stream simulator at 102,239 cycles versus
97,237 for the current interlock, but the simulator already passed the physical
failure. More importantly, resident single-store handoffs rise from 6.15 to
11.12 cycles and the four-store case rises from 12.11 to 14.16; nonresident
single/four-store cases rise to 15.13/18.16. The experiment was reverted. It
shows that a blanket drain is expensive and supplies no new root-cause evidence.

Matched physical mode controls now show that the failure requires the
interaction of hardware context switching and successor-prefetch traffic. The
exact ten-stream, 124-node graph passes twice in software-interleaved mode at
60,714 and 60,754 cycles, even though it retains the same graph and successor
hints. The previously measured hardware-switching/no-successor-hint control
also passes, and the one-hint/eight-dirty-victim directed test passes physically
with a zero mismatch mask. Exact NBF and transcript hashes are retained under
`stack-slot-diagnostics/physical-mode-controls/`.

Lightweight physical checkpoints narrow the race to the final context-2
interval in their schedule. Reading the set-62 saved return address at any
context-zero checkpoint from 124 through one remaining node returns
`0x80000300` and makes the run pass, proving that one recency update rescues
the line. With no earlier stack touch, the value is still correct after
contexts 0 and 1 finish their final nodes but is zero after context 2. A finer
lightweight probe first observes zero after context 2's set-7 demand to
`0x8001d1c0`; the simulator sees that demand miss and replay-hit 13 cycles
later while preserving the stack.

A matched control prevents overinterpreting that boundary. Four variants have
byte-identical `.text` and NBF memory maps differing only in a volatile stage
word. They observe at context-2 entry, after the pointer load, after the payload
load, and after publication. All four read `0x80000300` and pass in
77,127--77,193 cycles. The common stage-selection instructions suppress the
failure even when the first stack read is delayed until after publication.
Thus the set-7 load is a timing landmark, not a proven direct corruptor. The
robust result is a narrow, instruction-spacing-sensitive cross-request or
response/context-transition race; ordinary set replacement still cannot make a
set-7 demand evict set 62. Source, disassembly, exact FPGA logs, NBF hashes,
and the re-extracted simulator trace are retained under
`stack-slot-diagnostics/{stack-sentinel,final-lap-sentinel,context2-event-sentinel,matched-event-sentinel}/`.

A post-switch delay control is now board-ready without the recompilation
confound. Recompiled 0/1/2/4/8-NOP variants pass simulation in
89,284/90,480/91,691/94,103/98,924 cycles, but linker relaxation changes many
unrelated instruction words. The preferred one-bubble image instead patches
the exact failing NBF's four-byte hot-loop jump into a same-size `c.nop; c.j`
sequence. Its complete NBF diff is one 64-bit record at `0x80000580`; it passes
simulation in 90,476 cycles, a 1,192-cycle or 1.34% increase. A fresh-overlay
physical A/B against the original hash is still required to determine whether
one post-switch cycle suppresses the board-only race.

Two further single-record controls place the cycle after hint generation but
before the switch, or after the payload load but before hint generation. They
pass simulation in 90,485 and 90,486 cycles. On the FPGA, post-switch-only
recovery would identify an incoming-demand boundary, pre-switch-only recovery
would identify outgoing-hint settling, and recovery at all three placements
would show broader loop-period sensitivity.

The same exact patch on the accepted two-stream performance NBF measures
19,258 unmodified and 20,536 patched simulator cycles. The former is only four
cycles below its 19,262-cycle FPGA result; the 1,278-cycle increment equals
the exact number of non-final handoffs. A full-cost physical projection is
therefore 20,540 cycles, 6.64% slower than current hardware while retaining a
2.925x speedup over the 60,077-cycle demand baseline. This argues for a
state-conditional interlock if the physical causal matrix identifies a safe
condition narrower than every handoff.

Exact remote log paths, hashes, NBF identities, cycle values, and the step
sweep are recorded in `result.json`. The store-handoff fix is physically
accepted, while full ten-stream correctness remains rejected.
