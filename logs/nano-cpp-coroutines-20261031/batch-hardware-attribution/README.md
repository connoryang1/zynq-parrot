This simulator-only diagnostic attributes the N=9 matched-batch versus hardware-worker gap using architectural retirements. It keeps the exact traces, compact reports, hashes, and limits needed to distinguish executed instructions from cycles with no retirement. No FPGA was used.

# Batch versus hardware attribution

Both runs use the same Nishanov-style diagnostic ELF and NBF, differing only
in the runtime mode selector. The ELF SHA-256 is
`8166e57a54512e2ca56314db8cac4b9b5563bb3549ef5db27326a7ba8c9d8322`,
the NBF is
`c981878bf1e749f448ed9334426b78cd5008ff8e90f9ef96ec42ced6014234e2`,
and the clean trace-enabled model is
`d3f9c56ea24eeee80285ad8d6582a7f6f08dbae192050f91284a33807ba111eb`.
The model has two physical threads, ten logical contexts, ten prefetch slots,
and pipelined synthetic 200-cycle AXI reads with queue depth ten.

The analyzer selects the last of eight ordered `run_window` pairs using the
retired begin/end physical-cycle CSR PCs `0x80000ed6` and `0x80000ede`.
Boundary instructions are excluded. Its core-cycle counts exactly equal the
guest's reported measurements, and both runs pass result, checksum, guest,
core, and host checks.

| N=9 mode | Cycles | Retired instructions | No-retirement cycles | IPC | Cycles/node |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hardware worker | 3,032 | 1,883 | 1,149 | 0.621 | 30.626 |
| Matched batch | 5,920 | 4,590 | 1,330 | 0.775 | 59.798 |
| Batch minus hardware | 2,888 | 2,707 | 181 | n/a | 29.172 |

Thus 2,707 cycles, or 93.7% of the gap, correspond one-for-one to additional
retired instructions on this single-issue core. Only 181 cycles, or 6.3%, are
additional cycles without retirement. Hardware has lower IPC because its
context redirects and memory schedule create more bubbles relative to its much
smaller instruction stream; it still finishes sooner by retiring 59.0% fewer
instructions.

Disassembly plus the known 54 lower/45 upper branch outcomes accounts for the
2,707-instruction delta:

| Retired-instruction component, batch minus hardware | Instructions | Per node | Share of total cycle gap |
| --- | ---: | ---: | ---: |
| Prefetch issue/address loop versus register-resident worker path | +693 | +7.000 | 24.0% |
| Consume/update array state versus context-private registers | +1,800 | +18.182 | 62.3% |
| Loop setup, outer-step control, and publication | +229 | +2.313 | 7.9% |
| Batch wrapper advantage | -15 | -0.152 | -0.5% |
| Additional no-retirement cycles | +181 | +1.828 | 6.3% |
| **Total** | **+2,888** | **+29.172** | **100.0%** |

The main mechanism is therefore register state placement, not a mysterious
memory stall. Each hardware context retains `lower`, `length`, `checksum`, and
`node` in registers across `csrw 0x800` handoffs. The batch state machine must
load/store those arrays, walk several stack-array pointers, reload the active
worker bound, and execute separate issue and consume loops. The remaining 181
no-retirement cycles combine context redirect, pipeline, and memory-schedule
effects; this experiment does not assign those cycles more finely.

The FSTs are retained locally under `waveforms/` and covered by
`WAVEFORM_SHA256SUMS`; compact committed evidence is under `runs/`. The initial
direct launches used a `trace0` executable and are rejected as attribution
evidence, although they reproduced the timing totals. A first clean trace build
also stopped before Verilator because the worktree's RISC-V/Boost install paths
were absent; the accepted build was cleaned again and used the canonical
`/home/coyang/zynq-parrot/install` toolchain explicitly.
