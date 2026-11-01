This directory evaluates whether a smaller physical data-preview footprint can turn useful local cache fills into faster Linux first use. The experiment changes only the benchmark's registered/load line count while retaining the accepted wake-data kernel, instruction table, routed FPGA, and fixed-arm protocol.

# One-line wake/data best case

The predeclared first candidate uses one target line in group seven. The
benchmark registers one physical address and three zeros, so the unchanged late
kernel hook executes one physical-hint CSR write instead of four. The target
body performs one dependent load. Both enabled and disabled arms retain
identical pinning, cache pressure, FIFO policy, and persistent replay state.

The acceptance protocol is four independent fresh-board boots in opposite
enabled-disabled and disabled-enabled orders, 512 accepted trials per arm. The
strict analyzer must bind `lines=1`, exact artifact identities, one/zero hook
counts, kernel-failure scanning, and all terminal markers. Wake-to-load is the
primary endpoint; local load cycles distinguish a useful fill from scheduler
overhead. A one-line result is a deliberately favorable workload shape, not a
general four-line-footprint claim.

```text
NBF:             8cee44733ed80439541168fb2c610b00af1f37a7108e4c2ae8eb52b5d728d64c
benchmark ELF:   15f44168ce075cef78cd487938210b2758c50e45393698b5d970a4c464136d15
fast transfer:   6c68779caf36ca2b054a95824f5f6ac08d8b5f67fea80cc25402267ff863e395
control program: 2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30
bitstream:       a070df7f2d69b86e745a9b915798e704ac4ee2255e97d3c50e3aa1a4f4ba3ce9
```

## Result

All four arms pass exact identities, `lines=1`, 512 ordered rows/tails, expected
hook counts, zero filtered attempts, kernel-failure scanning, and terminal
child/parent/core/host gates. Strict analysis SHA-256 is
`0a644a3b61a1d03337dce5a5670b65c8338bcff3dc56b0b9d5e24be5b0d67aec`.

The single target load improves by 37 cycles on the replicate-stratified
enabled-minus-disabled estimand, with circular-block interval `[-39,-19.5]`.
Wake-to-load instead has a harmful +7,980.75-cycle point and unresolved interval
`[-1869.5,16050]`. Roundtrip improves by 299.75 cycles with
`[-688.5,-42.75]`, approximately 0.21% of the pooled disabled median. Negative
means enabled is faster.

Reducing four physical hint writes to one therefore preserves a useful local
fill but does not demonstrate faster incoming-context first use. The four-CSR
issue count is not the sole explanation for the missing resume-latency gain.
The next timing discriminator should move this same one-line data hint earlier
while retaining the wakeup instruction trigger and absolute replay table.
