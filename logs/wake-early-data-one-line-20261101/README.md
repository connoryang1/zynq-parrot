This directory evaluates whether moving one physical data hint earlier than the accepted late-data experiment produces a measurable Linux first-use benefit. It preserves the same one-line FIFO handoff, instruction table, routed FPGA, and four-fresh-boot fixed-arm protocol so hint timing is the intended mechanism change.

# One-line wake replay plus early data

## Predeclared mechanism

The candidate reuses existing runtime mode one. Instruction replay begins when
the target is successfully woken, while the existing mode-one physical-data
hook issues one hint when the scheduler selects that task. This moves data
earlier than mode six's pre-register-switch hook without changing the absolute
instruction table, kernel layout, OpenSBI, rootfs, DTB, or RTL.

The deployable NBF is derived from the accepted mode-six futex-v1 image with
three fail-closed 64-bit record replacements. At physical `0x8023dc0e` and
`0x8023dc76`, `li a5,6` becomes `li a5,1` in the two successful-wakeup paths.
At physical `0x80a13b58`, the selection-time suppression comparison changes
from mode six to mode one. Complete-file `cmp -l` reports only six changed
ASCII characters, exactly the two hexadecimal digits in each 16-bit
instruction encoding. The original source-built experiment retained the
audited `try_to_wake_up` and `__schedule` symbol addresses; it was used only to
locate and check semantics, not transplanted into the accepted binary.

Exact prepared identities are:

```text
base mode-six NBF: 93b2e29de83be627631a6cb6e78b2a5529f9a42c89cb365894cfe7138a028629
candidate NBF:     ae2924776233446e41a25e44866a41e5171efc76575216950104b0432ad9005c
benchmark ELF:     8333e8d1517c85734a8b580e3d61041450b1e438662d89ce74a7383fe6027c09
fast transfer:     6ce18f6c76eba4ac2e17c809a63fecbb81301d37f4711861119f6771b45181ca
control program:   2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30
bitstream:         a070df7f2d69b86e745a9b915798e704ac4ee2255e97d3c50e3aa1a4f4ba3ce9
compressed NBF:    3644bb1d547d07ea9f7b67935d9f76fd472d1683a4fa53b289dd0a2daa62949f
```

The compressed candidate is durable at
`/home/coyang/fpga-artifacts/context-resume/wake-early-data-one-line-20261101/`;
streamed decompression reproduces the candidate NBF hash above. The 47 transfer
chunks reconstruct the benchmark ELF byte-for-byte.

## Acceptance protocol

Use group seven, one target line, FIFO policy, persistent replay state, and
fixed enabled or disabled arms. Run two independent opposite-order pairs:

1. enabled, then disabled;
2. disabled, then enabled.

Every arm requires a complete board power cycle, PYNQ readiness wait, exact
overlay restage and hash gate, 512 ordered accepted rows and tails, the expected
mode-one hook count, no kernel-failure marker, and child/parent/cell/core/host
PASS. Wake-to-load is the primary endpoint. Local load cycles determine whether
the hint still creates a useful fill; wake-to-entry separates scheduler cost;
roundtrip is secondary throughput evidence. Negative enabled-minus-disabled
cycles mean preview is faster.

This is a deliberately favorable one-line mechanism test. A resolved gain does
not establish a general Linux or application speedup; a locally useful fill
without a wake-to-load gain falsifies scheduler selection as sufficient lead
time for this workload and motivates a true wakeup-time data path.

## Preparation notes

An initial source variant changed the scheduler-selection mode-one comparison
directly to mode six. Its extra compressed immediate shifted later code, so it
was rejected before NBF construction or FPGA use. The selected mode-one design
keeps the three patched instructions at their original addresses.

One patch dry-run command was launched after a Python test invocation from the
wrong import directory failed; shell cleanup then briefly reapplied patch 0009
and left `.orig` backups. Exact baseline hashes exposed the state immediately,
the patch and backups were removed, and all five audited source hashes now
match the saved baseline. The first clean guest build also used the unavailable
default compiler name and stopped before producing an ELF. The accepted build
uses the explicit Buildroot GCC path, matching the established guardrail.

Before FPGA launch, 79 harness tests and all 124 discovered Linux-test tests
pass. The board remains untrusted after the prior guest shutdown and must be
fully recovered before the first arm.

The second arm's first restage stopped before overlay load because only 28 MiB
remained and atomic replacement needed space for a second 69 MiB NBF. The
existing candidate retained the exact expected hash and the partial incoming
file had its private staging name. Both recoverable board copies were removed,
the durable local archive remained verified, and restaging then passed. Later
arms verify and remove the exact prior candidate before atomic restaging; no
run used a partial or stale image.

## FPGA result

All four fresh arms pass exact NBF, ELF, transfer, control-program, and
bitstream identities; `lines=1`; 512 ordered rows and tails; expected mode-one
hook counts; kernel-failure screening; and child/parent/cell/core/host PASS.
The first enabled arm filters one asynchronous double-hook attempt; all other
arms filter zero. Strict analysis SHA-256 is
`8b3dd59a68421ba494b7a380cc7298dadaa81e6b9e76c6265243d3eff510953c`.

The replicate-stratified enabled-minus-disabled results are:

| endpoint | cycles | IID 95% interval | block 95% interval |
| --- | ---: | ---: | ---: |
| wake to entry | +41.75 | [-13,164.5, +15,048.75] | [-8,248.5, +11,804.75] |
| one dependent load | +4.5 | [0, +6] | [-18, +22.5] |
| wake to first use | +2.75 | [-11,340.5, +14,083] | [-7,981.25, +8,451.75] |
| complete roundtrip | -1,056.25 | [-2,003.5, -603.5] | [-1,792.5, -742] |

Negative means enabled is faster. Pooled roundtrip medians are 144,794.5
enabled and 145,882.5 disabled, a 1,088-cycle or 0.75% reduction; the
replicate-stratified reduction is approximately 0.72%. Wake-to-load is neutral
at the point estimate and unresolved. Unlike the accepted late one-line image,
the earlier hint no longer improves the target load.

An independent strict early-minus-late effect comparison has SHA-256
`6ef427d514ea52bda0c430fa58a843f4bd4b290b382f8319d3fe07ad07b64219`.
Moving the hint earlier worsens the local-load effect by 41.5 cycles with block
interval `[11,58.75]`, proving the late image's useful fill is lost before
demand. Earlier issue improves the total roundtrip effect by 756.5 cycles with
`[-1516.75,-259.75]`, driven primarily by a 387-cycle improvement in the
return-handoff partition (`[-640.75,-81.25]`). Its incremental wake-to-load
shift is -7,978 cycles but unresolved at `[-20761.75,7379.25]`.

This exposes a timing tradeoff: the late hint survives until first use but can
leave work near the architectural handoff, while the earlier hint clears that
tail at the cost of losing the line. Neither timing demonstrates faster first
use. The next useful architecture work is direct issue/completion/first-use
timing or a retained/midpoint data path; simply issuing still earlier is not
supported by this evidence.
