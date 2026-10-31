This directory records the independently scheduled instruction-plus-data preview
candidate and its best-case Linux validation. Results are added only after their
exact revision and acceptance boundary are known. The accepted data-only result
shows a small local load-body gain but no resolved wake-to-load speedup.

# Joint preview best-case validation

## Source checkpoint

- Initial confounded routed RTL source: top `009b4de22131bafa0f5f07df830cc487425e8278`,
  BlackParrot `1b4126d60208a990f49b06997e61424476238079`.
- Route job: `20261031T135833Z-009b4de2`, configuration
  `e_bp_unicore_zynqparrot_prefetch5_cfg`.
- The later Linux collateral commits do not alter the immutable routed RTL.

The controlled accepted implementation is exact job
`20261031T160854Z-f79221bc`, top
`f79221bcf4d7a5bdd42ec0b315a3edc957d8f3bf`, BlackParrot
`1b4126d60208a990f49b06997e61424476238079`, and configuration
`e_bp_unicore_zynqparrot_prefetch_cfg`. It uses the same four logical contexts
and four D-UCE request slots as the instruction checkpoint.

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

The controlled image places at 50,308/53,200 LUTs (94.56%), 24,959
registers, 94 BRAM tiles, and 11 DSPs. Automatic post-route physical
optimization improves setup from `-0.257 ns` to final WNS/TNS `+0.241/0 ns`;
WHS/THS is `+0.037/0 ns`, routing is complete, and bitstream generation passes.
The verified package/bitstream SHA-256 values are `9912f313...b629` and
`e97e0517...2381`. The launcher's original FAIL was a report-selection bug: it
read the stale pre-physopt timing report. The fixed, revision-checked recheck
path and exact route metadata are retained under `route/`.

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

Each enabled trial must observe exactly one scheduler hook, and each disabled
trial must observe zero. The initial exact ELF exposed that arming before the
40 KiB eviction walk lets a timer preemption issue an unintended hint batch.
Arming after eviction still cannot prevent a later timer preemption inside the
irreducible handoff, so this best-case benchmark reports and retries
contaminated attempts. Only clean attempts enter the 512 rows. The accepted
clean-handoff ELF SHA-256 is
`5033ffdbb1bb5b96bebd8d2003d5b6bf2eb7f20ea2e8edaccf60a6da21cedeb8`; its
transfer SHA-256 is
`a7e858107c132508da071d2c56c44b55cae4d1b5557b600f3aa1d60920a5dc1c`.

A cell is accepted only with all 512 ordered timing rows. The fourth analyzer
regression rejects a truncated 128-row transcript even when its synthetic PASS
markers remain present.

`linux-tests/run_scheduler_physical_preview_sweep.py` uses the reviewed
serialized interactive runner, verifies the guest ELF hash, executes every one
of the 16 cells exactly once, alternates early/late order by group, and powers
off for final core/host markers. Its two plan tests plus the five analyzer tests
originally passed; the final suite has six runner/plan and five analyzer tests,
including dual prompts, repeated UART carriage returns, and disjoint suffix
recovery.

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

## Accepted physical data-only result

The full matrix was completed across two recovered boots because the first
long run lost timer/preemption progress after ten accepted cells. Its next cell
required zero retries versus 45--67 in every preceding cell, printed `rc=0`,
and then never returned a shell prompt; that abnormal cell and everything after
it were rejected. The immutable raw log is retained. A derived prefix contains
exactly the first ten normal-liveness cells (5,120 rows, SHA-256
`ad9bd0b4...897f0`), and a fresh suffix reran cells 10--15 with 48--60 retries
each before clean final `CORE PASS` and `BSG PASS` (SHA-256
`cc453e48...7fa1e`). Across the 16 accepted cells, 857 preempted attempts were
reported and excluded, 45--67 per cell.

The strict set-stratified result is:

- Early issue saves 8.5 cycles in the four-dependent-load body, with 95%
  bootstrap interval `[5.5, 10.5]` cycles.
- Late issue saves 11 cycles in that body, interval `[11, 12]` cycles. Across
  cell medians this is roughly 6.1% of the 185-cycle disabled load body.
- Wake-to-load does not improve: early saved cycles are `-842` with interval
  `[-1517.25, 56]`; late is `-62.25` with `[-770.5, 942]`. Negative means the
  enabled arm was slower. The median disabled wake-to-load cell is about
  32,103 cycles for late issue, so the resolved 11-cycle local benefit is only
  about 0.034% of that interval before scheduler noise.
- Late versus early load-body effects vary by L2 set group; no timing mode wins
  every group. Late is the better pooled candidate, but the result does not
  justify choosing a single exploratory group.

This image deliberately sets `BP_ICACHE_PREFIX_ENABLE=0`; it tests the data
lane on joint-capable hardware, not combined instruction-plus-data replay. The
result proves useful data arrives by first use and that later issue retains
slightly more benefit, but four 16-byte hints are too small a target to move the
full Linux handoff measurably. The strict analyzer output and compressed raw
transcripts are under `physical-sweep/`.

One recovered boot also failed before userspace with an OpenSBI nested illegal
CSR `0x34b` report, while the preceding three and following recovered boots
reached a shell. That nondeterministic fault and the later timer-loss run are
retained as stability limitations; neither contributes timing samples.

## Combined instruction-plus-data follow-up

`splice_opensbi_nbf.py` constructs a fail-closed combined image at the natural
`0x80200000` payload boundary. It takes 17,024 OpenSBI records from instruction
donor NBF SHA-256 `d7a2964c...e235` and proves all 1,861,846 kernel/DTB records
come unchanged from the accepted data NBF. Boot-control preambles must match,
selected addresses must be unique, and the base timer/control tail is retained.
Three unit tests pass, the exact partitions compare byte-for-byte, and combined
NBF SHA-256 is `8cb1261a...3592`. The image booted Linux to a root shell.

The long-run prompt loss recurred after plan index 10, so the same conservative
recovery boundary was used: the abnormal cell was rejected, the first ten
normal cells were derived at SHA-256 `5e4ebd69...15ed`, and a fresh six-cell
suffix with SHA-256 `a2e21457...5bfe` reached final CORE/BSG PASS. All accepted
cells had 43--62 retries, 826 total.

Instruction replay is active in both data-enabled and data-disabled arms of
this matrix. The paired result therefore estimates the incremental data effect
while instruction replay is present, not instruction replay's total effect:

- Late data preview saves 12.5 load-body cycles, 95% interval `[11, 15]`.
- Early data preview saves 3 cycles, interval `[1.25, 5.5]`.
- Late wake-to-load saved cycles are `-88.5`, interval `[-814.5, 542.75]`;
  early is `-635.75`, interval `[-1350.75, 65.5]`. Neither resolves a gain.
- The median disabled wake-to-load cell is 32,107.75 cycles for combined late
  versus 32,103 for data-only late. This near-equality is only a cross-boot
  observation, not a paired proof that instruction replay has zero effect.

The earlier 3.25% instruction-only result used a different persistent futex
pair and cannot be added numerically to this result. A direct instruction
on/off comparison needs alternating matched images or a runtime instruction
toggle in this exact benchmark. The complete combined analysis and provenance
manifest are retained under `physical-sweep/`.

## Runtime-gated total-joint candidate

The next kernel candidate gates the shared instruction trigger on the same
incoming-task `bp_preview_phys_mode` byte that controls physical data preview.
Mode zero is therefore a matched instruction-and-data-disabled arm; modes one
and two enable the exact old 16-line instruction table plus early or late data
preview. This changes no RTL and preserves page registration, pins, eviction
traffic, task pair, and benchmark binary across the comparison.

The isolated Linux 6.6 build passes and disassembly proves a byte load and
zero-test branch around the sole `csrw 0x5c0, zero` in `__schedule()`. The
kernel `Image` and `vmlinux.bin` SHA-256 are both
`e9496891...c7cb5`; the reused 64 MiB DTB remains exact at
`bfa8247a...906f`. The old 16 table was recovered directly from accepted donor
NBF `d7a2964c...e235` and compares entry-for-entry with the generated header.
The donor-derived OpenSBI payload is `57b2acd9...a232`, and the resulting 8 MHz
candidate NBF is `9b94fee3...9a4d`. Executable-section CSR collision scans,
five strict analyzer tests, six board-runner tests, and three NBF-splice tests
pass. FPGA boot and timing results are recorded below.

Two build guardrails were exposed before board staging. A direct kernel make
without Buildroot's `BR_BINARIES_DIR` expanded the configured initramfs path to
missing `/rootfs.cpio`; rerunning with the retained exact rootfs succeeded.
Also, patch 0008 changes the scheduler hunk introduced by patch 0001, so the
old reverse-patch idempotency probe no longer recognized a completed stack.
Staging now recognizes the exact trigger in `core.c`; two consecutive complete
stack staging calls pass. An initial firmware candidate built from the old
canonical SDK's unpatched OpenSBI source was rejected before FPGA use because
it lacked the donor's `fw_base.S` and `sbi_hart.c` changes.

The first donor-correct candidate booted Linux, but its baseline SDK rootfs
contained `test_shutdown.sh` and powered off cleanly before a shell benchmark
could run, so it is not performance evidence. The replacement begins from the
exact accepted data-kernel build (`2a9a2e15...f18c`) and preserves its
decompressed embedded initramfs byte-for-byte at SHA-256
`0aab5597...e1c1`; only patch 0008 is added. A timestamp-only attempt was
rejected because changing `BR_BINARIES_DIR` invalidates Kbuild's recorded
command and regenerates `usr/initramfs_inc_data`.

The first board-stage sequence copied and hash-verified the now-rejected
baseline-rootfs candidate and then immediately power-cycled for mandatory recovery.
After boot and overlay load the same pathname hashed as `832239fd...0bd7`, so
the image was rejected before any guest execution. A not-yet-durable filesystem
write is the suspected cause, but the hash transition alone does not prove it.
Future board image staging occurs after power recovery and requires an explicit
remote `sync` plus a second hash check before the serialized runner starts.

## Runtime-gated total-joint FPGA result

The corrected image booted Linux on the accepted routed bitstream
`e97e0517...2381`. The strict matrix completed all 16 planned cells with 512
accepted trials per cell. As in the two prior matrices, the console lost its
prompt after the tenth completed cell; that unstarted cell was rejected, the
first-ten log was preserved at raw SHA-256 `65b7dc6b...9505`, and a mandatory
power-cycle, readiness wait, overlay reload, and NBF re-hash preceded the
disjoint six-cell suffix. The suffix raw log is `65e7bdb1...9594`, rejects no
overlapping cells, and ends in CORE/BSG PASS. The benchmark rejected 776
timer-preempted attempts across both boots.

The stratified paired results are:

- early joint warming: 4.25 `[1,5.75]` cycles saved in the four-load body and
  536.75 `[-267,1169.75]` cycles saved from wake to the end of those loads;
- late joint warming: 4.75 `[2.5,7]` local cycles and
  159.5 `[-760,912.5]` wake-to-load cycles saved.

The early and late full-handoff intervals both cross zero. Using the median of
the eight disabled cell medians only as a representative denominator, their
point estimates are about 1.15% and 0.35%, respectively. The accepted claim is
therefore a small local demand-load improvement, not a Linux context-switch
speedup. Exact compressed logs, status records, and strict analysis SHA-256
`2718dbfc...e6a6` are retained in `physical-sweep/`; the compressed first-ten
and suffix logs hash to `b6b84e2b...c4e9` and `ec426b41...5096`.

A post-run unit-test command invoked the three test files from the repository
root and failed import collection because `linux-tests/` was not on the Python
module path. This was a command-location error, not a test failure; invoke the
same modules with `linux-tests/` as the working directory.
