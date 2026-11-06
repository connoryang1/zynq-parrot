This directory records the correction of the tagged benchmark's instruction-wake control and the resulting FPGA measurement. It prevents a hook-counter-only kernel mode from being mistaken for instruction replay and binds future logs to the exact kernel mode used.

# Corrected instruction-only wake replay

## Confirmed harness mismatch

The benchmark previously mapped `instruction-wake` to kernel mode four. The
maintained patch stack defines mode four as a selection-time hook counter that
deliberately emits no shared-prefix trigger. The earlier two-boot
`3771.5 [588.5,5304.5]` wake-to-load result is therefore superseded as
instruction-replay evidence.

An intermediate mode-six correction was also rejected before any accepted
sample: mode six triggers instruction replay but patch 0010 additionally issues
late physical data replay. Its live hook-count mismatch stopped trial one, the
run was interrupted, and the board was hard-recovered.

Patch `0021-blackparrot-dedicated-wakeup-instruction-replay.patch` adds mode
thirteen: one successful-wakeup `0x5c0` write, one hook count, no data command,
and no selection fallback. The benchmark prints `kernel_mode=13
expected_hooks=1`, and the strict analyzer requires this binding for
`instruction-wake`; historical unlabeled logs and a mode-four substitution are
rejected.

## Validation and artifacts

All 190 host tests pass. The exact kernel links mode thirteen to
`try_to_wake_up+0x44e` at `0xffffffff8003e060`, where `csrw 0x5c0,zero` is
immediately followed by hook accounting. Reserved Linux and OpenSBI `.text`
CSR scans pass. The immutable artifacts are under
`/home/coyang/fpga-artifacts/context-resume/corrected-instruction-wake-20261106/`:

- bitstream: `1caf54e7...949f`
- shell NBF: `e2707672...98fb`
- benchmark ELF: `3be97cc9...9a6a`
- transfer: `74d1728a...dac1`

Two separately recovered FPGA boots each complete 512 balanced trials, exact
mode/hook and zero-data-counter gates, and terminal parent/CORE/BSG PASS.
Transcript hashes begin `c2f5731b` and `7974cecc`; their status files are
byte-identical at `5b84da7e...70d3e`.

Boot-stratified pooling reports `-460 [-1885.25,685.25]` wake-to-load cycles
saved, `8.5 [-5.5,21.5]` target-load cycles saved, and `-671.75
[-4105.75,2622.5]` full-roundtrip cycles saved. The actual direct instruction
trigger has no resolved benefit and agrees with the zero-data hardware-follow
result. The next useful boundary is instruction-prefix coverage and residency
for this exact post-wake stream, not additional trigger-path surgery.
