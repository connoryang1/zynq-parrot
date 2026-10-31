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

A later combined verification command made the inverse location mistake: it
ran from `linux-tests/` but named the CSR checker as root-relative `tools/...`.
Both scans failed to start, then the newline-separated shell continued to 28
passing unit tests and returned zero. That aggregate exit is not CSR evidence;
run each collision scan separately from the repository root (or use `../tools`)
and require its own zero exit.

## Old-16 exact-kernel coverage audit

The total-joint run used the accepted old-16 table from the earlier
instruction experiment. A replay-disabled `to-peer` capture on the exact joint
kernel records 222 I-side and 15 D-side accepted misses over 23,386 cycles with
no overflow, but none of the old 16 physical lines appears. The earlier
instruction experiment observed 11 configured lines on this same persistent
futex capture shape. The raw run ends in TRACE_PASS, runner exit zero, CORE
PASS, and BSG PASS.

An initial local audit omitted Linux's 2 MiB physical load offset and produced
false filesystem symbol mappings. The hardware trace's known scheduler CSR
location exposed the error before commit. The corrected mapping, rejected
interpretation, and exact hashes are in `old16-exact-kernel-audit.txt`.

This narrows the accepted result: the data side and all same-boot controls are
valid, but the run did not exercise a covered instruction best case. The next
joint image must train from a replay-disabled trace of this exact kernel and
rebuild OpenSBI without relinking the kernel. Every candidate table must prove
exact-trace coverage and use the recorded physical load offset during symbol
resolution.

## Exact-kernel post-trigger prefix result

`select_icache_prefix_from_trace.py` fail-closed on overflow, missing PASS,
record-count mismatch, absent start line, and short suffixes, then selected the
first 16 unique I-side misses beginning with observed post-trigger physical
line `0x80a1bac0`. The resulting table JSON is
`exact-kernel-post-trigger-prefix16.json` with SHA-256 `796f17bc...6ce3`; no
I-cache set receives more than two entries.

The OpenSBI-only rebuild was validated against the old table first. Its binary
payload and packaged NBF reproduce accepted hashes `5dea920a...204c` and
`9b94fee3...9a4d` exactly; ELF-only differences are build-path debug strings.
The candidate changes 44 firmware bytes before the 2 MiB payload boundary and
compares equal thereafter, so the kernel and DTB remain exact. Candidate NBF
SHA-256 is `07b9fed7...f9b`. Separate kernel and OpenSBI executable-section CSR
scans pass. The whole-NBF scan repeats known embedded-data false positives and
is not executable-code evidence.

The strict 16-cell FPGA matrix rejected 798 timer-preempted attempts and used a
hashed first-ten-cell prefix plus a recovered disjoint suffix ending in
CORE/BSG PASS. Results are:

- early: 5.5 `[3,7]` local load cycles saved, but `-220.25
  [-1071,442.25]` wake-to-load cycles saved;
- late: 6.5 `[3.5,8]` local cycles, but `-288.5
  [-1564.5,292.25]` wake-to-load cycles saved.

The candidate is rejected: its full-handoff point estimates are harmful and
unresolved. It was trained on the exact kernel but on the persistent-futex
capture path, so one useful instruction experiment remains—capture and train
the exact pipe/clean-handoff path. Exact analysis SHA-256 is
`3435510b...9266`; compressed first-ten and suffix log hashes are
`cd15d07a...dd31` and `e34cc521...b640`.

## Exact pipe-trained 12-line result

`scheduler_physical_preview_trace_capture.c` reproduces the benchmark's 16
warmups, 40 KiB eviction loop, disabled preview bookkeeping, pipe wake, and
four dependent target loads. The parent clears and arms the physical miss
recorder immediately before the final wake; the child disarms immediately
after the loads. The exact FPGA run records 144 I-side and 65 D-side misses in
25,984 cycles without overflow and ends in TRACE/CORE/BSG PASS. Raw compressed
trace SHA-256 is `c02c30ff...ad1`; status is `03220a5a...fead7`.

The first 12 unique I-side misses beginning at observed post-trigger line
`0x80a1bac0` cover context-switch core code, `switch_mm`, `mm_cid_get`, FPU
save, and `finish_task_switch`. Records after this point begin mixing
syscall-return/user or speculative-looking paths, so the experiment stops at
12 instead of filling all 16 hardware slots. Table JSON SHA-256 is
`ac0168ac...82f5`.

Candidate NBF SHA-256 is `f3a026b6...31a7`. All 1,865,933 memory records at or
above the `0x80200000` Linux load boundary compare exactly with the accepted
control; boot controls and the final 8 MHz timer write also match. Separate
kernel and OpenSBI executable-section CSR scans pass. The shorter table shifts
the OpenSBI link layout, so broad byte-difference counts below the payload
boundary are not meaningful.

The first run completed ten cells and reproduced the known missing-prompt
boundary after a valid `group=4 late` exit. Its raw SHA-256 is
`0b6c3006...f71e`; the FAIL status `78667570...dd0` preserves the recovery
requirement. After a full power cycle, readiness wait, overlay/NBF reverify,
the disjoint six-cell suffix completed with runner, CORE, and BSG PASS. Its raw
SHA-256 is `855cb750...52ba`, status `1d5a45bd...5654`. The two logs contain
exactly 16 distinct cells and reject 830 timer-preempted attempts.

Strict analysis SHA-256 `bc65f94d...a087` gives:

- early wake-to-load: `-462 [-1218.25,183.5]` cycles saved; late:
  `-199.25 [-1101.75,539.5]`;
- early local loads: `9.5 [7,11]` cycles saved; late: `11 [9.5,11.5]`;
- early roundtrip: `2807.25 [416.5,4471.5]` cycles saved, about 2.26%; late:
  `3190.75 [123,4863.25]`, about 2.51%.

Thus the exact pipe-trained prefix still does not accelerate first useful
target work, but it produces a resolved two-switch roundtrip effect. That
secondary effect needs instruction-only isolation and replication before it
can be treated as a feature gain.

## Exact-kernel count-zero isolation

The matched data-only image changes only OpenSBI prefix initialization. It
writes no prefix entries and one count-clear command; all `1,865,933` emitted
Linux memory records at or above `0x80200000` and every non-memory boot/control
command compare exactly with the pipe-prefix-12 image. The final NBF SHA-256 is
`5fe0d96f...969f`; kernel and OpenSBI executable-section CSR scans pass.

The first boot completed ten cells with 39--72 rejected preemptions per cell,
then hit the established missing-prompt boundary. After full board recovery,
the disjoint suffix at plan index 10 completed six cells with 43--62 retries,
runner PASS, and final CORE/BSG PASS. The complete matrix rejects 874
timer-contaminated attempts. Compressed first-ten and suffix logs hash to
`a4cf5b50...355e` and `6925ef38...5c8e`; their status records hash to
`1db69804...3863` and `c4e3c9ef...472e`.

Strict count-zero analysis SHA-256 `5c96fd32...e16` gives:

- early: 2 `[1,5]` local-load cycles saved, 523.25 `[-233.5,1263]`
  wake-to-load cycles, and 874.5 `[-2267,2850.75]` roundtrip cycles;
- late: 8.5 `[6,10]` local cycles, 548.75 `[-152.75,1212.75]`
  wake-to-load cycles, and 19.25 `[-2612.75,2751.25]` roundtrip cycles.

The deterministic independent-bootstrap comparison against pipe-prefix-12
hashes to `5f4e3938...a89c`. Prefix replay adds `1932.75
[-960.75,5507.25]` early and `3171.5 [-631,6016.25]` late roundtrip cycles,
so the instruction contribution itself remains unresolved. It changes
wake-to-load by `-985.25 [-2017.5,-0.75]` early and `-748 [-1963,351.75]`
late; the early contrast is resolved harm at the target-resume boundary. This
keeps instruction replay as the leading explanation for the joint roundtrip
result but does not establish an instruction or context-switch speedup.

## Pipe experiment workflow corrections

The first trace build used the Makefile's unavailable default cross compiler
after a clean, so no stale executable was accepted. It was rebuilt with the
explicit project toolchain; one subsequent hash command used a root-relative
path from `linux-tests/` and was rerun with the correct path.

OpenSBI reconstruction initially failed in three distinguishable ways: a new
linker lacked its runtime library path, GCC 15 treated `bool` as a C23 keyword,
and a Buildroot GCC 13 invocation omitted `PLATFORM_HART_COUNT`. Each failed
before producing a candidate. The accepted build uses the SDK's GCC 13.2,
`-std=gnu17`, and the DTB-confirmed single hart.

Splicing after timer patching failed closed because the patch inserts a
non-memory record. Regenerating the old unpatched NBF still exposed an
unaligned low-OpenSBI record that the strict splicer intentionally rejects.
The accepted full candidate instead proves exact equality for every Linux/DTB
record at or above `0x80200000`, plus matching boot controls and final timer
override.

The first performance invocation omitted its log parent directory. Because
the old runner spawned the board process before opening the log, that attempt
was treated as board contamination and followed by a full recovery. The
runner now validates the log parent before board launch, with a regression
test; no measurement from the failed invocation is retained.
