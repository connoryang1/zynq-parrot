# Controlled 64-byte hardware-loop alignment

This experiment starts from the exact repeatedly failing source and changes
only the `source_*` and `peer_*` hardware-loop alignment attribute from 8 to
64 bytes. The original verification logic and main-stack layout remain intact.
The demand-loop opcode sequences are unchanged.

The aligned ELF passes warmup and samples 1--50, then starts sample 51 and
produces neither a result nor a verification message. After 60 seconds with no
additional output, the controller is deliberately stopped. The board requires
a power cycle, so the prefix is failure evidence rather than accepted timing.

`source_demand` moves from `0x11e58` to the 64-byte boundary `0x11e80`, and
`peer_demand` moves from `0x11e98` to the boundary `0x11ec0`. Their 16 and 22
functional instruction words are unchanged. Alignment therefore does not
eliminate the lifecycle hazard. Cross-run validation and exploratory failure
statistics are in `logs/linux-hardware-demand-lifecycle-repeats-20261003/`.

| Artifact | SHA-256 |
| --- | --- |
| Aligned guest ELF | `90411570eaf29908cd5d94d1d6eac449f9fde0d36261234860f445cc2ffe22d8` |
| Original guest ELF | `8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643` |
| Bitstream | `9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |
