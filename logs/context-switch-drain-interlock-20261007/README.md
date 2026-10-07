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

Physical A/B validation remains pending. The managed execution environment
allows board-status SSH but rejected each local-file SSH/SCP connection before
it opened, so the board still contains the explicitly verified pre-fix image;
no partial fixed package was installed.
