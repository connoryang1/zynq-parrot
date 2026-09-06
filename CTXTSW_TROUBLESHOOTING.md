This file keeps the debugging lessons that still matter for everyday development. Full incident transcripts and abandoned hypotheses remain in the pre-cleanup Git checkpoint described in HISTORY.md.

# Troubleshooting guardrails

- **Check identities first.** Bind every result to the RTL/configuration, bitstream, NBF, and host runner hashes. A different filename, old copied ELF, or skipped unpack target has repeatedly produced misleading comparisons.
- **One writer per simulator or board.** Clean before building, never concurrently with it. Archive a closed waveform before another run overwrites it; use the serialized FPGA runner.
- **Check actual compiler concurrency.** An outer parallel Make lost its jobserver and serialized the clean Verilator build during documentation validation. Serial outer Make with explicit `VERILATOR_BUILD_JOBS=12` restored twelve-way compilation; preserve build logs and terminate the old build fully before resuming.
- **Require guest success.** A host exit code or final `BSG PASS` alone is insufficient. Require the test-specific marker and `CORE PASS`; timeout, `CORE FAIL`, or absent markers invalidate the run.
- **Separate teardown from execution.** The minimal simulator has a known GPIO `fini()` assertion after guest PASS. Record it explicitly, rather than calling the entire process warning-free.
- **Recover a contaminated board.** After timeout/interruption, use the established recovery flow and wait for PYNQ initialization before overlay loading. Never run `control-program` with a dummy image just to check sudo.
- **Don't infer synthesis behavior from simulation alone.** Register-file RAM read/write collisions required an explicit bypass on FPGA even when local tests passed. Preserve the deployed dependency revisions as well as RTL.
- **Keep ordinary execution ordinary.** Context-specific redirects must not leak into normal replay/refill paths; typed packet widths and logical-versus-physical IDs must agree throughout the pipeline.
- **Respect translation and cancellation.** Target replay needs the target's restored PC. An older trap must cancel younger speculative context-switch work before it becomes architectural.
- **Use the correct clock.** `0xCC0` is the physical cycle counter; standard `time` retains the CLINT/OpenSBI path. Replacing it with the core clock changed the configured time rate.
- **Make reproductions discriminating.** Capture live inputs at the failing boundary, validate reporters, and require the reproduction to fail on the bad version and pass on the fix. A nearby failing probe is not automatically the same Linux bug.
- **Materialize exact dependencies.** Initialize only needed submodules; verify their gitlinks and real Git directories before issuing nested Git commands. Never rely on a similarly named checkout elsewhere.
- **Archive before deleting.** Preserve dirty files and nested Git databases, not just a commit hash. Shared hard-linked Git objects require serialized archive verification/removal. Avoid `grep -q` under `pipefail` when producer SIGPIPE could look like a failed check.

Operational commands live in the repository skills and runner tools; do not
copy changing command sequences into multiple status files. Add only new,
confirmed, generally useful lessons here; put routine failures in run artifacts.
