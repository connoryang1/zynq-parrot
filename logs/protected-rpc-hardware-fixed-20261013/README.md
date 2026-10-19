This directory preserves the traced simulation that repairs repeat protected entry without relying on server recovery code.

# Protected RPC repeat-entry repair

The adversarial two-domain Sv39 test leaves eight NOPs and a fatal self-loop after `preturn`. Both protected calls must enter the M-installed fixed server entry, transfer four arguments and one result, return through the hardware continuation, and finish without dispatching the unreachable post-return stream.

The failure was not a generic frontend epoch leak. The second call first produced a legitimate ITLB/I-cache replay at the fixed entry, but the resident server's context NPC and per-thread CSR bookkeeping PC (APC) still held the sequential `0x200ac` saved after the previous `preturn`. The replay therefore restarted at stale state. On every accepted protected call, RTL now atomically rebinds the target's resident/logical saved NPC and writes the inactive target CSR bank's APC to the capability entry.

The accepted traced run reports direct service at 220/31 cycles first/repeated and protected hardware RPC at 90/66 cycles. The meaningful repeated comparison is 66 cycles versus RL-044's matched 109-cycle raw transport: protected RPC is 1.652x faster. Relative to the 31-cycle direct helper, raw transport adds 78 cycles and protected transport adds 35, so the hardware path removes 43/78, or 55.1%, of the raw premium.

The guest prints `[BSG-PASS] atomic protected RPC capability, fixed entry and return`, followed by guest and host PASS. Verilator then reaches the known DPI GPIO finalizer assertion after `done()`; `testing/check_run.py` classifies the transcript as valid because both PASS markers precede it.

`dispatch-check.txt` audits the complete selected-PC trace. It observes both service entries and both `preturn` executions, with zero dispatch samples at the first sequential NOP (`0x200ac`) and zero at the fatal self-loop (`0x200cc`). Thus the repeated result contains no hidden server recovery path.

## Artifacts

- `accepted-run.log`: complete accepted transcript.
- `accepted.dump.fst`: retained local waveform (ignored by Git because of size).
- `accepted.elf` and `accepted.nbf`: exact executable inputs.
- `source.c`: exact benchmark source.
- `dispatch.tsv` and `dispatch-check.txt`: selected dispatch stream and the forbidden-PC audit.
- `disassembly.txt`: exact ELF disassembly.
- `extract_rpc.c`: waveform extractor source.
- `results.json`: machine-readable measurements and checks.
- `SHA256SUMS`: hashes of retained artifacts.

Routed timing and FPGA execution remain separate acceptance gates. The prototype still supports one resident capability and depth-one return state; legacy unsafe CSRs remain enabled, and nesting, revocation, interrupt semantics, and Linux integration remain future work.
