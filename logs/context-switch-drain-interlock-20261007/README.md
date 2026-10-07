# Context-switch drain interlock fast-path control

BlackParrot `ee522c10c` prevents CSR 0x800 context switches from issuing while ordinary local memory work is busy or unordered. This control reruns the dedicated context-switch overhead benchmark with no pending memory work.

The exact result remains 5.13 resident cycles per switch, 9.26 nonresident cycles per switch, and a 4.13-cycle nonresident increment. Guest `CORE PASS`, host `BSG PASS`, and the maintained `VALID RUN` check all pass. The final DPI-GPIO assertion occurs after both pass markers and is the simulator harness's known teardown behavior.

This proves the interlock adds no measurable cycle to the ordinary switch fast path. It does not substitute for the pending physical-board test of the store-followed-by-switch failure. Exact revisions, command, transcript, and transcript hash are retained here.

## Store-bearing handoff control

A matched benchmark executes 256 resident and 256 nonresident handoffs in each condition. The pure/single-store pairs are 5.14/6.15 resident cycles and 9.14/11.15 nonresident cycles. The immediately preceding RTL gives the exact same single-store numbers, proving that the interlock adds no delay after one ordinary hot store.

With four consecutive hot stores immediately before every handoff, the fixed RTL measures 12.11 resident and 16.11 nonresident cycles, or 6.97 cycles above its respective pure ring. The pre-fix RTL measures 9.14 and 14.14 cycles. The interlock therefore adds 2.97 resident and 1.97 nonresident cycles in the burst that needs protection. This is far smaller than inserting eight unconditional NOPs and occurs only while real local memory work remains. Completion state, all store sinks, guest, host, and maintained harness checks pass on both revisions.

## Pre-fix FPGA control

The exact 20 MHz pre-fix image (`a16a9532` / `4f56fba7d`, bitstream `e041ad3b...`) ran the reviewed FPGA NBF three times after an explicit overlay reload and remote hash verification. All three cycle rows are identical: 5.10/9.14 pure resident/nonresident, 6.15/11.15 after one hot store, and 9.14/14.14 after four hot stores. Every run passes benchmark state, core, host, cleanup, and bounded-runtime checks. This closely reproduces the pre-fix simulator and supplies the physical half of the pending matched-image A/B.
