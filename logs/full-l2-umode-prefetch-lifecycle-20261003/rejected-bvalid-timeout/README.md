# Rejected pre-fix run

This run reached the translated lifecycle guest marker, `CORE PASS`, and
`BSG PASS`, but the maintained checker rejected it because an AXI write-response
timeout appeared before PASS. A repeat reproduced the timeout with the same
101,299 retired instructions and 52,596 MTIME ticks.

`gp2-events.txt` is the compact GP2 transaction trace extracted from the raw
waveform. Address and data are accepted immediately. `BREADY` then rises and
`BVALID` appears only a few cycles later, proving that the modeled peripheral
did return the response. The simulation loop advanced raw RTL clocks without
resuming the host AXI coroutine, so the coroutine missed the short `BVALID`
pulse and later reported a false timeout.

The accepted sibling run services host coroutines on every simulated cycle.
It has exactly the same guest instruction and MTIME counts, passes the checker,
and has no pre-PASS timeout.
