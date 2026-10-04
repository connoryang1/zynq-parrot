# Persistent context-group fast path under Linux

This experiment closes the gap between the separately measured Linux-hosted
direct handoff and bare-metal ready-selector tests. One no-libc Linux process
seeds a resident context and a nonresident context once, then runs 128 timing
windows of 256 general LR/SC ready-bitmap handoffs for each. A third context's
ready bit remains present as a spectator. Each peer validates its logical ID,
private `s11`, shared ready word, completion, and Linux `getpid` result before
returning to context zero.

The physical run uses the selector-qualified bitstream SHA-256
`9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf`
and Linux shell NBF SHA-256
`af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`.
The accepted ELF SHA-256 is
`61b4d4977ffd6f06750096696a32924d319cf3362c510905c979a79b55f222da`.
The guest ELF hash, custom PASS, exit zero, and `CORE[0] PASS` all pass.

The probe was built from the repository root with:

```sh
/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  -Os -Wall -Wextra -Werror -static -nostdlib -nostartfiles -ffreestanding \
  -fno-stack-protector -ffixed-s11 -Wl,-e,_start -Wl,--build-id=none \
  -march=rv64imafdc_zicsr -mabi=lp64d -mcmodel=medany -mno-relax \
  -DBP_NUM_THREADS=2 -DBP_NUM_CONTEXTS=10 \
  -o logs/linux-context-group-fastpath-20261003/context_group_fastpath \
  logs/linux-context-group-fastpath-20261003/context_group_fastpath.c
python3 -B logs/linux-context-group-fastpath-20261003/run_board.py
```

| Peer | Median cycles/handoff | p95 window | Bare-metal selector | Hosted overhead | Linux scheduler / hosted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Resident context 1 | 17.074 | 17.074 | 17.035 | 0.039 cycles (0.23%) | 324.79x |
| Nonresident context 2 | 22.090 | 22.125 | 22.035 | 0.055 cycles (0.25%) | 251.04x |

The Linux-hosted fast path therefore retains essentially the complete
bare-metal selector performance. At the routed 18 MHz frequency, the medians
are 0.949 microseconds resident and 1.227 microseconds nonresident. The
comparison Linux scheduler handoff is the mean of its measured 5,496- and
5,595-cycle directional medians.

One resident timing window in the accepted run averages 239.1 cycles per
handoff and one nonresident window averages 90.3; every other window remains
near the median. These are aggregate 256-handoff windows under normal Linux
interrupts, so the transcript does not identify a particular interrupt.

## Reservation retries

Unlike the earlier bare-metal probe, this program accumulates every failed SC
across all operations. The accepted run observes zero failures. A preceding
otherwise complete run observes one source-side failure during the
nonresident phase and then finishes both timing series; its original strict
zero-retry policy emits FAIL and is retained as
`zero-retry-policy-rejection.log`. Across the two runs there is one observed
failure in 131,072 nominal selector operations, or 7.63 per million. This
demonstrates why the runtime must retain the LR/SC retry loop even though
contention is rare on this single-pipeline design.

The earlier bare-metal analyzer named its reported values total SC failures,
but its assembly reset the counter at each selector operation. Those values
cover only each context's final operation. The earlier timing and correctness
results remain valid; their all-operation zero-retry claim is corrected by
this experiment.

## Lifecycle correction

The first prototype initialized the naked peer's unused `gp` and `sp` through
remote register writes and then hung before its first result. The accepted
version follows the already qualified Linux ring lifecycle: it seeds only the
peer's checked `s11` and NPC. It also keeps each peer alive for the whole timing
series instead of repeatedly reseeding it. This is closer to the proposed
runtime, where Linux creates a protected group once and userspace performs many
fine-grained handoffs within it.

Linux still does not allocate or protect these context IDs. This measurement
establishes the data plane: a Linux-hosted persistent group can select a ready
context in about 17--22 cycles. Kernel ownership, cleanup, accounting, and the
no-ready fallback remain control-plane work.

The first post-stall recovery attempt timed out waiting for the board's FPGA
manager and did not load an overlay or execute a guest. The next readiness gate
passed, the exact bitstream was reloaded with FPGA state `operating`, and the
accepted run then completed. The readiness and overlay transcripts are retained
separately from target evidence.
