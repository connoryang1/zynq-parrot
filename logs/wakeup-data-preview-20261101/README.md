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

## Current verification

The complete maintained patch suffix `0009`, `0010`, and `0013` applies in
order over the compiled instruction-only Linux tree. After correcting the new
patch's hand-written hunk counts, forward and reverse dry-runs are fuzz-free.
All 134 Linux host tests pass.

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

## Workflow guardrail

The first object compile used a hard-linked kernel clone. Source files and the
historical `core.o` were hash-checked unchanged, and compiler outputs received
private inodes, but Make rewrote the shared generated
`include/generated/vdso-offsets.h` timestamp. Its contents were from the same
configuration, but the historical tree's generated-header timestamp is no
longer provenance. Future full builds must use a real copied or independently
materialized output tree, not a hard-linked build tree.

## Remaining gate

No Linux image or FPGA performance result exists yet. A full kernel link and
count-zero image must pass executable-section CSR checks and boot on the exact
16 KiB routed image. The first trace should require zero target demand misses
for the enabled arm; only then is a fixed-arm performance comparison useful.
