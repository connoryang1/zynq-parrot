# Five-slot physical acceptance and adjacent-word regression

The routed five-slot image at top commit `4e527cad1` and BlackParrot commit
`d4c20786d` was loaded on the PYNQ-Z2 with bitstream SHA-256
`933777e636853c0a6e9c6cb6d068778b4a49209510d16e49226c63bcbb6793ea`.
The FPGA manager reported `operating`, and every reported passing sample had
guest, core, and host PASS markers. The benchmark images are the checked
`candidate-k3` 2/3/4/10-stream images recorded in
`logs/prefetch-mlatency-20260926/board-collateral/source/candidate-k3/`.

One ordered sweep measured:

| Streams | Serial demand | Serial prefetch | Software interleaved | Hardware switching |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 60,090 | 82,600 | 62,237 | 69,902 |
| 3 | 60,019 | 82,457 | 60,906 | 73,144 |
| 4 | 60,099 | 82,580 | 60,729 | 74,377 |
| 10 | 60,352 | 82,152 | 62,843 | CORE FAIL |

An independent first three-stream hardware sample was 73,152 cycles. Reloading
the exact overlay before repeating ten-stream hardware switching reproduced the
same early `CORE FAIL`, before a benchmark result. Thus the failure is not
residual board state. These are diagnostic samples rather than accepted
performance medians.

The ten-slot image at top commit `a69fad73`, BlackParrot commit `db5a52da5`,
and bitstream SHA-256
`c74495d7acb596934492be70d9b76f20b7672cdd36871afc656eee85b0dce520`
was then loaded as a control. It measured 60,064/82,377/61,168/69,958 cycles
for two-stream modes 0/1/2/3, 60,474 for ten-stream software interleaving, and
76,023 for ten-stream hardware switching. The latter passed. Ten slots do not
restore the original fast behavior, so five-slot capacity is not the cause of
the performance collapse. The five-slot ten-stream failure remains a separate
undersubscribed-queue correctness issue pending a rebuilt fix candidate.

The physical performance regression is caused by BlackParrot commit
`10cb0e645`. A narrow prefetch returns the 16-byte sector containing both a
node's next pointer at offset 0 and value at offset 8. That commit invalidated
both words when the pointer load hit. The following value load therefore took
an ordinary DRAM miss once per node. This directly explains why software
interleaving moved back to the approximately 60,000-cycle demand baseline and
why serial prefetch became slower than demand. The later rotating-replacement
commit `518d2fca7` already prevents an unused neighbor from pinning a full
buffer, so whole-sector invalidation is unnecessary.

BlackParrot commit `4f56fba7d` restores per-word consumption while retaining
rotating stale-entry replacement. In the exact current narrow-path simulator,
the two-stream, 1,280-node software case falls from 80,803 to 10,715 cycles,
a 7.54x improvement, with checked guest/core/host PASS. The five-slot,
ten-stream hardware-switch case also passes in simulation at 97,040 cycles
under the 200-cycle synthetic memory model. The five-slot stale-entry test
issues ten old unused hints followed by ten new hints and passes, establishing
that adjacent-word retention does not restore the old replacement-pinning bug.

The simulator result establishes the RTL cause and fix but is not a replacement
for physical acceptance. A new five-slot route containing `4f56fba7d` must be
loaded and the complete physical matrix repeated before reporting recovered
FPGA speedup or resolving the ten-stream board failure.
