This directory records the source-level successful-wakeup data-preview candidate and its validation boundary. It distinguishes the new implementation from older artifacts whose names implied wakeup data even though their disassembly contained no wakeup-time physical hints.

# Successful-wakeup data preview

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

## Next discriminator

Do not spend another experiment on more lead time, more L2 capacity, or CSR
batching alone. The PMA-drop split now proves a useful accepted-request cache
effect but cannot resolve incremental wake-path cost because the userspace
endpoint crosses a 25k--50k-cycle scheduler phase. Add close cycle timestamps
around the successful-wakeup helper and expose them to the benchmark, first
comparing disabled, PMA-dropped, and accepted modes on the same kernel. Only a
resolved accepted-minus-drop hook cost justifies request QoS changes; a
resolved common helper/CSR cost instead justifies a single context-tag/batch
command. The eventual implementation target remains a separately throttled
lane with issued/completed/consumed/late/drop counters.
