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
loaded bitstream identities before measurement. It deliberately cannot run
until `expected-bit.sha256` is created from a routed and verified package.

Run the formerly failing placement first after staging and reloading the new
image. Require warmup completion, all result rows, native request exit zero,
`CORE[0] PASS`, and runner exit zero. Then use a recovered fresh boot for the
stable placement and the corresponding `e62165fa...` expected ELF hash. A
timeout or incomplete terminal sequence requires board recovery before the next
program.
