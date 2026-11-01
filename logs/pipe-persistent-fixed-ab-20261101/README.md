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
- Fixed-arm transfer SHA-256: `b6d9f3731ebcbd6b2717a1e0d8987c7b6a3ee58364ce7d04ce19801f0d2dd09e`
- Compiler: `/home/jhumphri/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-gcc`

The generated enabled command is:

```text
/tmp/scheduler_physical_preview_benchmark_dynamic 7 wake-trigger hot-proxy fifo persistent enabled
```

The disabled arm changes only the final argument. The board runner selects only group 7, records the fixed arm and control-program hash in its adjacent status, and powers off after the cell. All 100 discovered Linux Python tests pass; the focused Makefile harness passes all 60 checks after a clean RV64 rebuild.

## Decision sequence

First compare the pipe-trained table against disabled replay. If the opposite-order fixed-arm result resolves, compare the accepted futex-specific v1 table on the same pipe protocol to quantify specialization. If the initial group result is promising but set interference remains plausible, expand the fixed-arm comparison across all eight groups before claiming a pipe-path speedup.

## Rejected boots

The first disabled attempt reached `/init` and began Buildroot startup, then the host bridge reported `Errant write to 1c3d80` while the guest printed `Running sysctl`. The run ended with host BSG PASS before a shell, uploaded ELF, benchmark command, or timing sample existed. Exact launch hashes had passed, but the root cause of this intermittent pre-shell failure is not established; the transcript is rejected and retained as `rejected-rep1-disabled-boot1.log.gz` with its FAIL status.

After complete recovery, the unchanged retry reached a shell but died with `Errant write to 1e3de8` near the end of the historical 76-column base64 upload. It issued roughly 240 individual shell commands over several minutes and still produced no benchmark sample. That transcript is `rejected-rep1-disabled-boot2-slow-transfer.log.gz`. A successful enabled feasibility run using the same slow transfer is retained as `exploratory-slow-transfer-enabled.log.gz`, but it is excluded from the matched A/B because the transfer protocol is changing.

The second failure exposed avoidable guest exposure rather than a disabled-mode result. The exact 13,784-byte ELF compresses to 6,020 bytes and needs only 36 data commands when ordinary base64 lines widen from 76 to 512 characters. The Makefile now permits an explicit `PHYSICAL_PREVIEW_TRANSFER_WIDTH=512` while keeping 76 as the historical default. The exact 39-line transfer was generated with `make --no-print-directory` so redirected Make chatter cannot become bogus guest commands, and a local execution reconstructed the exact ELF SHA-256 byte for byte. Final A/B arms restart with this one fast-transfer identity. Every failed board state still requires a complete physical power cycle, readiness wait, and overlay reload.

## Pipe-trained fixed-arm FPGA result

Four successful fresh boots form opposite-order pairs: disabled then enabled, followed by enabled then disabled. Every arm passes exact NBF/transfer/ELF/control identity, contains 512 ordered base and tail rows, records only the requested fixed mode with zero hook deltas, and ends in runner/child/parent/CORE/BSG PASS. The accepted runs filter 3/1/1/2 asynchronous attempts respectively; those attempts are reported by the benchmark and excluded before trial numbering.

The two enabled wake-to-load medians are 29,260 and 29,981.5 cycles. Disabled medians are 46,824.5 and 30,184.5. The first disabled run spends its second quarter in a slow phase, so the replicate-stratified first-use estimate is -8,883.75 enabled-minus-disabled cycles but both IID `[-17264.75,7186.5]` and circular-block `[-16900.5,6503]` intervals cross zero. Quarter pairing also has two of eight positive differences. Persistent pipe replay therefore does **not** yet establish a faster incoming-task first-use boundary.

The complete two-handoff roundtrip is stable. Enabled medians are 162,065 and 162,255 cycles versus disabled medians of 164,782 and 163,691.5. The replicate-stratified enabled-minus-disabled estimate is **-2,076.75 cycles**; IID `[-2480.25,-1683]` and circular-block `[-2473.75,-1668.75]` intervals resolve below zero. Pooled medians are 162,152 versus 164,293.5, a **2,141.5-cycle or 1.30% reduction**. All eight 128-trial quarter differences favor enabled, with median -2,119.75 cycles.

The roundtrip result proves that retained replay transfers beyond the futex harness as a steady-state pipe-pair throughput effect. It does not prove the intended incoming-task first-resume gain: the interval for wake-to-entry also crosses zero, return handoff is nearly but not fully resolved, and shared scheduler lines warmed on the outbound switch can help later portions of the roundtrip. The 23-cycle pooled target-load difference is not promoted because its replicate/quarter direction is inconsistent even though the conditional bootstrap interval is below zero.

The strict result is `pipe-trained-fixed-ab-results.json`, SHA-256 `56547ceb3ebcfe93330e2667292cc17413b9afaa3c8d550d1deea17aa88e911c`. Accepted deterministic transcript/status hashes are:

```text
rep1 enabled:  f8177b5f53b3dc86ff55d80fac4c7034b9ee77f9cb481438a0e5d685310fabe6 / e939adcbfc79715423fa4ca736f365120bc6633f9aca3736bbe7a833b327d83b
rep1 disabled: 30a5c0bcfc02e2ef99ae958e8c6736e15a76a969661a430ea30dfefb23c22f61 / 264a2dc6923f50e059710f620c574f9235bd6d2e61c169b1f5580bc9597ba5b0
rep2 enabled:  7b65f7d34d2a27b4c403d7112261474c0b37b1682fa20c573d66667cea81dac1 / e939adcbfc79715423fa4ca736f365120bc6633f9aca3736bbe7a833b327d83b
rep2 disabled: 6cf358ff2125e9865eb576447d638b79d1ea9b623a80a8e8bba5d88754fa36b6 / 264a2dc6923f50e059710f620c574f9235bd6d2e61c169b1f5580bc9597ba5b0
```

The board was left in the untrusted post-guest-shutdown state after the final arm. Any follow-up must begin with physical recovery. The next useful discriminator is a fresh opposite-order current-table versus futex-v1 comparison on this exact pipe protocol: it tests whether manual futex specialization sacrifices the now-resolved pipe throughput effect.
