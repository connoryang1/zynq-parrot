This directory preserves the predeclared instruction-only control for the corrected-route wake/data experiment. It measures the accepted mode-six wakeup replay on the same routed FPGA and FIFO pipe workload before interpreting the joint image.

# Corrected-route instruction-only control

The protocol uses four independent fresh-board boots in opposite arm orders:
enabled then disabled, followed by disabled then enabled. Every boot runs one
fixed group-seven arm with target data, FIFO scheduling, persistent replay
state, and 512 accepted trials. The strict analyzer must require exact software
and bitstream identities, zero hook deltas, kernel-failure screening, and all
terminal guest/core/host markers.

Exact predeclared identities are:

```text
NBF:             93b2e29de83be627631a6cb6e78b2a5529f9a42c89cb365894cfe7138a028629
benchmark ELF:   16eb7b7b89c25383aaef23ce98d8206352e713e60e3ff72bc5c95ad60d25dcba
fast transfer:   b6d9f3731ebcbd6b2717a1e0d8987c7b6a3ee58364ce7d04ce19801f0d2dd09e
control program: 2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30
bitstream:       a070df7f2d69b86e745a9b915798e704ac4ee2255e97d3c50e3aa1a4f4ba3ce9
```

The primary comparable endpoints are wake-to-entry, local load cycles, and
wake-to-load. The ordinary `wake-trigger` benchmark calls `getrusage()` after
first use to validate one voluntary switch, whereas the joint `wake-data`
benchmark uses a counted late hook. Its post-load and complete-roundtrip tail
therefore cannot be directly subtracted from the joint result; this control can
attribute the first-resume and local-load effects, not the joint roundtrip
effect by itself.

## Result

All four independent boots pass exact identity, 512-row/tail, zero-hook,
kernel-failure, and terminal child/parent/core/host gates. Replicate one ran
enabled then disabled and filtered two/zero asynchronous attempts; replicate
two ran disabled then enabled and filtered two/two attempts.

Instruction-only replay changes wake-to-load by +181 cycles on the
replicate-stratified enabled-minus-disabled estimand, with circular-block
interval `[-3507,8597]`; it is unresolved. Its local-load effect is exactly
zero cycles, with block interval `[0,0.5]`. Strict analysis SHA-256 is
`499d436dd9bf6f9795b1de48c128a0350b372eba799d8001d9f49b96e6380636`.

The strict cross-experiment bootstrap compares this control with the accepted
joint `wake-data` result only through first use. The incremental joint-minus-
instruction effect on the four loads is -33.75 cycles with block interval
`[-37.5,-19]`, proving that the useful local data effect comes from the data
hints rather than instruction replay. Incremental wake-to-load is +7,267.75
cycles with `[-9363,15621.5]`, unresolved with a harmful point estimate.
Comparison analysis SHA-256 is
`ad026cf058d8a45b2073d8f19a972dd96c1c745d4ece854e2b2d7b791a85781f`.

The joint image therefore fetches genuinely useful target data, but it still
does not demonstrate a faster incoming-context first-use boundary. The joint
roundtrip reduction remains a valid within-image throughput result but cannot
be attributed by this cross-image comparison because the post-load filtering
shapes differ.
