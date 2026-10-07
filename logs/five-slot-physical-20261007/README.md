# Five-slot physical acceptance and adjacent-word regression

"Slot" throughout this record means one detached-prefetch transaction entry.
Both the five- and ten-slot images retain two resident architectural register
banks and ten logical contexts; slot count does not name the resident-thread
count.

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

A later alternating-order rerun establishes the matched buggy-image medians:

| Streams | Serial demand | Serial prefetch | Software interleaved | Hardware switching |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 60,083 | 82,608 | 62,244 | 69,893 |
| 3 | 60,025 | 82,488 | 60,943 | 73,137 |
| 4 | 60,060 | 82,510 | 60,678 | 74,377 |
| 10 | 60,375 | 82,411 | 62,851 | CORE FAIL |

All 45 accepted runs pass guest, core, and host checks. Each passing cell has
three samples; the largest range is 122 cycles, or 0.15%, and the separate
ten-stream hardware gate reproduces `CORE FAIL`. The exact bitstream and
46 MB CMA control program are pinned by SHA-256 in
`buggy-five-slot-matrix/analysis.json`.

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

The focused sector diagnostic now isolates that causal step directly. It
issues one narrow hint, waits beyond the response interval, then independently
times the first word at offset 0 and its adjacent word at offset 8. On the
corrected five-slot simulator, all 16 first-word and all 16 adjacent-word
intervals are 3 cycles. On the physically loaded buggy ten-slot control, three
complete repetitions (48 sectors) retain a 3-cycle first word but take a
42-cycle median for the adjacent word, with a 42--43-cycle range. Three more
repetitions on the exact prior five-slot, 20 MHz image reproduce the 3/42-cycle
medians across another 48 sectors, with a 42--45-cycle adjacent range. Every
run passes its guest value checks plus core and host completion checks. This is
a 39-cycle median penalty per node and directly observes the ordinary-memory
fallback inferred from the pointer benchmark; it is not merely a correlation
with total runtime. The five-slot control also gives the pending corrected
image a matched slot-count and clock-frequency A/B baseline.

The direct penalty also predicts the end-to-end regression. At 1,280 nodes,
39 extra cycles per adjacent load is 49,920 cycles. Comparing the accepted fast
medians with the repeated buggy five-slot medians gives:

| Mode | Streams | Fast | Broken | Increase | 49,920 / increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Serial prefetch | 2 | 30,821 | 82,608 | 51,787 | 96.4% |
| Serial prefetch | 4 | 30,891 | 82,510 | 51,619 | 96.7% |
| Serial prefetch | 10 | 31,005 | 82,411 | 51,406 | 97.1% |
| Software interleaved | 2 | 14,167 | 62,244 | 48,077 | 103.8% |
| Software interleaved | 4 | 8,413 | 60,678 | 52,265 | 95.5% |
| Software interleaved | 10 | 8,077 | 62,851 | 54,774 | 91.1% |

The corresponding demand medians differ by only 7--30 cycles, bounding broad
image-to-image cycle drift. The single measured adjacent-word penalty therefore
accounts for essentially the entire 48,077--54,774-cycle prefetch regression;
the residual varies with scheduling overhead and the older image's different
clock configuration.

The exact board NBF SHA-256 is
`817dfa78b1516ef70458a71cfc2a7cca590dd5b911dee2dd0bcc2ebf49a7d966`.
Build inputs, disassembly, manifests, raw simulator and physical transcripts,
and the reproducible parser are retained under `sector-diagnostic/`. The same
NBF is staged on the board for the corrected-image comparison. That comparison
still remains pending the live `a16a9532`/`4f56fba7d` FPGA implementation.

## Corrected five-slot physical result and terminal-switch race

The routed 20 MHz image at top `a16a9532` / BlackParrot `4f56fba7d`, with
bitstream SHA-256
`e041ad3bcc0b2619c348e4bf19ea209a628586fe8bc5b839e95535d01215512b`,
physically confirms the adjacent-word repair. Three checked
samples per cell give these medians:

| Streams | Serial demand | Serial prefetch | Software interleaved | Hardware switching |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 60,077 | 31,018 | 14,195 | 17,978 |
| 3 | 60,001 | 30,974 | 9,713 | 21,178 |
| 4 | 60,070 | 31,023 | 8,415 | 22,288 |
| 10 | 60,384 | 31,030 | 62,642 | `CORE FAIL` |

Thus software interleaving reaches 4.23x, 6.18x, and 7.14x demand speedup at
two, three, and four streams. Ten streams exceed the five-entry detached-hint
capacity and thrash, so software interleaving falls back slightly below demand.
Hardware switching is best at two streams (3.34x demand speedup); additional
nonresident register movement outweighs the extra overlap at three and four
streams. All 45 non-gate samples pass guest, core, and host checks. The three
ten-stream hardware repetitions fail before printing a benchmark result.

The ten-stream failure is independent of the adjacent-word repair. A no-hint
ten-stream hardware program passes, as does an initial-hint-only control;
repeated successor hints expose the failure. Adding instructions between the
final result publication stores and the final context switch gives an exact
physical threshold: seven NOPs fail and eight pass. Moving the eight NOPs
before the stores or after the switch does not help, and reloading `ra` twice
after the switch does not help. A diagnostic trap handler on the seven-NOP
case reports illegal instruction at PC zero with restored context zero's
`ra = 0`, after the benchmark result has already been computed.

The backend detector allowed CSR `0x800` context switches to issue while
`mem_busy_i` was asserted. The resident fast path has no context-cache drain
state, so a switch immediately following ordinary stores could hand off before
their local pipeline effects were safe. This is an ordering bug, rather than a
detached-prefetch response delay: only the placement after ordinary result
stores matters, and detached hint credits are intentionally excluded from the
local ordered condition.

BlackParrot `ee522c10c` now interlocks context switches on
`mem_busy_i || !mem_ordered_i`; top commit `c43549d3` records the submodule
update. It also makes the existing fence hazard cover `mem_busy_i`. The exact
zero-NOP ten-stream simulator passes at 97,237 cycles. A matching 20 MHz FPGA
route is in progress; physical correctness and the post-fix 2/3/4-stream cost
remain acceptance gates.
