This file is a short map of the accepted SRAM-backed context-switch implementation. It points to the code that defines behavior and states the limits of the current prototype; dated experiment narratives are preserved in Git.

# Context-switch architecture

BlackParrot still executes through one shared pipeline. The deployed PYNQ-Z2 configuration has two resident register banks and four software-visible logical contexts; hardware maps a logical context into a resident bank before resuming it.

## Where the state lives

- [Integer backing memory](import/black-parrot/bp_be/src/v/bp_be_context_mem.sv): private, on-chip synchronous RAM, separate from Linux DRAM and the coherent data cache. Integer writes update the backing image; nonresident restore reads wide lines.
- [Resident register banks](import/black-parrot/bp_be/src/v/bp_be_regfile_mt.sv): operand-read storage and line installation. Increasing logical capacity costs backing memory and metadata, even when the resident-bank count stays fixed.
- [CSR ownership](import/black-parrot/bp_be/src/v/bp_be_csr_wrapper_mt.sv): per-bank control state. The accepted fix restores the target's architectural replay PC rather than inheriting the victim's.
- [Scheduler](import/black-parrot/bp_be/src/v/bp_be_checker/bp_be_scheduler.sv) and frontend logic: serialize architectural handoff, preserve thread identity, and cancel speculative work when an older trap wins.

Inline comments and the RTL are authoritative for protocol details. Do not treat an old experiment's state diagram or cycle count as the current contract.

## Software interface and limits

The prototype uses custom CSRs: `0x800` switches/reads logical context ID,
`0x801` seeds a target PC, `0x802` seeds remote register state, and read-only
`0xCC0` supplies a core-wide cycle counter. Encoding examples live in
[the Linux demonstration](linux-tests/ctxtsw_user_tiny.c) and the test helpers;
these are not standard RISC-V threading instructions.

Ordinary floating-point execution is supported, but the accepted FPGA endpoint
does **not** provide complete nonresident FP context preservation. It also does
not make hardware contexts independently scheduled Linux tasks, implement a
permission-protected thread API, or establish isolation between mutually
untrusted contexts. The Linux proof uses cooperating contexts in one process.

## Validation and measurement

[Linux status](LINUX_BOOT_STATUS.md) records exact FPGA identities and acceptance.
[The canonical guide](CURRENT_CHECKOUT.md) identifies the supported checkout.
Measure nonresident behavior with fewer resident banks than logical contexts:
`NUM_THREADS=2 NUM_CONTEXTS=4`.

Keep benchmark spacing separate from architectural handoff latency. The accepted
FPGA benchmark measured 5.10 resident and 11.12 nonresident cycles/switch;
waveform endpoints and cache/refill tails must be reported separately. Use
`0xCC0`, not a context-restored `mcycle`, for cross-context elapsed cycles.
