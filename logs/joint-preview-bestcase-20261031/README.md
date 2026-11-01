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

## Hot-data instruction proxy and late replication

The opt-in `hot-proxy` footprint registers four eviction-buffer lines and
rereads them immediately before arming, while the measured four-line dependent
ring remains cold. This preserves mode gating, the instruction trigger, and
exact hook counting without useful target-data hints. The proxy ELF SHA-256 is
`fb0cc7b5...172d`; its transfer is `6ff8122a...1d7`. The exact NBF and
bitstream remain `f3a026b6...31a7` and `e97e0517...2381`.

The first full run completed nine cells, then stalled inside the partial tenth
cell at trial 322. After interruption and mandatory recovery, a disjoint
suffix from plan index 9 completed seven cells with final runner/CORE/BSG PASS.
The accepted cells reject 891 contaminated attempts. Strict analysis SHA-256
`eedaae0d...f18` gives:

- early: `0 [0,0.5]` target-load cycles, `-217.75 [-1216.25,630]`
  wake-to-load cycles, and `-1101.5 [-2571,766.5]` roundtrip cycles;
- late: `0 [-1,0]` target-load cycles, `-164 [-918,615]` wake-to-load
  cycles, and `1768.25 [-129.5,3175.5]` roundtrip cycles.

The zero local-load effect validates the intended proxy behavior. A direct
target-minus-proxy comparison resolves the expected 9.5--11 target-load cycles
but cannot purely attribute broader differences because the benchmark binary
and footprint differ.

A predeclared late-only replication used all eight groups in one boot. Its
first attempt ended during ELF transfer on host `Errant read from 1e3c74`,
before any configuration marker; that transcript is retained as rejected
infrastructure evidence. After full recovery, the unchanged retry completed
all cells with 417 rejected attempts and final PASS markers. It independently
finds 0 local-load cycles, `-513.5 [-1241,157.5]` wake-to-load cycles, and
`1568.25 [-383.75,3599.5]` roundtrip cycles.

Boot/set-stratified pooling SHA-256 `fcc873a2...694` resolves `1740.75
[226.75,2883]` late roundtrip cycles, about 1.4%, while local loads remain `0
[0,0]` and wake-to-load remains harmful and unresolved at `-318.75
[-890.25,135.75]`. This is evidence for a later two-switch tail benefit, not
faster target resume. The next measurement partitions child post-load work
from the return handoff.

## Direct post-load tail partition

The instrumented proxy records a third physical cycle timestamp after hook
validation and immediately before the accepted child pipe write. Every trial
must satisfy `child_post_load + return_handoff = roundtrip - wake_to_load`.
The ELF SHA-256 is `2bf990b4...d314` and its transfer is
`b745455e...9aa8`; the NBF and routed bitstream are unchanged.

Two independent late-only matrices were completed. Each full boot emitted all
eight cells but failed to return the final group-7 shell prompt, so group 7
from those boots was conservatively rejected. The derived group-0-through-6
prefixes each contain exactly 3,584 base rows, 3,584 tail rows, and seven
child/parent/cell PASS markers. Mandatory power recovery and a fresh verified
overlay preceded a disjoint group-7 suffix for each replication; both suffixes
end in runner, CORE, and BSG PASS. The accepted replications reject 419 and
421 timer-contaminated attempts.

Exact-binary base pooling SHA-256 `244cafc9...5906` gives:

- target loads: `0 [-0.5,0]` cycles saved;
- wake-to-load: `165.25 [-177.5,680.5]` cycles saved;
- roundtrip: `1769.5 [321.75,3124]` cycles saved.

Component pooling SHA-256 `678a870a...30a` gives:

- child post-load work: `-6.25 [-13.25,-1.5]` cycles saved;
- return handoff: `-599.5 [-1465.5,719.25]` cycles saved;
- exact combined post-load tail: `-376.5 [-1399.75,1086.5]` cycles saved.

The roundtrip median remains resolved, but no directly measured tail component
does. This is not an identity failure: block differences are exactly additive,
while medians of their noisy distributions are not. The result rejects the
simple claim that the 1.4% statistic directly measures a warmed return switch.
A lower-noise scheduling protocol or return-window miss trace is required.
Raw failed boots, derived prefixes, recovered suffixes, status records, and
all four analysis JSON files are retained under `physical-sweep/`.

## Equal-priority FIFO mechanism control

An optional `fifo` benchmark argument calls `sched_setscheduler(...,
SCHED_FIFO, priority 1)` before `fork`, so the parent and child inherit equal
real-time priority and alternate through blocking pipe operations. This is a
best-case noise-control workload, not a representative Linux scheduling
policy. The matching runner option is `--policy fifo`. The rebuilt ELF is
`7fdf6c6b...a423`; its transfer is `c1efef0a...7dcc` and reconstructs exactly.

A one-cell group-7 feasibility run completed with zero rejected attempts and
final runner/CORE/BSG PASS. Two predeclared prefix-12 eight-group replications
then completed in one boot each with three and zero rejected preemptions,
respectively. Both include 4,096 ordered base rows, 4,096 exact tail rows, and
final PASS markers. Prefix pooling SHA-256 `eb70b642...a789` gives:

- wake-to-entry: `-490 [-581.25,-336]` cycles saved;
- target loads: `0 [-0.5,0]`;
- wake-to-load: `-482.25 [-585.5,-331]`;
- roundtrip: `-393 [-694.5,-45.5]`.

Negative saved cycles mean the enabled arm is slower. Tail pooling SHA-256
`3f45840b...3c07` leaves the exact combined post-load interval unresolved at
`-8 [-291,181.25]`, while child bookkeeping is 10 `[7.5,12.5]` cycles slower.
The resolved cost therefore appears before the child's first-use boundary.

The exact count-zero image then completed all eight FIFO cells with zero
retries. Its analysis SHA-256 `6a99b5c2...32e8` resolves `-439.75 [-514,-321]`
wake-to-load and `-540.5 [-742.5,-219]` roundtrip cycles with zero target-load
effect. Independent prefix-minus-count-zero comparisons hash to
`6296aff3...9f49` and `560f2795...4d6`; their wake-to-load differences are
`+6.25 [-222,314]` and `-61.25 [-238.25,121]`. Thus the approximately
440--480-cycle first-resume cost is already present when the instruction table
is empty. It belongs to the shared enabled path—the four hot dummy physical
hints and scheduler hook—not to a resolved prefix-replay effect.

The first count-zero invocation stopped before `control-program`: the serialized
runner's remote SHA check found that the historical NBF had been removed. No
guest launched. The failed prelaunch log/status are retained; the exact
`5fe0d96f...969f` image was copied back, followed by remote `sync` and two
matching SHA checks, before the accepted run.

## True instruction-only runtime isolation

Runtime mode 3 triggers the shared instruction prefix and increments the
existing one-switch hook counter without executing any of the four physical
data-hint CSR writes. The rebuilt kernel embeds the exact accepted rootfs; its
`vmlinux.bin` SHA-256 is `62f9058f...b6c6`. A reconstructed old-payload
OpenSBI build and complete NBF pipeline first reproduced accepted prefix-12 and
count-zero hashes byte-for-byte. The new exact-kernel images are
`9d089f49...e094` and `d449ee97...717b`; their 1,861,851 Linux memory records
and 11 boot/control records compare exactly. Linux and OpenSBI executable CSR
collision scans pass. The dynamic benchmark and transfer hashes are
`c54cefb7...944c` and `5a682f22...333c`.

Both equal-priority FIFO matrices completed all eight set groups in one boot,
with 4,096 balanced rows and tails, exact hook deltas, runner PASS, and final
CORE/BSG PASS. Prefix-12 costs 280 wake-to-load cycles with interval
`[10.5,454.25]`; count zero costs 200.75 cycles with interval
`[-1.5,361]`. Prefix-12 minus count zero is unresolved at `-79.25
[-324.5,236]`, so replay itself has no demonstrated first-resume effect. The
common empty-table trigger/counter path explains most remaining overhead. The
roundtrip contrast favors prefix-12 by `529 [-32.75,1217.75]` cycles but is
unresolved and does not accelerate the incoming task. Strict analyses and raw
evidence are in `physical-sweep/instruction-only-*.json` and
`physical-sweep/physical-sweep-instruction-only-*.log.gz`.

Preparation exposed several fail-closed workflow issues. An invalid root-level
Python module name executed no tests; direct file invocations then passed. A
rejected temporary-cleanup command and a JavaScript reserved-word error both
stopped before mutation. OpenSBI did not notice a changed `PAYLOAD_PATH` in an
incremental build; the embedded-payload comparison caught the stale output,
and a separate `make clean` plus full rebuild fixed it. GNU Make directory
banners polluted the first redirected transfer file; local execution returned
127, and `--no-print-directory` produced a byte-exact reconstruction. A quoted
remote `awk` check failed before deletion; `sha256sum -c` verified the exact
board file before its corrected removal. The board's two old prefix/count-zero
NBF duplicates were deleted only after matching retained local hashes, freeing
space for atomic staging; both remain recoverable locally. A strictness-test
edit initially changed the partial-cell call site instead of the new full
instruction matrix; diff audit caught it, the invalid in-flight suite was
interrupted, and the corrected complete suite passed all 13 tests.

## Counter-only runtime isolation

Runtime mode 4 increments the incoming task's existing hook counter but writes
neither the instruction trigger nor any physical data hint. Mode 3 and mode 4
join at the identical counter update in kernel disassembly; only mode 3 executes
`csrw 0x5c0`. The clean kernel embeds the exact accepted rootfs and produces
`vmlinux.bin` SHA-256 `16dcb292...ad54`. Its executable-section CSR scan passes.
The count-zero OpenSBI `.text` scan also passes; its 17,003 low memory records
match the accepted count-zero image exactly, and all 1,861,853 high records
reconstruct the new kernel byte-for-byte. The final NBF is
`88ea24cd...999e`; benchmark and transfer hashes are `03aadeea...d33` and
`f7e13c2e...a01e`.

The full equal-priority FIFO matrix completed all eight groups in one boot with
4,096 balanced base and tail rows, one rejected asynchronous attempt, runner
PASS, and final CORE/BSG PASS. Counter-only mode costs 410 wake-to-entry cycles
with interval `[88.5,614.5]` and 420.25 wake-to-load cycles with
`[101.5,619.25]`; target loads remain exactly neutral at `0 [0,0]`. This is
about 0.90% of the representative 46,711.5-cycle disabled wake-to-load interval.
The independent instruction-minus-counter contrast is unresolved at
`+219.5 [-175.5,495]` wake-to-load cycles. Thus the empty hardware trigger has
no demonstrated incremental cost or gain; the resolved common-path cost belongs
to the measurement counter path. The next control must issue the trigger with
no hook increment in either arm and detect extra scheduling separately.

Preparation exposed three additional fail-closed workflow issues. The first
OpenSBI invocation used the bare-metal compiler whose linker lacks required PIE
support; the next omitted the SDK's `PLATFORM_HART_COUNT` definition. Both
stopped before firmware linking, and a clean rebuild with the SDK's exact Linux
toolchain, FDT, and platform flags succeeded. Unscoped payload-ELF and NBF CSR
scans reported embedded Linux/data words as false instructions; separate Linux
all-executable and OpenSBI `.text` scans are the valid gates. An inline Python
validation command was initially shell-escaped as literal newlines and failed
before reading evidence; the corrected read-only validation proved exact NBF
reconstruction. The old remote count-zero NBF was unlinked only after its hash
matched the retained local copy, and remains recoverable locally.
Two long comparison/test invocations outlived their initial observation without
retained session identifiers; their exact PIDs were verified live and were not
restarted. After they terminated, the final focused test and deterministic
comparison were rerun with captured results; comparison output remained
byte-identical while unused per-cell summaries were removed from that path.

## Pipe experiment workflow corrections

During the later hot-proxy preparation, a combined build-and-test command ran
the focused unit tests from the repository root and repeated the already-known
sibling-import failure. The benchmark build itself completed and was retained;
the import errors are not test evidence. Rerunning the two modules from
`linux-tests/` passed all 14 tests.
The tail-partition preparation repeated the same root-level import-only error;
no test executed in that invocation. The corrected `linux-tests/` invocation
passed 18 tests, and the later pooling extension's complete focused module
passes all 10 tests. A synthetic pooling test initially expected a confidence
interval spanning its two constant replicate effects, but the implemented
stratified median correctly collapses to their common pooled median; only that
test expectation changed, and its focused rerun passed before the full module.
One later mode-setting command also prefixed a path with `linux-tests/` while
already inside that directory; only `chmod` failed, and the concurrently
invoked tests still passed. The corrected root-relative mode command and the
expanded 17-test suite then passed before analysis.

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

## Uncounted trigger-only control

Runtime mode 5 issues only the instruction-prefix trigger. It performs no
hook-counter update and no data-hint CSR writes. The benchmark uses
`getrusage(RUSAGE_SELF)` around the handoff to accept exactly one voluntary
pipe block and zero involuntary context switches in both arms; the second call
is after the wake-to-load timestamp. The clean kernel `vmlinux.bin` SHA-256 is
`3b498116624395c23ca6ea4177ceb57f12643a52632644cb851602849d84daa2`.
The exact NBF, benchmark ELF, and transfer SHA-256 values are
`b8ecabda679a5930890b4d9b94679ef16d9ad2b292b685ff8b9b6f2c0f5911d2`,
`ed605f46f3c3975e6a80b0677aa88f6a15ceb8b52dabf282721870922e616345`,
and `cc9b847d5aab2625597bfeeef41e18bdcd62c68732e113b8093c74d1c2470261`.
Executable-section Linux and OpenSBI `.text` collision scans pass, and the NBF
reconstructs the exact kernel while preserving the accepted count-zero
OpenSBI/DTB region.

The one-cell group-7 feasibility run passed 512 rows and tails with two
rejected involuntary preemptions and final runner/CORE/BSG markers. After a
fresh verified overlay reload, the predeclared full run completed all eight
groups in one boot: 4,096 accepted rows and tails, 20 rejected attempts (each
one voluntary plus one involuntary switch), eight child/parent/cell PASS sets,
runner exit zero, and final CORE/BSG PASS. Both arms report zero hook deltas.

Strict set-stratified analysis gives `-19 [-741,650.75]` wake-to-entry,
`0 [0,0]` local-load, `+105 [-655.75,734.75]` wake-to-load, and
`+867 [511.75,1314.5]` roundtrip cycles saved. The primary incoming-task
endpoint is unresolved around zero. Independent trigger-minus-counter and
trigger-minus-instruction wake-to-load contrasts are respectively
`+525.25 [-303.25,1201]` and `+305.75 [-472,979.5]`; neither resolves.
This confirms that the earlier resolved approximately 420-cycle cost belonged
to counter instrumentation, not a demonstrated empty-trigger penalty.

The within-mode tail partition reports `+15 [-15.5,51.25]` child-post-load,
`+800.5 [412,1504.25]` return-handoff, and `-383 [-850.75,115.5]` combined
tail cycles saved. Every row satisfies the exact additive identity, but robust
component medians are not additive and do not localize the resolved roundtrip
median. The second `getrusage()` also lies in this tail, so no cross-mode tail
or Linux prefetch-speedup claim is made.

Raw full-log/status SHA-256 values are `0ea82c7b...064` and `b587aeb9...56c`.
The deterministic compressed full transcript hashes to `8bdd2b69...41a2`;
the feasibility transcript hashes to `c7edbb43...ce74`.
Base, tail, trigger-minus-counter, and trigger-minus-instruction analyses hash
to `363ac5dc...e19`, `d20c7d32...0f8`, `92661992...439`, and
`e23cc041...db1`.

Two fail-closed command mistakes caused no board or evidence mutation. Patch
reverse dry-runs were first invoked from the repository root without the
kernel `-d` directory, so `patch` could not locate its targets; corrected
explicit-directory dry-runs passed. Later, the trigger-tail analyzer output
was accidentally named relative to the repository while the command was
already in `linux-tests/`; redirection failed before the analyzer launched.
The concurrently launched focused unit test completed and passed, and the
analyzer was then run once from the repository root with the intended path.
An initial final rebuild used the SDK's standalone GNU compiler and produced a
different ELF layout. ELF comments and RISC-V attributes identified the tested
binary as a Buildroot GCC product; rebuilding through the rootfs-matched
Buildroot compiler reproduced the physical ELF byte-for-byte at
`ed605f46...6345`. The maintained build example now names that compiler.

## Uncounted prefix-12 replay

The next image changes only the instruction table behind mode 5. The strict
NBF splicer combines 17,020 low records from accepted prefix-12 donor
`9d089f49...e094` with all 1,861,853 records from the trigger-only count-zero
base. Candidate NBF SHA-256 is `b3cb808755d3bc54204d33d084805a967c833ea308254aae9c6f1bbde21f08b3`.
The three splicer tests pass, and the physical benchmark ELF and transfer stay
byte-identical at `ed605f46...6345` and `cc9b847d...0261`.

The group-7 feasibility cell passed 512 rows/tails with two rejected
preemptions and final runner/CORE/BSG markers. After a fresh verified overlay,
the full predeclared matrix passed all eight cells in one boot with 4,096
accepted rows/tails, 15 rejected involuntary-preemption attempts, zero hook
deltas, runner exit zero, and final CORE/BSG PASS.

Within prefix-12, the strict result is `+260.5 [-241.25,856.5]`
wake-to-entry, `0 [0,0]` local-load, `+177.25 [-304.5,808]` wake-to-load,
and `+895 [581.5,1125]` roundtrip cycles saved. The decisive independent
prefix-12-minus-count-zero contrast is `+279.5 [-596,1188]` wake-to-entry,
exactly `0 [0,0]` local-load, `+72.25 [-732,1068.5]` wake-to-load, and
`+28 [-507,448.25]` roundtrip cycles. Thus none of the 12-line replay effects
resolve; the large within-image roundtrip median is already present with an
empty table and is not replay benefit.

The prefix tail partition is `+5.5 [-22,37.5]` child work,
`+295.5 [39.5,596.5]` return handoff, and `-310.75 [-597.25,85.75]`
combined tail cycles. As in count zero, nonlinear robust medians plus the
post-load `getrusage()` prevent causal tail attribution.

Compressed feasibility/full logs hash to `be2a8fad...842c` and
`093463e6...51a`; full status hashes to `8f443253...616`. Base, tail,
prefix-minus-count-zero, and uncounted-minus-counted-prefix analyses hash to
`78bfc4b2...55b`, `29646073...0c3`, `f67ffd5a...86b`, and
`031cbcfd...7ad`.

One splicer-test invocation repeated the known repository-root sibling-import
failure and executed no test. The corrected invocation from `linux-tests/`
passed all three tests; the successful splice itself preceded and was
independent of that test-command error.
