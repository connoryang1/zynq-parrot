This directory records the source-level successful-wakeup data-preview candidate and its validation boundary. It distinguishes the new implementation from older artifacts whose names implied wakeup data even though their disassembly contained no wakeup-time physical hints.

# Successful-wakeup data preview

On 2026-11-02, the first full elaboration of the tagged data-replay prototype
exposed a pre-existing minimal-top reporter mismatch. Commit `7195fbc3` changed
the reporter to a `bp_processor` hierarchy, while
`cosim/black-parrot-minimal-example/v/top_zynq.sv` still instantiates
`bp_unicore_lite` directly. Both non-trace and clean `TRACE=1` elaborations
completed and then failed in the host C++ compile at those nonexistent names;
neither produced a runnable model. The reporter was restored to the direct
minimal-top hierarchy, and the guardrail is to require a clean trace build plus
a previously known-good runtime before trusting feature behavior.

The first corrected trace rebuild then failed during generated C++ compilation
because GCC placed assembly temporaries in root-backed `/tmp`, which had only
about 14 MiB free. The generated model occupied about 228 MiB and showed no RTL
error. This result is also invalid; clean it and set `TMPDIR` to the roomy
`/run/user/1001` filesystem for the replacement build.

The first integrated 32-line protocol run intentionally initialized every
target with stores. Its bounded trace reached the tagged trigger, admitted
seven entries, then ended with replay busy at index eight, D-UCE preview count
four, and both prefetch slots valid. The target lines were still dirty in L1,
while physical preview bypasses L1 and requests them below it. This is evidence
of a dirty-resident self-coherence hazard, not a performance result; the clean,
never-written target control must pass before the mechanism can advance, and a
final design must suppress or safely join dirty L1 residents.

## Tagged hardware footprint replay prototype

The replacement prototype stores four software-assigned footprints of up to
32 physical cache-line addresses and accepts a two-entry queue of context-tag
triggers. A trigger selects one footprint, waits its configured delay, and
replays its entries with a configurable gap. Software writes the footprint and
configuration outside the wakeup critical path; the wakeup operation is one
tagged command rather than 16--32 serialized address CSRs. Saturating counters
report accepted and dropped triggers plus entries admitted below L1 or filtered
before the detached lower-cache path.

The first integration drove replay directly into D-UCE and was rejected after
dirty-resident targets filled its detached slots and stalled. The accepted
integration instead sends each replay through the ordinary D-cache tag lookup,
with priority below architectural memory traffic. An L1 hit, including a dirty
hit, completes and filters the replay locally. An L1 miss enters the existing
detached prefetch path only when that path accepts it. A refused miss is retried
after a 16-cycle backoff; immediate retries had reproduced an intermittent
storm that monopolized the request boundary while both detached slots were
full.

A clean trace-enabled two-resident/four-context model with 64 D-cache sets
passes the cold 32-line test three consecutive times from the same ELF/NBF.
Each run reports 32 lower-path admissions, zero filtered entries, one accepted
trigger, no dropped triggers, intact data, and guest/CORE/host PASS. The
dirty-resident arm reports zero lower admissions and 32 filtered entries with
intact data and the same terminal gates. The existing physical-preview overhead
benchmark also passes on the rebuilt model, and the standalone controller gate
passes queueing, delay, gap, backpressure, filtering, counter, and 32-entry
ordering checks.

Exact logs, ELFs, NBFs, and compressed waveforms are under
`evidence/dcache-replay-backoff-cold-run1`, `-run2`, `-run3`,
`evidence/dcache-replay-backoff-dirty`, and
`evidence/dcache-replay-backoff-regression`. The first preservation command
incorrectly looked for run artifacts in `testing/`; the harness places them in
`cosim/black-parrot-minimal-example/verilator/`. No result was lost, and later
commands use the simulator directory explicitly.

The first checkpoint push invoked both branch names from the BlackParrot
submodule. The RTL branch pushed successfully, while Git correctly rejected
the top-level branch name because that ref does not exist in the submodule;
the top-level push was retried from the repository root. The guardrail is to
run and verify each repository's push from its own worktree.

This is simulator correctness and liveness evidence, not a Linux performance
result or an FPGA fit/timing result. The prototype still needs synthesis and a
Linux benchmark in which one tagged trigger replaces the current serialized
per-line hook before any speedup can be claimed.

## Tagged Linux source candidate

Patch `0017-blackparrot-tagged-data-replay.patch` adds two experimental wakeup
modes. Mode nine issues one data-footprint tag; mode ten first launches the
existing instruction prefix and then issues the same tag. A registration-time
prctl expands four pinned, cache-line-aligned page bases into one to eight lines
per base, programs an explicit hardware slot, and records a 16-bit trigger
delay plus 8-bit issue gap. The explicit slot is intentionally a controlled
single-CPU benchmark ABI, not a general Linux slot allocator.

The release path disables publication and waits for both the legacy physical
preview queue and the tagged replay engine to drain before unpinning pages.
Fork/exec/exit lifecycle paths clear or release the slot metadata. A read-only
status prctl exposes busy/queue state and accepted, filtered, accepted-trigger,
and dropped-trigger counters so a performance result can distinguish useful
replay from a dropped or still-active command.

`scheduler_tagged_replay_benchmark.c` registers four page bases with eight
lines each, constructs a 32-line dependent pointer ring, and compares disabled
against tagged replay while keeping pins, table programming, cache pressure,
and instruction-cache invalidation identical. Its arguments select data-only
or joint replay, trigger delay, and issue gap. Reprogramming outside each timed
trial doubles as an idle barrier, preventing a late command from contaminating
the next arm.

The patch applies and reverses fuzz-free after the maintained `0001`--`0016`
stack. The exact GCC 13.2 configuration compiles the affected objects and links
a complete 21 MiB `vmlinux`; all 142 Linux host tests pass, and the dynamic
benchmark cross-compiles. The linked kernel SHA-256 is
`300d72e9ad7826bae471ebd3109c99c2c78bc1ca7ec10ffb1bb05668338d6d2d`;
the benchmark SHA-256 is
`aae420e05c44b99626a5319ee152660295aea9cd4cf151582b6490c90c5d855d`.
The exact OpenSBI payload and generated NBF are respectively
`67ab829192001eb017a4ee608cab703bd27341d6ae8b58950053c8236ffb8774`
and `853e029b72ae5d244363cc39ad5eaac78d5a392c43d4f0ad1d387d3b4707581f`.

Exact ELF disassembly finds six uses of CSRs `0x9c1`--`0x9c3`, all intentional:
two replay-idle reads in lifecycle/configuration, one userspace-status read,
one table-entry write site, one configuration write, and one wakeup trigger.
The raw NBF scanner also matches instruction-shaped words inside compressed
initramfs data; the accepted predecessor NBF has the same class of false
positive. Therefore the executable ELF audit, exact payload provenance, and
the intended six-site list are the collision gate for this candidate.

The lightweight source-overlay build exposed three workflow guardrails. An
out-of-tree build must first remove symlinked in-tree build products, every
patch-touched input including `arch/riscv/Kconfig` must be copied into the
overlay, and final GCC/Verilator links must set `TMPDIR=/run/user/1001` while
root-backed `/tmp` is full. Direct `bp3`/hostname SSH probes were also invalid
outside the farm controller; subsequent monitoring uses the controller or its
recorded endpoint. None of these failed attempts produced performance evidence.

This candidate has a linked Linux image but no boot or performance result yet.
The routed FPGA job is recorded separately; board deployment remains gated on
routed fit/timing and exact package verification.

## Design

Patch `0013-blackparrot-wakeup-data-preview.patch` changes mode one so a real
`try_to_wake_up()` success launches the existing instruction prefix and then
issues up to four pinned physical data hints. The mode-one instruction trigger
and physical batch are both suppressed at scheduler selection. Mode two is
retained as a same-image selection-time joint control, while mode six remains
the existing wakeup-instruction/late-data control.

The helper validates the target task's registered `mm`, reads its four pinned
physical addresses, emits only nonzero addresses through CSR `0x9c0`, and
increments the existing hook counter exactly once after the batch. The pins
make the operation valid before the target address space is installed.

## Source and image verification

The complete maintained patch suffix `0009`, `0010`, and `0013` applies in
order over the compiled instruction-only Linux tree. After correcting the new
patch's hand-written hunk counts, forward and reverse dry-runs are fuzz-free.
All 135 currently discovered Linux host tests pass.

An isolated GCC 13.2 object build of `kernel/sched/core.o` passes using the
existing Linux 6.6 configuration and exact Buildroot cross compiler. Candidate
object SHA-256 is
`b4ef293c23f9233ab4231adcc198e8f0a9d1b6017724349ed08454e77cc7e123`.
Disassembly of `try_to_wake_up()` shows `csrw 0x5c0, zero` followed by four
conditional `csrw 0x9c0` instructions and the hook increment. Disassembly of
`__schedule()` checks modes four, six, and one before its selection trigger,
so mode one branches around the duplicate; its remaining physical-write sites
belong to the preserved mode-two/mode-six controls.

The older `/dev/shm/zp-mode7-wakeup-data-build` is not evidence for this
candidate. Its `try_to_wake_up()` disassembly tests modes six and seven but
contains only CSR `0x5c0`; no physical CSR `0x9c0` appears in that wakeup path.

The candidate was subsequently linked into the accepted count-zero Linux
image and exercised on the exact 16 KiB routed PYNQ-Z2 implementation. The
the successful-wakeup top-level checkpoint is `28b3a86b`, while the reused
routed hardware is exact top-level `7195fbc3` and BlackParrot `174f2787a`.
The routed bitstream SHA-256 is
`a5f3a8acfed45325df06dc3925a31f0e606433ddb346e078ff495432dbbbded1`.
The successful-wakeup implementation is therefore no longer source-only.

## FPGA/Linux results

The complete eight-group fixed-arm FIFO matrix resolves a 20-cycle saving in
the four dependent target loads, with replicate-stratified 95% circular-block
interval `[17.5,21.5]`. It simultaneously makes wake-to-first-use 610.75
cycles slower, with `[494.25,726.75]`. A one-line point reduces the penalty to
roughly 218 cycles but does not produce a local-load gain. Mode two's older
selection-time batch saves 32.5 local-load cycles while making first use
575.75 cycles slower. Trigger-only and hook-counter controls are neutral.

Two follow-up controls bound the cause:

- Adding 512 physical cycles between successful wakeup and the parent's block
  leaves the four-load saving at 11 cycles and wake-to-first-use unresolved at
  a harmful 489-cycle point. The normal Linux wake-to-entry interval is about
  48,000 cycles, so lack of raw lead time is not the supported explanation.
- Re-reading proxy lines immediately before each arm still makes first use
  822.25 cycles slower, with `[465,1178.5]`, and provides no load benefit.
  Cold target refill traffic is therefore not the dominant source of the
  regression. The remaining candidates are shared cache/link perturbation and
  Linux scheduling-path interaction while detached commands are in flight.

The first lead-time launch stopped before userspace and is preserved as a
boot failure, not benchmark evidence. The recovery-qualified retry and the
hot-proxy run both pass exact bitstream/NBF/control/ELF identity, benchmark,
terminal child/parent, CORE, and host gates. Raw logs, statuses, and analyses
are under
`/home/coyang/fpga-artifacts/context-resume/wakeup-data-preview-20261101/`.

## Direct command-overhead control

`testing/mt_physical_preview_overhead_benchmark.c` compares matched bodies
containing zero, one, or four CSR `0x9c0` writes immediately before a resident
hardware-context switch. It warms all four lines, waits for preview idle,
rotates the three modes across seven samples, and records the peer's first
instruction with the core-wide cycle counter. A clean trace-enabled full-top
run on `e_bp_unicore_zynqparrot_prefetch16k_cfg` reports all 21 samples equal
at 11 cycles and reaches guest and host PASS; exit 134 is only the established
post-PASS DPI finalizer assertion.

The waveform proves that this is not a dropped-command false pass. It contains
exactly 40 cycles of `physical_preview_v_lo` in 16 bursts, matching eight
one-command and eight four-command runs. Every burst reaches D-UCE enqueue;
the queue reaches depth one and drains concurrently. Thus four retired preview
commands do not delay an immediate resident handoff in the full-core model.
The Linux penalty occurs later or elsewhere in the shared memory/scheduler
path, not in architectural CSR retirement or the switch instruction itself.

The validated ELF, run log, FST, and source are archived as
`/home/coyang/fpga-artifacts/context-resume/wakeup-data-preview-20261101/physical-preview-overhead-sim.tar.xz`
(SHA-256 `e2157c7d89acb5a581a3555e86b81bc3833d812a1c79438ff48d8dcdb7089062`).
The ELF, log, and FST SHA-256 values are respectively `ee18c7fa...f6d`,
`e219a9a4...f92`, and `ab57fc06...e8`.

## Shared L2 contention control

The preview path gives architectural D-cache demand priority inside D-UCE, but
after issue both I-cache/D-cache ordinary requests and physical previews enter
the same round-robin forward crossbar and L2 request controller. Response
selection prefers ordinary traffic; request admission does not inspect the
preview bit. This is a real opportunity for interference, but a directed
full-core control bounds its size for hot preview hits.

`testing/mt_physical_preview_icache_contention_benchmark.c` places `fence.i`
before the same matched zero-, one-, and four-command bodies, forcing the
peer's first instruction through L2. After the initial transient, all six
rotated sample groups measure the no-hint path one cycle faster than both the
one- and four-hint paths; one and four are equal. The fixed ASCII checker,
guest, CORE, and host pass on the clean trace-enabled 16 KiB model. Hot preview
traffic therefore can delay a cold instruction handoff, but only by one cycle
in this control—not the 611--822 cycles observed under Linux.

The ELF, run log, FST, and source are archived as
`/home/coyang/fpga-artifacts/context-resume/wakeup-data-preview-20261101/physical-preview-icache-contention-sim.tar.xz`
(SHA-256 `2d696d15b13e79bb1419bc6be911be9ba4e5bbba810d47097b92124b624b115d`).
The exact ELF, log, and FST SHA-256 values are `d2f0021c...7a3`,
`5099f273...159`, and `4ff1110a...ac`.

The Linux wakeup helper always reads all four contiguous registered-address
slots before testing which are nonzero. Consequently the four-versus-one
penalty scaling cannot be attributed to reading three additional metadata
slots; it tracks nonzero CSR commands or their downstream work. A Linux-only
control that executes the same CSR writes with PMA-rejected addresses is the
next clean split between software/retirement cost and accepted memory traffic.

## PMA-drop Linux control

Kernel mode seven executes the same successful-wakeup helper, reads all four
registered physical-address slots, increments the same hook counter, and
writes CSR `0x9c0` four times, but substitutes local addresses `0x1000` through
`0x4000`. The existing PMA gate rejects those values before D-UCE/L2. The
maintained patch applies and reverses fuzz-free against the accepted kernel;
the exact GCC 13.2 configuration links, and disassembly proves four constant
CSR writes in mode seven while preserving mode one's real-address path.

On the same candidate NBF and routed image, separate 512-trial group-seven
FIFO arms show:

- PMA-dropped mode seven has a neutral local-load estimate of -0.5 saved cycles
  with 95% interval `[-1.5,0.5]`. Its wake-to-entry point is 554 cycles slower,
  but the interval `[-1174.5,2010]` spans both signs.
- Accepted mode one saves 24.5 local-load cycles with `[15.25,31.25]`. Its
  wake-to-entry point is 694.75 cycles slower, with
  `[-1267.75,1377.25]`.
- An independent cross-boot bootstrap gives accepted-minus-dropped local
  saving 25 cycles with `[15.5,31.75]`, but incremental wake-path saving
  -140.75 cycles with `[-2797.75,1948]`.

The tighter `accepted-drop` benchmark arm interleaves mode seven and mode one
inside each `[drop,accepted,accepted,drop]` block. Both sides therefore execute
one hook and four CSR writes; only PMA acceptance differs. Its clean retry has
zero rejected handoffs and all child/parent, CORE, and BSG PASS markers.
Accepted hints save 14.25 target-load cycles over dropped hints with
`[11.25,20.75]`, while incremental wake-to-entry is unresolved at -629 saved
cycles with `[-1685.75,1655.25]`. Request acceptance clearly causes the useful
cache effect, but it does not resolve a downstream wake-path cost and cannot
explain the earlier precise 611--822-cycle regression.

The unresolved interval is structural benchmark noise, not merely a small
sample: a typical four-trial block spans 23,574 wake-to-entry cycles, versus a
hundreds-of-cycles candidate effect. The local-load interval remains tight.
Post-hoc trimming would not be a defensible fix; the next measurement must
timestamp immediately around the kernel wakeup helper and remove the long
scheduler transit from the cost endpoint.

## Kernel-local hook timing

Patch `0015` records global cycle CSR `0xcc0` immediately before and after the
successful-wakeup mode branch, instruction trigger, physical helper, and CSR
writes. Mode zero traverses the same empty bracket. A read-only prctl exposes
the latest interval, and the benchmark emits one ordered hook record per
accepted handoff only when explicitly requested. Disassembly proves both cycle
reads bracket every mode-one/mode-seven return path and that the four accepted
or constant PMA-drop writes remain inside the interval.

Four clean group-seven FPGA arms decompose the cost:

- PMA-dropped mode seven versus disabled changes the hook from median 29 to
  156 cycles: 127 cycles of overhead with 95% paired interval `[126,127]`.
  Target loads remain exactly neutral: 0 saved cycles with `[-0.5,1]`.
- Accepted mode one versus PMA-drop raises the hook from median 156 to 222
  cycles. Request acceptance adds 64 cycles with `[59,73.25]`, while the four
  target loads improve by 22 cycles with `[15.5,28]`.
- Accepted mode one versus disabled directly measures 174.75 hook cycles of
  overhead with `[166.25,184.5]` and saves 15 load cycles with `[7.75,20.5]`.
  Wake-to-entry regresses by 596.25 cycles with `[112.5,803]`, reproducing the
  earlier roughly 611-cycle matrix result. Subtracting each trial's own hook
  leaves a harmful 415-cycle point, but its interval spans from 52.75 cycles
  beneficial to 614.75 harmful; the asynchronous/scheduler remainder is not
  independently resolved by this one group.
- Reducing accepted data from four lines to one lowers hook overhead only to
  135.5 cycles with `[132.5,155]` and produces exactly zero local-load gain.
  The three extra hints therefore cost only about 39 cycles total. Four-to-one
  CSR batching alone cannot remove the dominant fixed cost.

The result changes the optimization priority. The tested four-load benefit is
smaller than synchronous hook overhead even before any unresolved downstream
effect. A single batch CSR can save only the roughly 39-cycle incremental
portion. The larger opportunity is to remove the fixed scheduler-path work:
use one context-tag command, retain the footprint in hardware, and let a
separately scheduled lane walk it without backpressuring the architectural
hook. A larger useful footprint is also required to amortize even the first
command; one line is explicitly unsupported as a positive case.

The exact timing NBF, benchmark ELF/transfer, build log, disassembly, and hash
manifest are archived at
`/home/coyang/fpga-artifacts/context-resume/wakeup-data-preview-20261102/hook-timing-minimal.tar.xz`
(SHA-256 `65df305028ea04944d9d759775a95c805c0bc40c39fb1b05d0aea8ab2e443026`).
The NBF, ELF, kernel, and disassembly hashes are respectively
`702ecd7d...17f5`, `ba44d13a...0b4e`, `896fa8d3...d3fb`, and
`944d6a04...0dd7`. Passing logs/status/analyses use the
`group7-hook-*` names in the existing durable FPGA directory.

## Data-only wakeup control

Mode eight issues the same four real physical data hints and hook accounting
as joint mode one but omits instruction replay CSR `0x5c0`. The full kernel
links, disassembly proves mode eight enters the physical helper without the
instruction trigger and suppresses the selection duplicate, the exact NBF
splice round-trips, and all host gates pass.

Against disabled on its own image, data-only saves 22.5 target-load cycles
with `[14.5,31]` and has unresolved wake-to-entry at a harmful 27.75-cycle
point with `[-727.25,1136]` in saved-cycle convention. Its hook overhead is
267 cycles `[266,268]`, unexpectedly larger than the 174.75-cycle joint result
from the preceding kernel image. That cross-image difference is not causal:
adding mode eight changed mode-dispatch branches and code layout.

The decisive same-image `[data-only,joint,joint,data-only]` arm keeps the four
accepted data hints identical and toggles only `0x5c0`. It passes 512 trials
with zero retries and all terminal markers. Joint versus data-only changes
target loads by exactly 0 cycles with `[-1.5,2]`, changes wake-to-entry by a
harmful 31.5-cycle point with `[-367,715.5]` in saved convention, and is 9.25
cycles faster inside the hook with `[9,10]`. Instruction replay therefore
does not explain the local gain, synchronous cost, or the earlier total wake
regression. Data-only is not a demonstrated better baseline.

This also establishes a measurement guardrail: absolute close-hook costs from
different kernel images cannot be attributed to a single source feature when
the compiler changes the shared mode-dispatch path. Prefer a same-image direct
arm whenever a control mode can coexist with the candidate.

The exact data-only NBF, direct-comparison ELF/transfer, build log,
disassembly, and hash manifest are archived at
`/home/coyang/fpga-artifacts/context-resume/wakeup-data-preview-20261102/data-only-minimal.tar.xz`
(SHA-256 `f835c38960218b8ba4fb051aa68eee89b9f777e6c70b92997c2e1c38270644e0`).
Passing evidence is `group7-hook-data-only-vs-disabled-fifo.*` and
`group7-hook-joint-vs-data-only-fifo.*` in the durable FPGA directory.

Exact passing logs, statuses, and analyses are
`group7-mode7-pma-drop-fifo.*`,
`group7-mode1-accepted-same-image-fifo.*`, and
`group7-accepted-vs-pma-drop-fifo.*` under the existing durable artifact
directory. The minimal rebuild bundle is
`/home/coyang/fpga-artifacts/context-resume/wakeup-data-preview-20261102/pma-drop-control-minimal.tar.xz`
(SHA-256 `5d14cc3bce5100308b6f477765d5a1a1c1077af4b2f5dc7bc5e34d00ef48c7c6`).
It contains the candidate NBF/kernel, exact build log/disassembly, both
transfers, the direct-comparison ELF, and a per-file hash manifest.

## Workflow guardrail

The first object compile used a hard-linked kernel clone. Source files and the
historical `core.o` were hash-checked unchanged, and compiler outputs received
private inodes, but Make rewrote the shared generated
`include/generated/vdso-offsets.h` timestamp. Its contents were from the same
configuration, but the historical tree's generated-header timestamp is no
longer provenance. Future full builds must use a real copied or independently
materialized output tree, not a hard-linked build tree.

The full simulator collateral target does not honor `PROG_RISCV`; after a test
program changes, remove its generated `prog.riscv`, `prog.mem`, and `prog.nbf`
before `make ... run`, then verify the copied `prog.riscv` hash. Also invoke
the Linux Python test suite with
`(cd linux-tests && python3 -m unittest discover -s . -p 'test_*.py')` so its
local imports resolve; there is no generic `make test` target in that directory.
Before the trace rebuild, stale reproducible generated outputs in two inactive
`/dev/shm` worktrees were cleaned to recover temporary space; no source or
unique evidence was removed.

The PMA-control build exposed four additional provenance guardrails. Regenerate
multi-file kernel patches from exact source copies instead of hand-maintaining
hunk counts, and run forward plus reverse dry-runs from a path whose working
directory is explicit. Supply the retained Buildroot initramfs directory
through `BR_BINARIES_DIR`; a first link failed because the copied configuration
otherwise expanded it to `/rootfs.cpio`. Do not trust a copied `vmlinux.bin`
beside a historical tree: the fail-closed NBF splicer rejected one stale file,
whereas objcopy of the accepted ELF round-tripped the accepted NBF exactly.
Finally, stage every new NBF with the hash-verifying artifact script before the
interactive runner; the first launch stopped before privileged execution when
the board copy was absent.

The first direct accepted-versus-drop board attempt stopped during Linux boot
at 3.591 seconds and hit the 300-second shell-prompt gate. It is retained under
the explicit `boot-timeout` name and is not benchmark evidence; a full
power-cycle/readiness/overlay recovery then produced the clean passing run.
An attempted raw durable copy also exhausted the root filesystem while writing
its second large file. Only the newly created incomplete duplicate was removed;
the source artifacts remained intact, and the compact 22 MiB bundle above was
verified before durable copy. Future preservation should check root capacity
first and avoid redundant accepted payloads.

The first accepted-versus-disabled hook-timing launch reached init at Linux
time 37.37 seconds but never produced a shell before the 300-second gate. Its
log/status are retained under an explicit `boot-timeout` name. The identical
NBF had already completed two clean timing arms, and a full recovery produced
the passing accepted-versus-disabled retry; the timeout is excluded from all
performance estimates.

## Next discriminator

Do not spend another experiment on more lead time, more L2 capacity,
instruction-trigger removal, or a four-to-one CSR batch alone. Data-only is
neutral versus joint, and extra hints two through four account for only about
39 hook cycles. The next implementation should replace the scheduler's
per-line metadata walk with one stable context-tag command, enqueue it through
a nonblocking command FIFO, and let a separately throttled lane replay a
hardware-resident 16--32-line footprint. Keep instruction replay independently
optional. Acceptance requires one-cycle-or-better architectural enqueue,
unchanged switch-only/cold-I controls, issued/completed/consumed/late/drop
counters, and a larger-footprint Linux arm whose local savings exceed command
overhead before claiming end-to-end value.
