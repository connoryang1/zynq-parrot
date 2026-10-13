This directory preserves the first accepted hardware-protected RPC simulation and the trace used to audit it. It also records a repeat-entry frontend limitation discovered by replacing the server's recovery branch with an unreachable self-loop.

# Hardware protected RPC checkpoint

The test runs two resident U-mode Sv39 domains with distinct address spaces. M-mode installs capability 1 with a fixed context-0 to context-1 entry; user mode then tries to replace that entry with `0x20100`. Two protected calls must still enter `server_service`, atomically copy `a0`--`a3`, return one result in `a0`, preserve private mappings, and reject invalid call and return operations.

The accepted trace reports direct service at 220/31 cycles first/repeated and protected hardware RPC at 43/71 cycles. Compared with RL-044's matched 109-cycle warm raw transport, the protected path is 1.535x faster and reduces the transport premium over the 31-cycle direct call from 78 to 40 cycles, a 48.7% reduction. The first-call number is not a cold-versus-cold speedup claim because cache and predictor state differ by execution order.

The guest prints `[BSG-PASS] atomic protected RPC capability, fixed entry and return`, followed by guest and host PASS. Verilator then aborts in the DPI GPIO final block after `done()`; `testing/check_run.py` classifies the transcript as valid because both required PASS markers precede that known shutdown assertion.

## Repeat-entry limitation

The 71-cycle repeat contains a 22-cycle recovery that the 43-cycle first call does not. After the first `preturn`, the frontend retains the sequential server PC `0x200ac`. On the second `pcall`, the fixed entry `0x20038` is dispatched, but the stale stream is subsequently observed; the server's `j server_service` at `0x200ac` redirects execution back to the authorized entry and the result remains correct.

Replacing that branch with NOP padding and an unreachable self-loop makes the second call hang at the self-loop. Experiments with a commit-time state reset, commit-gated protected redirects, a full issue-queue metadata bypass, a target-PC packet filter, and dropping the commit-cycle FE packet did not provide a correct general repair and were removed. The trace shows why a PC-only filter is insufficient: the target PC may first arrive as a legitimate I-cache-miss packet, so the design needs a redirect epoch or an explicit frontend purge/acknowledgment that covers I-cache responses, realignment, and the FE-to-BE queue.

This limitation prevents claiming that the 71-cycle repeated result is the final protected transition cost or that arbitrary server code after `preturn` is harmless. The accepted checkpoint still validates capability privilege, fixed descriptor state, atomic register transfer, protected continuation state, address-space separation, and end-to-end results for the test program.

## Artifacts

- `accepted-run.log`: complete accepted transcript.
- `accepted.dump.fst`: retained waveform.
- `accepted.elf` and `accepted.nbf`: exact executable inputs.
- `source.c`: exact benchmark source.
- `dispatch.tsv`: selected committed/dispatch PC stream extracted from the waveform.
- `disassembly.txt`: exact ELF disassembly.
- `extract_rpc.c`: waveform extractor source.
- `results.json`: machine-readable measurements and limitations.
- `SHA256SUMS`: hashes of retained binary and text evidence.
