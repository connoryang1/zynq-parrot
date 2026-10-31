This directory records the independently scheduled instruction-plus-data preview
candidate and its best-case Linux validation. Results are added only after their
exact revision and acceptance boundary are known; no Linux speedup is claimed yet.

# Joint preview best-case validation

## Source checkpoint

- Routed RTL source: top `009b4de22131bafa0f5f07df830cc487425e8278`,
  BlackParrot `1b4126d60208a990f49b06997e61424476238079`.
- Route job: `20261031T135833Z-009b4de2`, configuration
  `e_bp_unicore_zynqparrot_prefetch5_cfg`.
- The later Linux collateral commits do not alter the immutable routed RTL.

## First route result and corrected fit gate

The first route is rejected as the Linux fit gate, although its placement
failure is valid for the selected endpoint. Synthesis completed with zero
errors at 55,687 slice LUTs versus 53,200 available. Physical synthesis
combined 1,034 LUTs, but detail placement still required 11,531 slices while
only 10,940 were available and exited with `Place 30-487`.

The endpoint was not a one-variable comparison with the accepted instruction
image: `e_bp_unicore_zynqparrot_prefetch5_cfg` selects five D-UCE request slots
and also changes `num_contexts` from four to ten. The one-hart Linux scheduler
benchmark does not use the historical ten-context hardware workload, and the
accepted full-core feature regression already runs with two resident/four
logical contexts. The controlled reroute therefore keeps exact top
`009b4de2` and BlackParrot `1b4126d6` RTL but selects
`e_bp_unicore_zynqparrot_prefetch_cfg`, which retains four request slots and
four logical contexts. No RTL reduction or performance compromise is implied
by that correction.

## Accepted pre-route gates

- The focused UCE run at `/dev/shm/zp-joint-bestcase-uce-physical` passes a
  four-entry physical queue beside ten occupied ordinary hint slots, architectural
  demand priority, same-line discard, cancellation/drain, and L2-only replies.
- A clean `TRACE=1` two-thread/four-context full-core instruction replay run
  reaches its exact guest marker, `CORE PASS`, host `BSG PASS`, and `VALID RUN`
  at 20,608 retired instructions. The known post-PASS DPI finalization assertion
  does not invalidate the harness result.
- The Linux patch stack through `0007-blackparrot-select-preview-timing.patch`
  applies cleanly from the instruction-only kernel, applies idempotently, and
  compiles `arch/riscv/kernel/process.o`, `kernel/sys.o`, and
  `kernel/sched/core.o` with the pinned RV64 toolchain.
- The first object-build attempt stopped before these objects because host GCC
  used the full root `/tmp`. Repeating the exact build with a `/dev/shm` `TMPDIR`
  compiled all three objects. Future isolated kernel builds must set `TMPDIR`
  explicitly; the failed attempt is infrastructure evidence, not a source result.

## Best-case measurement shape

Both timing arms retain the same four page pins and 40 KiB eviction walk. The
measured target is exactly four dependent loads. Mode one emits physical hints
at exact scheduler selection; mode two emits immediately before `__switch_to`
to test whether later issue prevents tiny-L2 displacement. Groups zero through
seven cover both banks of all 16 L2 sets, and the complete analyzer requires all
16 timing/group cells plus final board PASS markers.

The completed-state oracle on the historical data-capable image bounds the
opportunity: 32 dependent data lines save 1,265.25 local cycles but only 2.66%
of wake-to-load, while combined instruction/data warming saves 2,044 local
cycles, about 4% of the full interval. The four-line hardware result is therefore
a timing/retention gate, not the final footprint-size recommendation.

## Data-only image preparation

- The instruction-only Linux tree was copied into `/dev/shm`, the complete data
  patch stack was applied there, and a full `Image` rebuild passed after the
  three directly changed objects had compiled. The resulting kernel SHA-256 is
  `2a9a2e15db3a80736e1ef1fb724c9d14d7edfaf6cd75d1df23d713f67b3ff18c`.
- The isolated OpenSBI build uses one hart and `BP_ICACHE_PREFIX_ENABLE=0`, so
  the first board sweep attributes any change to data preview rather than the
  shared instruction prefix. The payload contains exactly one copy of both the
  rebuilt kernel and the 64 MiB shell DTB. Executable-section CSR scans pass for
  Linux and OpenSBI.
- The generated Verilog memory had 14 sparse address directives. Every directive
  was checked inside `0x80000000`--`0x83ffffff` before rebasing, and the final
  8 MHz NBF SHA-256 is
  `77e13709ecc5a2880b4ad4d1be3d6b399a58032d29a7b31494a3198de5532aa3`.
- A whole-NBF CSR scan reported apparent uses of `0x802`--`0x807` in embedded
  data and initramfs words. This probe is rejected because it does not distinguish
  executable sections; the section-aware ELF scans above are the acceptance
  guard and prevent these data-word false positives from being treated as code.
