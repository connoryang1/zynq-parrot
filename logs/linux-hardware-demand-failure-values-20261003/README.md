# Hardware-demand failure-value diagnostic

This follow-up preserves the demand-loop assembly and adds only out-of-timing
failure reporting around `run_hardware`. If the returning context, peer
completion count, or peer terminal context is wrong, it prints all three
observed values and performs a direct Linux `exit_group` syscall. This avoids
losing the diagnosis in normal process teardown while the detached hardware
context remains outside Linux's pthread lifecycle.

The exact diagnostic ELF completes warmup and all **64 samples**, covering
524,288 checksum-verified requests. It exits zero, the runner exits zero,
`CORE[0] PASS` is present, and the failure reporter never triggers. Median
timing is 611,809 cycles, or 74.68 cycles/request; timing is secondary here,
but confirms that the loop still behaves like the preceding demand runs.

The source and peer demand routines remain opcode-for-opcode identical to the
previously failing ELF. The added diagnostic changes layout, moving both by 32
bytes (`0x11e58` to `0x11e78` and `0x11e98` to `0x11eb8`). Consequently this
pass proves there is no inevitable accumulated-state failure below 64 samples,
but it cannot by itself prove address sensitivity: layout, instrumentation,
and run-to-run physical state are confounded. The next discriminating test is
a fresh-boot repeat of the exact previously failing ELF.

| Artifact | SHA-256 |
| --- | --- |
| Diagnostic guest ELF | `e2f48758d80f1dab791f112ba1cf3778594a2ad573dd2add664888ee069272cf` |
| Previously failing guest ELF | `8d95f0cfbf91686836ab72b2fe3029bdee1f338a2658774ca1034debf5b1d643` |
| Bitstream | `9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |

Reproduce the analysis with:

```sh
python3 -B logs/linux-hardware-demand-failure-values-20261003/analyze.py \
  > logs/linux-hardware-demand-failure-values-20261003/analysis.stdout
cmp logs/linux-hardware-demand-failure-values-20261003/analysis.json \
  logs/linux-hardware-demand-failure-values-20261003/analysis.stdout
```
