This directory records the clean fixed-arm protocol for measuring persistent instruction replay on the existing Linux pipe-handoff benchmark. It separates enabled and disabled replay into fresh boots so retained advisory lines cannot leak between A/B arms. Initial FPGA measurements use the pipe-trained table before testing whether the futex-specific table transfers.

# Persistent pipe fixed-arm A/B

## Question

RL-081's pipe matrix interleaved disabled and enabled trials while completed replay lines persisted, so it could not measure the full feature-versus-disabled effect. RL-086/087 fixed that leakage with `fence.i`, but the resulting cold clear-and-refill policy is deliberately different from the retained policy that improves the futex pair in RL-088--090. This protocol measures the retained policy on a second handoff path without sharing state between arms.

## Protocol

The existing benchmark now accepts `alternating`, `enabled`, or `disabled` as a final argument. Fixed arms run 16 unreported warmups followed by 512 reported handoffs. Every arm uses:

- successful-wakeup mode 6;
- equal-priority `SCHED_FIFO` parent and child tasks;
- the hot-proxy footprint, keeping four data hints as cache hits while leaving instruction replay as the mechanism under test;
- persistent replay state with no `fence.i`; and
- group 7 for the initial feasibility/replication pair.

Every enabled or disabled arm receives a fresh physical power cycle, readiness wait, verified overlay reload, exact artifact hash checks, and terminal runner/child/parent/CORE/BSG PASS. Two replicate pairs run in opposite boot order. The strict analyzer requires the same NBF, transfer, ELF, control program, group, timing, footprint, policy, replay state, and 512 ordered timing/tail rows in all four arms.

## Prepared identities

- Routed bitstream SHA-256: `e97e0517d08771753e2eae96c6af95380944e5a8e2aefa0115da898b7be12381`
- Pipe-trained mode-6 NBF SHA-256: `5e42c2f6c801d71506a3c6fc5e708aa01c0e6a46996fc72bc64236135565d2bd`
- Control-program SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- Fixed-arm benchmark ELF SHA-256: `16eb7b7b89c25383aaef23ce98d8206352e713e60e3ff72bc5c95ad60d25dcba`
- Fixed-arm transfer SHA-256: `855fb8493f10bf0b7a366bb5fb0b76755e99a3810417bb6b52109e638b6e60cc`
- Compiler: `/home/jhumphri/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-gcc`

The generated enabled command is:

```text
/tmp/scheduler_physical_preview_benchmark_dynamic 7 wake-trigger hot-proxy fifo persistent enabled
```

The disabled arm changes only the final argument. The board runner selects only group 7, records the fixed arm and control-program hash in its adjacent status, and powers off after the cell. All 100 discovered Linux Python tests pass; the focused Makefile harness passes all 60 checks after a clean RV64 rebuild.

## Decision sequence

First compare the pipe-trained table against disabled replay. If the opposite-order fixed-arm result resolves, compare the accepted futex-specific v1 table on the same pipe protocol to quantify specialization. If the initial group result is promising but set interference remains plausible, expand the fixed-arm comparison across all eight groups before claiming a pipe-path speedup.
