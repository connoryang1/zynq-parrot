# Exact failing-ELF fresh-boot repeat

This experiment repeats the exact demand-only ELF that previously failed in
sample 27. It uses the same bitstream, Linux shell, configuration, and a fresh
board power cycle. The runner recognizes either a complete 64-sample pass or
the binary's original generic hardware-verification failure; on failure it
stops the controller immediately instead of waiting for the ten-minute target
watchdog.

The exact ELF passes warmup and samples 1--2, then starts sample 3 and produces
neither a result nor the post-run verification message. After 60 seconds with
no additional output, the controller is deliberately stopped rather than
waiting for the ten-minute board watchdog. The board requires a power cycle,
so this is measured stall evidence rather than an accepted performance run.

This fresh-boot reproduction proves that the prior sample-27 failure was not a
one-off mixed-mode artifact, while its earlier failure point proves the sample
count is variable. Cross-run validation and interpretation are in
`logs/linux-hardware-demand-lifecycle-repeats-20261003/`.

| Artifact | SHA-256 |
| --- | --- |
| Exact guest ELF | `8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643` |
| Bitstream | `9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |
