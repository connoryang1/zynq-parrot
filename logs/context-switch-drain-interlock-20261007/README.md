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
board transfer remains pending. A matched no-stack return control and an
uncached readback of `0x80082fa0` are the next decisive tests: together they
separate dirty cache-line/data corruption from a wrong-address or wrong-response
load.

A complete-calculator-drain control reused `register_seed_ready_i` for every
context switch. It passes the ten-stream simulator at 102,239 cycles versus
97,237 for the current interlock, but the simulator already passed the physical
failure. More importantly, resident single-store handoffs rise from 6.15 to
11.12 cycles and the four-store case rises from 12.11 to 14.16; nonresident
single/four-store cases rise to 15.13/18.16. The experiment was reverted. It
shows that a blanket drain is expensive and supplies no new root-cause evidence.

Exact remote log paths, hashes, NBF identities, cycle values, and the step
sweep are recorded in `result.json`. The store-handoff fix is physically
accepted, while full ten-stream correctness remains rejected.
