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

## Next discriminator

Do not spend another experiment on more lead time, more L2 capacity, or CSR
batching alone. The next useful measurement is downstream: identify whether
hot preview requests overlap ordinary kernel I-cache/D-cache/L2 traffic during
the Linux switch path, and whether strict demand-over-preview QoS removes the
roughly per-request first-use penalty. If it does, the implementation target is
a context-tagged replay command with a separately throttled lane and
issued/completed/consumed/late/drop counters. If it does not, instrument the
Linux handoff phases before changing RTL again.
