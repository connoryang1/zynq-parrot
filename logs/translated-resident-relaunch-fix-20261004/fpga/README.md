# Physical acceptance inputs

This directory preserves the exact two Linux userspace binaries needed to test
whether the translated resident-relaunch fix resolves the physical lifecycle
failure. They are copied unchanged from the preceding controlled experiments:

| Binary | Switch-loop PCs | Prior result on predictor-corrected image |
|---|---|---|
| `failing-placement.elf` | `0x11e80` / `0x11ec0` | Hung in the first warmup |
| `passing-placement.elf` | `0x11f00` / `0x11f40` | Passed 128 samples |

`input-SHA256SUMS` records both ELF identities and the exact Linux shell NBF.
The NBF passes the maintained collision check for custom CSRs `0x800` through
`0x802`. `run_board.py` verifies the guest ELF, Linux NBF, control-program, and
loaded bitstream identities before measurement. `expected-bit.sha256` records
the bitstream extracted from the independently verified routed package.

Run the formerly failing placement first after staging and reloading the new
image. Require warmup completion, all result rows, native request exit zero,
`CORE[0] PASS`, and runner exit zero. Then use a recovered fresh boot for the
stable placement and the corresponding `e62165fa...` expected ELF hash. A
timeout or incomplete terminal sequence requires board recovery before the next
program.

## Accepted result

The routed package passed `verify_pynq_package.sh` with package SHA-256
`9a3e4b8e9bacfa2a323633759246d513519b2e438c563abc219c7350b6472237`
and bitstream SHA-256
`2ab6ec08860d07fe627ef079090a76c0604e1d6b40d4003fa9f5dd3a1fc8488b`.
Full timing signoff is WNS/TNS `+1.462/0 ns` and WHS/THS `+0.022/0 ns`.

Both 128-sample fresh-boot runs passed warmup, every result row, native request
exit zero, `CORE[0] PASS`, and runner exit zero:

| Placement | Median cycles | Median cycles/request | p05 | p95 |
|---|---:|---:|---:|---:|
| formerly failing `0x11e80` / `0x11ec0` | 611,716 | 74.672 | 589,600 | 647,379 |
| stable control `0x11f00` / `0x11f40` | 611,074.5 | 74.594 | 589,152 | 646,905 |

The independent-run median difference is 641.5 cycles, or 0.105% of the
control median. `board-analysis.json` records the full summaries and hashes of
both raw logs and terminal-status records.
