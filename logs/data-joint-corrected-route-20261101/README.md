This directory preserves the corrected-route data-only and joint instruction/data feasibility experiment. It reuses one immutable Linux payload, benchmark, routed bitstream, and physical protocol so only the OpenSBI instruction table distinguishes data-only from joint operation.

# Corrected-route data and joint preview

The routed four-context bitstream already contains both the detached
instruction-replay buffer and the independent four-entry physical data-preview
queue. The accepted instruction-only result used runtime mode six, which emits
the wakeup instruction trigger but no data hints. This follow-up requires no RTL
change.

The exact images are:

```text
data-only count-zero NBF: 9cb18adf98b41ea88ed9958555c238a4b00970984fb4b07720cc2c1695358c71
joint futex-v1 NBF:        93b2e29de83be627631a6cb6e78b2a5529f9a42c89cb365894cfe7138a028629
benchmark ELF:             16eb7b7b89c25383aaef23ce98d8206352e713e60e3ff72bc5c95ad60d25dcba
fast transfer:             b6d9f3731ebcbd6b2717a1e0d8987c7b6a3ee58364ce7d04ce19801f0d2dd09e
control program:           2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30
bitstream:                 a070df7f2d69b86e745a9b915798e704ac4ee2255e97d3c50e3aa1a4f4ba3ce9
```

The fail-closed OpenSBI splicer takes all 1,861,857 Linux/DTB records from the
count-zero image and all 17,024 low records from futex-v1, reproducing the joint
NBF byte-for-byte. Thus the two NBFs have an identical Linux payload. A durable
count-zero archive is under
`/home/coyang/fpga-artifacts/context-resume/data-joint-corrected-route-20261101/`;
streamed decompression reproduces its hash above.

First run one predeclared group-7 `late target fifo isolated alternating`
feasibility cell on each image after an independent full board recovery,
artifact restage, hash check, and overlay load. Mode two triggers instruction
replay at task selection and issues the four pinned physical data hints
immediately before the architectural switch; the count-zero image therefore
measures data-only, while futex-v1 measures joint operation. Both arms retain
identical page pins, eviction traffic, FIFO policy, symmetric `fence.i`, and
balanced `[off,on,on,off]` trials. The runner must enforce the exact bitstream
hash above.

Group 7 is a historical functional-feasibility cell, not a selected performance
winner. A promising or ambiguous result advances to all eight predeclared cache
set groups; no general effect may be claimed from the feasibility cell alone.

## Selection-time feasibility and fixed-arm result

Three recovery-qualified alternating feasibility cells first separated the
existing paths. Data-only mode two improved the four-load body by 11 cycles but
made wake-to-load 192.75 cycles slower. Joint mode two improved the loads by
18.75 cycles but made wake-to-load 540.75 cycles slower. Its matched mode-three
instruction-only selection control showed that adding the four data hints
improved the local loads by about 20.5 cycles while worsening wake-to-load by
about 121.5 cycles. All three cells passed exact image, hook-count, row-count,
kernel, core, and host gates; they are feasibility evidence, not full A/B
replication.

The persistent mode-two follow-up then used four fresh boots in opposite
disabled-enabled and enabled-disabled orders. The four-load effect resolves at
-11 cycles on the replicate-stratified enabled-minus-disabled estimand, with
circular-block interval `[-25.5,-2.75]`. Wake-to-load remains unresolved at
-1,543.25 cycles with `[-16253.5,7525.25]`, and roundtrip remains unresolved at
-303 with `[-582.5,67.25]`. Thus retained state makes selection-time joint
operation less harmful than the cold feasibility point, but does not establish
an end-to-end gain. Strict analysis SHA-256 is
`e43ff0052d11c7b91cf530931de53aca23ece56fd899df089b9117230c20bae5`.

## Wakeup instruction replay plus late data

An initial mode-seven implementation was rejected before FPGA use. Although it
was functionally direct, recompilation moved `futex_wake` by four bytes and
`__schedule` by eight bytes, invalidating the absolute instruction table as a
matched control. No result from that image is claimed.

The accepted experiment instead changes only the existing late-hook comparison
immediate from mode two to mode six. The source-built image retains every
audited symbol address and differs from the accepted mode-six payload in 31
bytes; only one difference is executable logic: `li a4,2` becomes `li a4,6` at
physical `0x80a13ae4`. The deployable NBF applies that exact byte through one
fail-closed 64-bit record replacement at `0x80a13ae0`. `cmp -l` reports one
changed ASCII character in the complete NBF, so OpenSBI, the kernel layout,
instruction table, rootfs, DTB, and timer tail remain otherwise byte-identical.

Exact identities are:

```text
wake-data NBF:      8cee44733ed80439541168fb2c610b00af1f37a7108e4c2ae8eb52b5d728d64c
benchmark ELF:      232413aa5dbcd86914c89c0b7209322afb4f1680bf8f07da0c3e4602d79dbf54
fast transfer:      bd2135969325df1e3c9d1ff8b1b59b756c681792d03ff5d44144af2f5e3c59eb
bitstream:          a070df7f2d69b86e745a9b915798e704ac4ee2255e97d3c50e3aa1a4f4ba3ce9
strict analysis:    115ed5097fded94b31e05ebfefe351dd449254356bff3313b02587e46bcf5815
compressed archive: 60d4e15ad4b7cad62a28cb826d6bc41fa64eed6dedd322a59c0eb6cb6db30cf1
```

Four independent recovery/stage/hash/load boots form opposite-order fixed-arm
pairs. Every arm contains 512 ordered rows and tails, the exact bitstream and
software identities, expected mode and hook counts, zero kernel-failure
markers, and terminal child/parent/cell/core/host PASS. The final enabled arm
filters two asynchronous attempts; the other three filter none.

The replicate-stratified enabled-minus-disabled results are:

| endpoint | cycles | IID 95% interval | block 95% interval |
| --- | ---: | ---: | ---: |
| wake to entry | +6,807.75 | [-8,838, +16,547.75] | [-7,754.75, +16,077.25] |
| four dependent loads | -33.75 | [-35.5, -19] | [-37.5, -18.5] |
| wake to first use | +7,448.75 | [-8,776.25, +16,278.25] | [-7,320.75, +15,798.25] |
| complete roundtrip | -862.5 | [-1,571.75, -324.5] | [-1,354.5, -451] |

Negative means enabled is faster. Pooled roundtrip medians are 144,830.5
enabled and 145,716.5 disabled, an 886-cycle or 0.61% reduction; the primary
replicate-stratified reduction is about 0.59%. The data hints therefore have a
resolved local effect, and combined operation has a resolved steady-state
two-handoff throughput effect. The incoming task's first-use boundary remains
unresolved with a harmful point estimate, so this is not a demonstrated Linux
resume-latency speedup. Instruction replay is active in the enabled arm, so the
roundtrip result also cannot be attributed specifically to data without an
exact current-route instruction-only control.

The compressed NBF is durable at
`/home/coyang/fpga-artifacts/context-resume/data-joint-corrected-route-20261101/`;
streamed decompression reproduces the NBF hash above. The board is left in the
untrusted post-shutdown state and requires full recovery before reuse.
