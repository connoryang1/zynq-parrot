# Context-switch drain interlock fast-path control

BlackParrot `ee522c10c` prevents CSR 0x800 context switches from issuing while ordinary local memory work is busy or unordered. This control reruns the dedicated context-switch overhead benchmark with no pending memory work.

The exact result remains 5.13 resident cycles per switch, 9.26 nonresident cycles per switch, and a 4.13-cycle nonresident increment. Guest `CORE PASS`, host `BSG PASS`, and the maintained `VALID RUN` check all pass. The final DPI-GPIO assertion occurs after both pass markers and is the simulator harness's known teardown behavior.

This proves the interlock adds no measurable cycle to the ordinary switch fast path. It does not substitute for the pending physical-board test of the store-followed-by-switch failure. Exact revisions, command, transcript, and transcript hash are retained here.
