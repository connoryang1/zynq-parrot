This directory records the fastest existing two-context RPC transport before adding hardware protection. It separates useful service work from argument/result movement and context handoff so the `pcall`/`preturn` implementation has a measured target rather than an estimate.

# Unprotected two-context RPC transport

The benchmark uses two resident U-mode contexts with different Sv39 root page tables and ASIDs. The same private VA maps to different physical pages, while one page is shared explicitly. A call carries four integer arguments and returns one result. Two different argument tuples prevent stale register state from satisfying the second call, and the final verdict checks both private pages, the shared marker, the bootstrap handshake, and unexpected traps.

This is deliberately an unprotected upper bound. The existing U-mode CSR interface lets the caller select a context, seed arbitrary registers, and switch to the target's parked PC. It does not validate a capability, force a server entry, or protect the return continuation.

The final test invokes the same timed helper addresses twice. Argument values and constant remote-register headers are prepared outside the measured region. The direct interval contains the matched service; the raw interval additionally contains the four required remote writes, call switch, result write, and return switch.

| Path | First call | Warm call |
| --- | ---: | ---: |
| Matched direct service | 224 cycles | 31 cycles |
| Existing raw context transport | 179 cycles | 109 cycles |
| Raw minus direct | -45 cycles | **78 cycles** |

The first-call comparison is not a latency target: the server code was executed during its bootstrap and was warmer than the direct helper's first service fetch. The repeated same-address comparison is the meaningful transport result. It shows that protection need not inherit the software monitor's 287-cycle warm path; the existing unprotected machinery already completes the same useful work and cross-domain round trip in 109 cycles.

The warm waveform partitions the raw 109 cycles as follows. Times are converted with 50,000 FST ticks per core cycle.

| Boundary interval | Cycles |
| --- | ---: |
| Timer read through four remote writes and call-switch dispatch | 53 |
| Call switch dispatch to first parked-server dispatch | 6 |
| Parked-server dispatch through result seed and return-switch dispatch | 44 |
| Return-switch dispatch to caller counter read | 6 |

The matched direct helper takes 31 cycles total. The four argument writes dominate the avoidable call-side work, and the separate result seed adds serialization before the return. An atomic `pcall` can read `a0`–`a3` directly, validate one descriptor, install a protected return, and launch the existing switch. An atomic `preturn` can transfer `a0` while consuming that return. The measured boundaries put a first hardware target around 45–50 warm cycles: roughly 31 useful cycles plus two approximately 6-cycle handoffs and a small descriptor/transition cost. That estimate must be validated after RTL implementation; it is not a measured hardware-protection result.

The first attempted test failed closed with `mcause=12` before server bootstrap. CSR `0x801` snapshots the writer's privilege and translation state along with the target PC; seeding it from caller U/Sv39 incorrectly made the physical bootstrap PC a caller virtual address. The corrected test seeds context 1 from M/Bare before entering the caller. `failed-umode-seed-run.log` retains this diagnosis.

`accepted-run.log` contains the test-specific marker plus guest and host PASS. `timeline-summary.tsv` records the reported boundaries, `dispatch.tsv` is the complete selected-PC extraction, and `extract_rpc.c` is the retained FST reader. `results.json` is the machine-readable summary. The local FST, ELF, and NBF hashes are retained in `SHA256SUMS`; the large FST and binaries remain local evidence rather than tracked repository content.
