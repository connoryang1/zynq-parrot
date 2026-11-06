This directory records the instruction-prefix controller diagnostic that separates replay activity from prefix relevance. It binds the accepted status word, rejected board attempt, exact software identities, and stale-address audit so the next prefix is retrained against the linked kernel actually under test.

# Instruction-prefix status and identity

## Controller result

Kernel patch `0022-blackparrot-icache-prefix-status.patch` copies the complete
64-bit `0x5c0` status through a userspace pointer, avoiding signed-return
ambiguity when the resident-drop counter occupies bit 63. The mode-thirteen
benchmark reads it only before `fork()` and after `waitpid()`, outside every
timed handoff.

One hard-recovered FPGA run begins at `0x0000000000000101` and ends at
`0xff803fc758020101`. Decoding the final value gives:

- 16 configured entries and next index 16;
- idle controller, no held/read/query state, and lane ready;
- 7,520 accepted prefix entries;
- 255 accepted triggers, saturated;
- zero dropped triggers;
- 511 already-resident suppressions, saturated.

The transcript passes 512 ordered trials, exact mode thirteen and hook gates,
zero data-replay counters, and child/parent/CORE/BSG markers. It filtered 1,023
unsuccessful-wake attempts, so its timing estimates are diagnostic only and do
not replace the two-boot corrected performance result. Transcript, status, and
strict-analysis SHA-256 values are respectively `fe7d7f97...26d8`,
`3b1524ee...5d02`, and `d9075d3f...e52`.

An earlier fresh-boot attempt reached Linux and then took an OpenSBI terminal
illegal-instruction trap during the validated base64 transfer, before the ELF
or new status operation ran. It is retained as `rejected-upload-trap-attempt1`
and was followed by the required hard recovery.

## Prefix relevance root cause

The configured table is the first 16 physical lines from
`logs/cache-resume-trace-model-20261030/results.json`. The original raw trace
shows those numeric addresses as instruction-demand misses in its linked image.
In both corrected mode-thirteen kernels, however, the 15 addresses in the
kernel physical range decode as unrelated FAT/VFAT, journal, and firmware
loader code; `0x8000b4c0` lies in the firmware range. Kernel relinking changed
the meaning of the physical addresses, but the old header was reused.

Thus the controller is functioning and issuing substantial replay traffic, but
the physical prefix is stale for the workload under measurement. The next
valid performance experiment must capture the current exact futex handoff,
regenerate the prefix, bind it to the kernel/payload hash, and rebuild only the
software image on the accepted routed RTL.

Durable raw artifacts are under
`/home/coyang/fpga-artifacts/context-resume/icache-prefix-status-20261106/`.
