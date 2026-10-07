# Context-switch drain interlock fast-path control

BlackParrot `ee522c10c` prevents CSR 0x800 context switches from issuing while ordinary local memory work is busy or unordered. This control reruns the dedicated context-switch overhead benchmark with no pending memory work.

The exact result remains 5.13 resident cycles per switch, 9.26 nonresident cycles per switch, and a 4.13-cycle nonresident increment. Guest `CORE PASS`, host `BSG PASS`, and the maintained `VALID RUN` check all pass. The final DPI-GPIO assertion occurs after both pass markers and is the simulator harness's known teardown behavior.

This proves the interlock adds no measurable cycle to the ordinary switch fast path. It does not substitute for the pending physical-board test of the store-followed-by-switch failure. Exact revisions, command, transcript, and transcript hash are retained here.

## Store-bearing handoff control

A matched benchmark executes 256 resident and 256 nonresident handoffs in each condition. The pure/store-bearing pairs are 5.14/6.15 resident cycles and 9.14/11.15 nonresident cycles. A hot store immediately before every switch therefore adds 1.00 resident cycle and 2.01 nonresident cycles per handoff. Each delta includes both the extra store instruction and any drain wait, so it bounds rather than isolates the interlock-only cost. This shows the detector waits for actual pipeline state instead of imposing the eight-cycle software workaround on every handoff. Completion state, all store sinks, guest, host, and maintained harness checks pass.
