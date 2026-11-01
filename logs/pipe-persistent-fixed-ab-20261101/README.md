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

## Table-comparison preparation failure

The first fresh current-table arm for the follow-up reached a guest shell, reconstructed the exact ELF, and then reported `sha256sum: not found`; the benchmark never launched and no sample exists. The same NBF normally exposes `/usr/bin/sha256sum`, and the rootfs archive contains both that link and `/bin/busybox`. The exact cause of the missing link in this boot is unconfirmed. The rejected transcript/status are retained as `rejected-table-rep1-current-missing-sha-link.log.gz`; after the runner's bounded 300-second identity wait, the session was closed and the board requires full recovery.

The identity gate now invokes `/bin/busybox sha256sum` directly. This preserves the expected digest/output while depending only on the BusyBox binary that provides the running guest shell, not the optional applet link. Focused and complete runner tests must pass before the unchanged table arm is retried.

The first futex-v1 table arm later completed all 512 benchmark rows and printed child/parent/cell PASS, but an asynchronous `klogd` path had already reported a bad spinlock and scheduling-while-atomic trace. Guest `poweroff` then faulted and returned to the shell, so CORE/BSG PASS never appeared and the runner wrote FAIL after its bounded terminal wait. No timing from this contaminated boot is accepted. The transcript/status are retained as `rejected-table-rep1-futex-v1-poweroff.log.gz`; the cause is not assigned to table contents without an unchanged recovery-qualified retry. The guardrail remains full physical recovery and exact hash revalidation before that retry.

The unchanged recovery-qualified retry passed cleanly. However, the first futex-v1 arm in the reverse-order pair again completed all 512 rows and benchmark PASS markers before `poweroff` faulted and returned to the shell without CORE/BSG PASS. Unlike the first rejected candidate boot, this transcript has no earlier klogd BUG; it is retained as `rejected-table-rep2-futex-v1-poweroff.log.gz` and contributes no timing. Two shutdown failures among three candidate launches are a concerning correlation but not yet a confirmed table-content defect because one identical launch passed and the fault occurs after measurement. The strict fixed-arm loader now also rejects `BUG:`, panic, Oops, scheduling-while-atomic, and segmentation-fault text even if ordinary PASS markers exist. One final recovery-qualified candidate retry is the predeclared discriminator; another terminal failure rejects the cross-workload table comparison as unstable rather than retrying indefinitely.

The final recovery-qualified futex-v1 retry failed in the same way and is retained as `rejected-table-rep2-futex-v1-final-poweroff.log.gz`. The last two failures reach `wakeup_flusher_threads+0x5e/0xba` after cell PASS, execute the same faulting instruction bytes, and report different corrupted-looking bad addresses before `poweroff` segfaults. In total, three of four futex-v1 pipe launches fail terminal acceptance; only one is clean. The current-table comparison arm passes, as do all four current-table arms in the preceding enabled/disabled experiment.

The current-versus-v1 performance comparison is therefore rejected as unstable and no timing from the single clean pair is promoted. This does not revoke v1's accepted futex-specific 2.68% result, whose four measured boots pass, but it prevents treating v1 as a workload-independent/global table. The next bounded discriminator is the already-built v2 table: it retains 14 v1 entries and replaces only otherwise-unused `0x8023f780` and `0x802034c0`. A 512-handoff pipe stability run can test whether those two entries are necessary for the cross-workload fault; it is a functional isolation experiment, not an attempt to revive v2's rejected futex performance.

Two independent v2 stability boots both pass all 512 rows, strict kernel-failure scanning, and terminal CORE/BSG PASS. Their roundtrip medians are 163,158 and 161,984 cycles; these are not compared as a performance result because there is no opposite-order table protocol. V2 passes 2/2 pipe launches, while v1 passes only 1/4 under the same benchmark/transfer/bitstream. The evidence narrows the instability to the two v1-only entries as a pair, but sample count and simultaneous replacement prevent assigning either entry individually.

Exact v1-versus-v2 NBF comparison changes only two 64-bit OpenSBI records below the untouched Linux payload: table storage `0x80017e60` changes `0x8023f780` (`__dequeue_entity`) to `0x80a12500`, and `0x80017e90` changes `0x802034c0` (`restore_caller_reg`/bad-stack line) to `0x802980c0`. This makes one-record hybrid NBFs exact and avoids a source rebuild. The next productive discriminator restores each v1 entry separately on the clean v2 base and runs the same stability gate; it must preserve all other NBF records exactly and remains functional diagnosis, not performance tuning.

V2 deterministic evidence hashes are:

```text
rep1 gzip/status: 6340a5400397504e4eec47110a5bf0e48eb5e9f6a3c51a71b8760654be3a5125 / 44fbd7657a450413267597945640dca2f5cd0c73e48837bdf7e117fbc11bc55d
rep2 gzip/status: 42a80f28c1a08665d1319b36d751ac0468de07c02a30e6e05e6ffc989c94c0b3 / 44fbd7657a450413267597945640dca2f5cd0c73e48837bdf7e117fbc11bc55d
```

The board is left in the untrusted post-shutdown state after v2 replicate 2. The remotely staged futex-v1 image was removed to make space for v2; its exact local copy remains recoverable. Any hybrid run must begin with full physical recovery and post-cycle NBF rehash.

Hybrid preparation uses `linux-tests/patch_nbf_memory_records.py`, which requires an exact expected old word, changes each requested address exactly once, refuses overwrite, and preserves every other line. All 108 discovered Linux tests and 67 focused harness tests pass. The keep-update hybrid SHA-256 is `6c615c32dde22177fc8629c88982ee69f3731942a7815f5a04c32100f65698c5`; it differs from v2 only at table word `0x80017e60` and from v1 only at `0x80017e90`. The keep-restore hybrid SHA-256 is `999e134ce40340864a827090dba38f36e6ff4974438839bf3488b9f0ef70d1e2`, with the inverse one-word differences. Neither changes a record at or above Linux payload address `0x80200000`.

The first generic NBF CSR check was invoked without its required CSR arguments and therefore ran no scan; that attempt is discarded. Repeating it with custom CSR IDs `0x800`--`0x804` reports four known Linux data-word false positives in accepted v2 and both hybrids, with byte-identical diagnostic SHA-256 `68d66bb7...55eb`. The hybrids introduce no new whole-NBF collision, and their OpenSBI instruction bytes are otherwise exact accepted v2; the accepted v2 firmware-only ELF scan remains the relevant gate.

## One-record hybrid FPGA isolation

The keep-dequeue hybrid (historically named keep-update before correcting its symbol) stalls on its first fresh boot before a shell, stopping after `io scheduler kyber registered` at guest time 3.612 seconds until the 300-second shell gate expires. That boot cannot discriminate table contents: no benchmark command ran, the Linux patches initialize `bp_preview_phys_mode` to zero for new/exec tasks, and only an explicit benchmark `prctl` changes it to mode six and launches the table. Its second fresh boot passes 512 ordered handoffs, strict kernel-failure scanning, clean shutdown, and terminal CORE/BSG PASS, with a diagnostic-only 162,872.5-cycle roundtrip median. The rejected/pass gzip and status hashes are `368f7bf74dbc7551b7ebed46e21382943a6c8b9858638e49b24e734869f447a5` / `0c9a98b40c6b75350b2349c004857059f534c4ec2fb25045b42c178ae18d9384` and `12899d6794c54c628ce84af228a1ebc0021f4d8e4f9f6f689aa0c03e7636f20e` / `42be0fb60df9233ef0f04087496dab2d315e53c3de166e797d420e64465ec400`.

The inverse keep-restore hybrid passes both independent fresh boots through all 512 rows and terminal gates. Its diagnostic-only roundtrip medians are 162,336 and 162,341.5 cycles; gzip/status hashes are `2a1776c4fd66adfbf0f1605213111ce89858390b095d286a5f53cc54b148b600` / `3c36ad5867b7213e6efc34b594fed0c71bc78bed01cc0e7fb3281705d3e6785d` and `44fef8885bbba1ebd9b499489e8f66639abb9f8034ab76f182343a037eb1200c` / the same deterministic status hash. The activated comparison is therefore two keep-restore passes versus one keep-dequeue pass, with no activated hybrid failure; it does not isolate either v1-only entry. The board is untrusted after the final guest shutdown and requires full recovery before reuse.

The exact symbol audit corrects an earlier provenance mistake. Physical `0x8023f780` maps to virtual `0xffffffff8003f780`, not `0xffffffff8023f780`; exact mode-6 `vmlinux` SHA-256 `85ce28957b945372e9b0ed87e37be809ef9220d8fc06165a07d7a981a77d6df9` disassembles that line at `__dequeue_entity+0x2a`, agreeing with retained symbol map `d8782807b0a837ad0bb994a250d40066de25ed89c90c5ad1d7db186359011db6`. All 143 `.alternative` records were decoded and none overlaps the line; the image has no jump-label/static-call patch section. Runtime alternative patching is therefore not the immediate explanation. One objcopy probe omitted the required output operand and failed for lack of temporary space before extraction; the exact source hash was unchanged, and the corrected extraction used `/tmp`.
