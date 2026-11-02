This directory documents Linux performance and miss-timing experiments on the routed 16 KiB L2 context-resume candidate. Raw board transcripts remain in durable artifact storage; this summary binds their identities, accepted conclusions, and workflow failures without copying large UART logs into Git.

# Sixteen KiB Linux data-preview result

## Exact image and integrity gate

All accepted runs use top-level `0d0609e31305c5d929385c34a5143bb5dce4e965`,
BlackParrot `174f2787a05ca48a6e4362fc59dc462d3d95572c`, routed bitstream
`a5f3a8acfed45325df06dc3925a31f0e606433ddb346e078ff495432dbbbded1`,
mode-one NBF `ae2924776233446e41a25e44866a41e5171efc76575216950104b0432ad9005c`,
benchmark ELF `8333e8d1517c85734a8b580e3d61041450b1e438662d89ce74a7383fe6027c09`,
and control program `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.

Before Linux measurement, `mt_l2_capacity_integrity_test` covered every line
of the two-bank, two-way 16 KiB L2, forced dirty eviction/refill across the
complete set range, and checked a second write epoch. A clean trace-enabled
full-top simulation passed at 29,370 normalized BP cycles, and the same NBF
passed the exact routed PYNQ-Z2 image. Durable evidence is under
`/home/coyang/fpga-artifacts/context-resume/l2-capacity-integrity-20261101/`.

## Fixed-arm Linux effects

The one-line experiment has two independent opposite-order pairs, 512 accepted
trials per arm, exact identities, and terminal guest/core/host PASS. Enabled
minus disabled improves the target load by 37.25 cycles with circular-block
95% interval `[-71.5,-22]`, but wake-to-first-use is unresolved at +7,298.75
`[-8,139.5,+15,828.75]` and roundtrip is unresolved at -154.75
`[-551.25,+145.25]`. Strict analysis SHA-256 is
`4cc138bc6a736052885bf5b0bea882d6ac0d102a74aa89e2eb7c024fadf8434b`.

The matching four-line experiment also has two opposite-order pairs. Its four
dependent loads improve by 29 cycles `[-35,-28.5]`; wake-to-first-use remains
unresolved at -14,956.25 `[-16,366,+6,306.25]`; roundtrip improves by 561
cycles `[-930,-141.5]`, about 0.39%. The wake endpoint is bimodal near 28--30k
and 49k cycles: only 7--13 samples changing phase can flip an arm median by
roughly 15k, so the large first-use point is not accepted as a mechanism gain.
Analysis SHA-256 is `5dc26e7d3b6cf0b7e6dc266b99d9770628eac4e9d9d70c827aaf36ef445835d4`.

A strict same-image comparison finds no incremental local-load scaling from
one to four hints: four-minus-one is +8.25 cycles with block interval
`[-7,+42]`. First use and roundtrip are also unresolved. Comparison SHA-256 is
`6ffb5180bf67e97845171ca1527bc5063e0b56fcb0c9242b874faad18b4fdab8`.

## Paired phase controls

Interleaved `[off,on,on,off]` controls cancel the timer/scheduler phase but
answer different questions depending on replay isolation:

- With symmetric `fence.i`, four enabled hints save 66.5 load cycles
  `[58.5,70.25]`, yet first use is 248.5 cycles slower
  `[157.5,415.75]`; roundtrip is neutral. One line has no measured local-load
  saving and is 420.25 cycles slower to first use `[348,570]`. These runs also
  include cold instruction refill and therefore do not measure data alone.
- With persistent replay state, one-line first use and load effects are
  unresolved. Four lines save 53.75 load cycles `[45.75,60.75]`, while first
  use remains unresolved and paired roundtrip regresses. Persistent
  interleaving intentionally equalizes instruction warmth and is a data-path
  diagnostic, not an instruction-replay performance claim.

The accepted paired analyses are in
`/home/coyang/fpga-artifacts/context-resume/l2-16k-four-line-linux-ab-20261101/`.

## Exact miss chronology

The bounded physical miss recorder was extended to current mode one and run on
fresh disabled and enabled boots. Both captures have exact identities, no
overflow, and TRACE/CORE/BSG PASS. Disabled records the four target demand
misses 79, 125, 169, and 212 cycles after entry. Enabled still records all four
target demand misses, at 113, 137, 159, and 180 cycles after entry, and has no
recorder-visible target event before entry. Aggregate load time improves from
215 to 183 cycles.

This proves the current selection-time hints do not install completed target
lines before first use in this captured handoff. The 32-cycle saving is
consistent with demand joining partially completed detached work; the recorder
does not expose hint issue/completion directly, so that join interpretation is
an inference. Strict trace-pair analysis SHA-256 is
`6a75579346e5c225d9fca70fc3a5e382dc13ee479c9c78c0e60c14481ddf92b9`;
raw evidence is under
`/home/coyang/fpga-artifacts/context-resume/l2-16k-wake-early-data-trace-20261101/`.
That directory's retained evidence summary has SHA-256
`84e6f6180024cfa22b3d440079337a79c33255baa8ccf67f0a9161920e09f24b`.

## Workflow findings

PYNQ's boot service can overwrite an overlay loaded before startup finishes.
Every accepted arm therefore uses a full power cycle, the maintained readiness
wait through at least 90 seconds uptime, exact restaging, loaded-BIT hash gate,
and fresh overlay load. One correct-readiness boot stopped at NFS initialization
and remains an intermittent liveness observation; later fresh boots passed that
point repeatedly.

A concurrent checkout twice overwrote staged board artifacts. Exact package
and BIT gates rejected the wrong identities before measurement, but stage and
load are not one atomic cross-checkout operation. One local shell also invoked
the loader after staging failed because it lacked `set -e`; subsequent stage
and load sequences are fail-fast. Two trace transfers were rejected after Make
directory chatter and then 1,092-character commands left the guest at its
continuation prompt. The accepted transfer uses no Make chatter and a maximum
580-character command. Both board runners now reject commands over 768
characters before launch.

## Next architecture gate

The evidence no longer supports more cache-capacity tuning. Sixteen KiB is
correct, routed, and sufficient for the directed retention gap, but Linux first
use remains late. The next bounded candidate should issue the registered data
addresses at successful wakeup rather than scheduler selection, suppress the
old selection batch, and preserve the current 16 KiB route. A later hardware
batch/context-tag command should replace four serialized scheduler CSR writes
if true wakeup timing still cannot repay its critical-path cost.
