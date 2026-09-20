# RTL context-switch timing breakdown

This artifact records the context-cache state timing from the exact-top,
two-resident/ten-logical worker benchmark after the demand-join RTL change.

The source run used `BENCH_MODE=2`, `DIAGNOSTIC=0`,
`BP_AXI_MEM_PIPELINED`, `BP_AXI_MEM_READ_LATENCY=200`, and ten AXI queue slots.
The guest and host checks passed at 418 measured cycles; the simulator then
reported its known nonfatal GPIO teardown assertion. The trace was decoded with
`tools/ctxtsw_vcd_stream_events.py` over the measured cycle window.

For the repeated nonresident handoffs, the context-cache FSM spends:

| State | Meaning | Cycles |
|---|---|---:|
| `wait_ctxtsw_commit` | wait for the CSR switch to retire | 3 |
| `wait_drain` | wait for the backend to drain | 2 |
| `save_restore_regs` | transfer the dirty integer state line | 2 |
| `launch_fe` | present the restored PC/context to the frontend | 1 |
| `done` | wait for frontend acceptance | 2 |

That is a ten-cycle active context-cache transaction. Between transactions,
the worker body contributes about eight idle cycles before the next switch is
accepted. The first consuming worker has an 84–85-cycle idle interval while its
detached data fill becomes visible; later workers do not repeat that stall.

This is why the 200-cycle worker result is 418 cycles rather than the old
3,645-cycle result: the old result included a duplicate full-line demand refill,
whereas the current trace shows ordinary context-cache transactions and no
matching normal refill. Further improvement requires shortening the actual
context-cache transaction or changing the schedule; an extra software barrier
was measured separately and increased the result to 491 cycles.
