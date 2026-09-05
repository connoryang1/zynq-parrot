# Context-Switch Troubleshooting Notes

This file keeps the durable lessons from older context-switch experiments. It is
not a complete diary of every branch state.

## Default Debug Rule

For any unexpected hang, pass/fail discrepancy, wrong output, or surprising
cycle count:

1. Stop changing RTL.
2. Reproduce with the smallest relevant `make -C testing ... TRACE=1` run.
3. Use the waveform tools before making another guess.
4. Compare against a clean known-good baseline when possible.

Keep debug instrumentation separate from functional fixes and remove it once
the measurement is understood.

When continuing a cherry-pick after resolving conflicts in an unattended
session, set `GIT_EDITOR=true`; otherwise Git may open an interactive editor
and fail on the non-interactive input stream. Verify the sequencer state before
retrying so commits are neither skipped nor applied twice.

## Common Failure Signatures

### Board disappears during overlay reload

If artifact staging has verified the package and NBF hashes but SSH is refused
while `load-blackparrot-overlay` is still running, no guest result exists. Treat
the board as contaminated, power-cycle it, wait for the PYNQ-ready gate, and
reload before retrying; do not classify that interruption as an RTL failure.

### Archived Linux runner reads an invalid reset CSR

The protocol-compatible runner identified by SHA-256 `76db…` is required for
the archived January bitstream, but it is not interchangeable with every
routed candidate. If its first base-register read reports a non-Boolean reset
value and does not reach NBF configuration, stop and power-cycle; restore the
candidate's reviewed runner before continuing. That is a host/bitstream
protocol mismatch, not guest or RTL evidence.

### Detached serial launch disappears before creating a transcript

On this PYNQ image, a `setsid`/`nohup` control-program wrapper can be reaped
when its originating SSH session closes, before it creates either its retained
log or status file. This is a launcher failure, not a board run: verify that
no `control-program` is alive, reload the intended overlay, and use the
serial helper with `PYNQ_CONTROL_PROGRAM_FOREGROUND=1` for the next bounded
or self-terminating control.

### Power-cycling immediately after artifact staging can truncate the overlay

A baseline package was verified and extracted successfully, then the board was
power-cycled immediately because the prior PL run had timed out.  On reboot the
new BIT/HWH/MAP files existed but were zero length, showing that the abrupt
power loss occurred before the filesystem had persisted the extraction.  Do
board recovery before staging whenever possible; if staging must precede a
power cycle, run `sync`, verify the artifact hashes again, and only then remove
power.  A zero-length or hash-mismatched overlay must be re-staged after the
PYNQ readiness gate and must never be loaded or treated as RTL evidence.

### Generated Linux probes can exhaust board storage

The board accumulated 104 temporary 69-MB Linux/OpenSBI probe NBFs and reached
100% filesystem usage, making atomic package staging unsafe.  Preserve the
canonical Linux NBF and exact runner by hash, remove only regenerable probe
variants after their transcripts are retained, run `sync`, and require ample
free space before every stage; the 2026-09-04 cleanup recovered 7.23 GB.

### Historical source checkpoint silently times out under a current runner

An old source revision that once booted Linux is not itself a sufficient FPGA
control. The rebuilt `2a1f8834` / `ce328a77` pair and the CSR-only candidate
both timed out silently with the same 0.133339 IPC signature under the current
reviewed runner, so do not attribute the candidate result to its RTL delta.
First establish a freshly bootable source/bitstream/host-runner control, then
perform an A/B comparison using identical NBF, runner hash, power-cycle, and
overlay-load procedure.

That control now exists for the pre-feature `4015d0f` / `08edfb` pair: its
freshly built bitstream reaches `/init` only with the source-matched legacy
threaded FIFO runner (`b774f7…`), while the newer pybind/PYNQ runner produces
the misleading silent 0.133-IPC loop. Treat the host runner as a versioned
component of every Linux classification, not incidental board tooling.

The runner match is a necessary control, not a universal cure. The full routed
context-switch stack (`1c42e9f2`, package `73342c3…`, bitstream `8ee250aa…`)
has now been tested with that same pinned runner and reaches Linux's atomic
DMA-pool boundary before stalling. Do not reclassify this post-DMA failure as a
host protocol issue without a new A/B control; it is currently a credible RTL
or architecture-state failure.

### Linux runner must explicitly zero DRAM, but zeroing is not a boot proof

The archived Linux runner includes `FREE_DRAM=1 ZERO_DRAM=1`; a normal runner
compiled with `ZERO_DRAM=0` is not an equivalent test even if the source and
NBF hashes match. Build a temporary hash-pinned zeroing runner and require its
`zero-d 0 MB` through `zero-d 63 MB` transcript before comparing Linux runs.
That condition is necessary but not sufficient: the exact historical baseline
still showed the same silent loop after a verified zeroing-runner control.

### Legacy Vivado flow supplies its own mode

The preserved pre-feature source invokes Vivado as `-mode batch`, whereas the
maintained 2024.2 wrapper historically added that option unconditionally.  Do
not treat Vivado's `mode can only be specified once` error as a source or RTL
failure: the wrapper now preserves a caller-supplied mode and only defaults to
batch when none is present.

### Vivado SmartConnect can fail before RTL synthesis

Midpoint route `20260904T221938Z-6a915e3b` failed while creating three
SmartConnect adapter IPs with XML `Unexpected end of message`; it never ran
RTL synthesis and therefore provides no candidate evidence.  A clean retry
reproduced the same failure, while the already routed historical AXI
Interconnect substitution advanced immediately past block-design validation;
carry that proven top-collateral patch on historical candidates rather than
retrying the damaged SmartConnect XIT service.

### Historical Vivado file list omitted a masked-write adapter

After SmartConnect was bypassed, Vivado reached RTL synthesis and reported
`bsg_mem_1rw_sync_mask_write_bit_from_1r1w` missing even though its parent
instantiated it.  Carry the previously routed one-line source-list fix, then
perform a clean traced model rebuild and known-good guest gate before routing;
the pre-fix synthesis failure is collateral evidence, not a feature result.

### Historical source uses nested FPGA submodules

The 2015-style source graph contains a nested
`black-parrot-subsystems/zynq/import/riscv-dbg` gitlink.  A top-level
submodule initialization is insufficient: before legacy Vivado packaging, run
the exact submodule's recursive initialization and verify `src/dm_pkg.sv` is
present.  A missing file is a reproducible checkout failure, not a missing RTL
source or a synthesis result.

### Historical simulator runs retain the previous program image

The legacy Verilator `run` target only creates `prog.riscv` when it is absent,
so changing `PROG=` can silently rerun the preceding test.  Before every
lower-level historical run, explicitly remove `prog.riscv`, `prog.mem`, and
`prog.nbf`, then confirm the expected test banner in `run.log`; a command-line
program name alone is not evidence that the requested binary ran.

### Pair historical BlackParrot RTL with its historical top collateral

A current zynq-parrot testbench directly probes internal context-cache signals
that do not exist at earlier feature midpoints.  Such an elaboration failure is
a wrapper/source-age mismatch, not a midpoint classification: use the top-level
commit that originally pinned the selected BlackParrot revision, and apply only
the narrowly reviewed compatibility overlays needed by the FPGA toolchain.

### Historical configuration names do not preserve FPGA dimensions

The first 57/113 midpoint used the expected `e_bp_unicore_zynqparrot_cfg` name
but inherited that revision's defaults: four resident threads and a 2x2 L2.
It synthesized to 63,298 LUTs and failed placement on the 53,200-LUT xc7z020;
this was not a feature or Linux result. Every replay candidate must explicitly
override the validated static shape—two resident threads, four logical
contexts, and a 1x1 L2—then pass a clean local gate before routing.

Early feature revisions may not yet contain a separate `num_contexts` member.
For those schemas, set only `num_threads=2` and the 1x1 L2 dimensions; adding a
later field is an elaboration error, not a feature result. The corresponding
prefix can classify Linux compatibility but cannot represent four logical
contexts until that field appears later in the feature sequence.

### Historical Verilator recipes can mask failures and ignore runtime limits

The historical Verilator recipe pipes its command through `tee` without
`pipefail`, so GNU Make can exit zero even when the log ends in `%Error` and no
simulator executable exists. Require both an executable and an error-free log;
its generated inner Makefile can be resumed directly with `make -C obj_dir -f
Vbsg_nonsynth_zynq_testbench.mk -j$(nproc)` when the wrapper loses its
jobserver. Some old host runners also ignore `TARGET_RUNTIME_MS`, so a modern
context smoke that is unsupported at that feature depth must be interrupted,
its child process checked absent, and recorded as non-classifying.

### Historical accelerator source can fail full Vivado elaboration

Some early snapshots assign the nonexistent `offset` member of
`bp_be_dcache_pkt_s` in `bp_cacc_vdp.sv`, even though the packet schema already
uses `vaddr`. A selected Verilator configuration may not elaborate that
disabled accelerator, while Vivado still diagnoses it during full source-set
elaboration; apply the upstream one-line `offset`-to-`vaddr` correction before
classifying the candidate, and do not treat this build failure as Linux or
context-switch evidence.

### Historical PLIC sources are generated collateral

The older `zynq/v/gen` PLIC directory is not committed with its source
snapshot.  Regenerate its patched OpenTitan PLIC first and stage the required
primitive and generated `rv_plic_*` files as one matched bundle; the pinned
historical configuration yields the same PLIC RTL hashes as the maintained
generator.  Do not substitute an arbitrary OpenTitan revision, because the
wrapper and register-package interfaces must match the historical PLIC glue.

### Stall after NBF load

Typical output:

```text
BSG-INFO:    ps.cpp: beginning nbf load
```

followed by no benchmark banner or pass/fail output.

This usually means the change disturbed startup/freeze/resume/control
sequencing, not only the measured context-switch loop.

### Guarding a probe at a compressed instruction

`make_linux_milestone_nbf.py --expect-first-word` checks four bytes, even when
the target instruction is a two-byte compressed instruction.  At Linux's
`0x8020294a` C.LD, the correct guard is the overlapping word `0x659c6198`,
not the C.LD's `0x6198` halfword padded with an assumed neighbor.  Let the
generator reject a mismatch and correct the source window before staging; a
rejected local generation is not a board or RTL result.

### Wrong or illegal instruction after sideband/fast-path work

Older failed sideband experiments produced wrong instruction fetches around
known benchmark PCs. Treat this as FE fetch/realign/queue metadata or I-cache
state corruption until proven otherwise.

### Trace and non-trace disagree

Trace markers, waveform gating, stale Verilator objects, or host scheduling can
change timing enough to hide a bug. Do a clean rebuild before trusting
waveform-dependent conclusions.

### Gap tests disagree unexpectedly

Check the binary shape with objdump. A gap helper that becomes an out-of-line
call/return sequence is no longer testing the same straight-line gap. The
controlled-gap helper should remain forced inline.

### CSR isolation reports a stale written value

If `mt_csr_isolation_test` reports that T1 wrote the value produced by the first
instruction of a `li` sequence, such as `0x5a5a6000` instead of `0x5a5a5a5a`,
check the register-form CSR write RAW path. The CSR source operand must not
consume an early integer producer before the final value is available.

### Ring isolation is quiet after NBF load

`mt_ctxtsw_4ctx_ring_isolation` intentionally prints only after the ring
returns to T0. A pre-ring banner can leave host MMIO stores outstanding; combined
with the thread-body fences, that exercises host I/O ordering instead of just
CSR/thread isolation.

## Durable Lessons

- `commit_pkt.ctxtsw` is the baseline architectural authority.
- `target ready` is not enough to launch an early switch safely.
- `pending_ctxtsw_sent_r` is not a complete protocol by itself.
- Early FE redirect is safer than early BE ownership, but still needs explicit
  finalization/cancel rules.
- Moving BE ownership before commit is high risk unless old-thread retirement
  identity, target-thread dispatch, context save, and rollback are fully
  separated.
- Memory side effects are not commit-only; arbitrary target-context BE execution
  before old-thread context-switch commit is not globally safe.
- Poison is not the same as hold/backpressure. If an entry is read while
  poisoned, the design may drop work that should have been held.
- A duplicate commit-time FE command may need suppression after early FE accept,
  but commit-time cleanup/fence/finalization often still needs to run.
- I-cache redirect/force behavior must not expose partially completed stale
  old-thread fills as valid target-thread instruction data.
- Thread IDs must follow queue entries, hazards, replay, late writeback,
  regfile writes, and host/MMIO side effects.
- BE-to-FE redirect metadata must preserve the owning thread id. A nonzero
  thread that takes a CSR/translation redirect with zeroed branch metadata can
  restart FE under thread 0.
- UCE request credits are used as an ordering signal by fences. Count one
  outstanding request per complete forward command and verify `credits_empty`
  before trusting fence-related deadlock conclusions.

## Early-Handoff Contract

Any future early/speculative design needs:

- one explicit token per classified switch
- a launch condition tied to FE eligibility, not just target readiness
- a single authority for architectural thread ownership per phase
- a defined old-thread save point
- explicit cancel paths for reset, freeze, resume, flush, exceptions,
  non-ctxtsw redirects, and squashed switches
- exactly-once finalization

Without those properties, previous attempts have split FE and BE ownership into
ambiguous states.

## Useful Tests

Smoke and basic state:

```bash
make -C testing run-mt_ctxtsw_smoke_test TRACE=1
make -C testing run-mt_regfile_test TRACE=1
make -C testing run-mt_csr_isolation_test TRACE=1
make -C testing run-mt_frf_isolation_test TRACE=1
```

Hazards and side effects:

```bash
make -C testing run-mt_ctxtsw_late_wb_hazard_test TRACE=1
make -C testing run-mt_abi_preservation_test TRACE=1
make -C testing run-mt_ctxtsw_gpr_ring_stress TRACE=1
```

Performance and spacing:

```bash
make -C testing run-mt_ctxtsw_roundtrip_benchmark TRACE=1
make -C testing run-mt_ctxtsw_gap8_benchmark TRACE=1
make -C testing run-mt_ctxtsw_ring_throughput_benchmark TRACE=1
make -C testing run-mt_ctxtsw_pure_ring_stress_test TRACE=1
```

## Waveform Focus

When debugging a switch window, start with:

- ctxtsw detect/dispatch
- pending token create/accept/finalize
- FE sideband or FE command accept
- redirect PC/thread metadata
- FE queue clear/roll/enqueue/accept
- issue queue preissue/dispatch
- `commit_pkt.ctxtsw`
- `current_thread_id_lo`
- I-cache state, force, abort, request, critical/last response
- late writeback thread ID and destination register

Use `$zynq-parrot-waveform-debug` for the repo tool map and cycle-level analysis
workflow.

## Historical Submodule Identity Guard

A prepared candidate once recorded a nonexistent BlackParrot gitlink because a
short commit prefix was manually expanded instead of queried. The submodule
clone then failed with an unadvertised-object error; always obtain the complete
object ID with `git rev-parse HEAD`, use that exact value for `git update-index
--cacheinfo`, and verify it afterward with `git ls-tree HEAD import/black-parrot`.
This mistake recurred while preparing the full-endpoint replay fix when a hash
was typed into `update-index`; the commit was amended before validation. Pass
the `rev-parse` result through a shell variable and require an exact
actual-versus-gitlink comparison before committing or pushing.
It recurred once more while preparing the GPR-fit endpoint; the invalid gitlink
was caught by submodule checkout, amended before push, and the exact `ls-tree`
comparison is now mandatory before any candidate build starts.
The same manual expansion error recurred while creating repaired feature 57;
the top-level commit was amended before push. Candidate creation must assign
the output of `git rev-parse HEAD` directly to the `update-index --cacheinfo`
command rather than copying even a freshly printed object ID by hand.

An unrestricted recursive submodule update in a fresh replay worktree began
cloning the entire SDK dependency graph even though FPGA readiness needs only
the top-level RTL dependencies and BlackParrot's three externals. Stop that
update cleanly and initialize only the submodule paths named by the FPGA
readiness check; use `protocol.file.allow=always` when those reviewed sources
are local worktree paths.

Setting only `ZP_DIR` in the root testing harness changes the program and RTL
dependency paths but does not change `FULL_SIM_DIR`, which is derived from the
harness checkout's `TOP`. An endpoint preflight accidentally ran three guests
on the main checkout's model and was discarded. For every alternate-worktree
full-model run, pass both `ZP_DIR=<worktree>` and
`FULL_SIM_DIR=<worktree>/cosim/black-parrot-example/verilator`, then confirm the
simulator artifact path before interpreting the result.

Launching the outer Verilator make with `-j` caused its generated nested make
to report that the GNU make jobserver was unavailable, so compilation fell back
to one worker despite a requested build-job count. Let Verilator own the worker
count (or mark the nested recipe jobserver-aware) and verify multiple compiler
processes before relying on a parallel-build claim.

A manually chained smoke-image conversion once continued after `objcopy`
failed, leaving an empty redirected NBF that was then launched. Image-generation
chains must use `set -e`, the checkout's fully qualified cross-tool path, and a
nonempty/hash check before starting the simulator or board runner.

A historical two-resident/four-logical smoke was initially compiled with only
`BP_NUM_THREADS=2`, so its seeding payload used a one-bit context field while
the RTL decoded two bits. Always pass both physical `BP_NUM_THREADS` and logical
`BP_NUM_CONTEXTS` values matching the elaborated configuration.

A fresh historical worktree was initially tested through its old local
`testing/Makefile`; missing generated collateral caused repeated setup failures,
and the eventual legacy simulator run had no native target limit. Use the
current root harness with both `ZP_DIR` and `FULL_SIM_DIR` aimed at the candidate,
or skip the redundant local run when the candidate is only a clean application
of two independently verified RTL deltas; never launch an unbounded guest.
**Farm collection wildcard mismatch (2026-09-05):** the first multi-VM artifact collection failed because GNU tar did not expand the requested package wildcard even though the routed package existed. The collector now transfers the complete immutable PASS job directory and verifies the status, revision, summary, console, and packed-bitstream files locally before reporting success.

**Unpolled staging session left the old overlay in place (2026-09-05):** a short-yield orchestration call returned an active session with no visible output, and treating that as completion left the board's prior bitstream on disk. Always retain and poll an active command session to its exit code, then compare the board bitstream hash with the verified package before loading or running any NBF.

**New worktree followed by commands in the old directory (2026-09-05):** a chained `git worktree add` command created an experiment worktree but the following index update and commit still ran in the command's original working directory. The commit was immediately copied to the intended branch and the original local branch restored to its unchanged remote revision; candidate-preparation commands must end after `worktree add`, then use a separate command whose explicit working directory is the new worktree.

**Farm probe reported itself as an active Vivado job (2026-09-05):** the original process search matched the remote probe command because its own argument string contained the Vivado path pattern. Builder probes now match the exact `vivado` process name, while build launch retains its stdin-delivered path guard.

**Path-only cancellation missed Vivado child workers (2026-09-05):** out-of-context Vivado workers drop the immutable job path from their command lines, so the first cancellation stopped the wrapper but left its process group alive. The remaining exact process group was terminated and verified empty; farm cancellation now captures the worker's process-group ID before closing tmux and refuses success while that group or any Vivado process remains.

**Historical simulation reused an incompatible context-switch ELF (2026-09-05):** the first feature-56 smoke contained the retired `0x081` CSR because a shared `riscv/` symlink made an older artifact appear current. Historical-RTL tests must pass the exact `ZP_DIR`, force-rebuild the one ELF, and verify its relevant disassembly before execution; after rebuilding with CSR `0x800`, the test reached the switch and exposed a separate AXI response timeout.

**Skill validator was invoked as an executable (2026-09-05):** the repository skill validated successfully once `quick_validate.py` was run through `python3`; its installed mode is not executable. Invoke the validator with its interpreter instead of relying on file mode.

**Multi-builder probe stopped after bp1 (2026-09-05):** SSH consumed the `while read` loop's builder-name input, so `probe all` silently skipped bp2 and bp3. Multi-builder probe/list calls now redirect each SSH stdin from `/dev/null`; heredoc-based launch and cancellation retain their required stdin.

**Serialized runner was given only a remote basename (2026-09-05):** `run_pynq_serial.sh` rejected the call locally because it hashes and verifies a local NBF before selecting its staged remote basename. Pass the exact local NBF path; this failed before acquiring the board lock or starting `control-program`, so no board recovery was required.

**Lower-level simulation reused stale program collateral (2026-09-05):** replacing the test ELF did not rebuild `prog.riscv`, `prog.mem`, or `prog.nbf` because the historical Verilator Makefile declares those outputs without useful prerequisites. Before any direct historical-model run, move the old collateral aside, regenerate it, and require the copied `prog.riscv` SHA-256 to equal the selected ELF before interpreting the waveform.

**Existing simulator binary was not a reusable-model guarantee (2026-09-05):** invoking `make run` on a supposedly reusable historical model rebuilt generated objects because its RTL timestamps/dependencies had changed, while a separate stale program image could still survive. Treat model identity and guest-image identity as two independent gates: verify the exact BlackParrot revision used to build the executable and verify the exact ELF-to-`prog.riscv` hash before every run.

**Direct simulator controls reused the preceding guest (2026-09-05):** two apparent control runs compiled new ELFs but invoked the low-level `make run` target without first removing `prog.riscv`, so its dependency-free collateral rule kept executing the earlier U-mode probe. Use `make -C testing run-<test>` for every changed guest, or explicitly verify the selected ELF and copied `prog.riscv` hashes before a lower-level run; equal NBF line counts and missing test-specific markers are grounds to quarantine the result.

**Passing waveform was overwritten before analysis (2026-09-05):** a known-passing context-switch trace was replaced by the next ordinary smoke run while waveform analysis was still pending. Archive each closed FST under a revision/test-specific immutable name immediately after the run, and do not launch another trace in that simulator directory until the archived hash is recorded.

**Successful historical simulations end with cleanup noise (2026-09-05):** the legacy Verilator harness prints `CORE PASS` and returns success before a DPI GPIO final-block assertion reports that `fini()` was not called. Treat the explicit terminal result and process exit code as the functional gate, retain the log, and do not misclassify this known post-result teardown assertion as a guest failure.

**Recursive Make ran during a dry run (2026-09-05):** `make -n` still executed recipe lines containing `$(MAKE)`, so a preview of the Linux demo target removed and partly recreated the SDK's generated work tree. Never dry-run a destructive recursive-Make target; inspect its expanded recipe or use a separate non-mutating preflight target instead, and require a fresh image build after such contamination.

**Unbounded nonresident simulation wasted debug time (2026-09-05):** the first repaired-feature-63 ring run was launched without `BSG_TRACE_TIMEOUT_S` and had to be interrupted after the expected switch sequence stopped progressing. All potentially stalling minimal-model guests must use the simulator's native trace timeout from their first run, even when the test is expected to pass.

**Interrupted FST needed its external hierarchy (2026-09-05):** a byte-identical copy of an interrupted `dump.fst` could not be reopened because its hierarchy remained in sibling `dump.fst.hier`; a normally closed PASS trace was self-contained and had no sidecar. Artifact collection must run with fail-fast shell semantics, copy the sidecar when present, and validate the archived trace with `fstminer -n` before treating it as reusable evidence.

**Historical SDK selected Python 2 for the demo DTS wrapper (2026-09-05):** the first tiny-init image build failed before DTS creation because the SDK's default `PYTHON=python` invoked Python 2 against the Python 3 wrapper. The image target now preflights an explicit `BP_DTS_PYTHON` and passes it into the recursive SDK build; restart from `clean_buildroot` after this failure so no partial Buildroot output is trusted.

**Historical SDK hid the complete Linux toolchain (2026-09-05):** the clean tiny-init build compiled the kernel but failed when its outer Makefile invoked `riscv64-unknown-linux-gnu-strip` from the checkout's incomplete install prefix. The image flow now derives, preflights, and injects the compiler-matched tool directory for every recursive Linux/OpenSBI step; its narrowly scoped resume target preserves a completed kernel only after a later packaging failure.

**Pinned OpenSBI lacked the selected BlackParrot platform (2026-09-05):** after the toolchain fix, the SDK requested `PLATFORM=generic/blackparrot`, but that directory existed only as untracked files in the old known-working SDK copy, not in the pinned OpenSBI commit. The Linux test flow now tracks the four known-working platform files as an explicit overlay and materializes them before every image build, eliminating the hidden home-directory dependency.

**Initramfs verification used the wrong archive pathname (2026-09-05):** the first manual extraction requested `./ctxtsw_user_tiny`, while the cpio entry is `ctxtsw_user_tiny`, so it produced an empty comparison rather than validating the embedded program. The image target now extracts the exact archive entry in a temporary directory and byte-compares it with the current ELF before packaging an NBF.

**Feature101 ring run reused the smoke NBF (2026-09-05):** the selected ring ELF and copied `prog.riscv` differed from the prior test, but stale `prog.nbf` still printed the smoke test's PASS marker; the entire result was quarantined before synthesis. Historical-model gates must archive/hash the regenerated NBF itself and require the test-specific PASS marker in addition to matching ELF and `prog.riscv` hashes.

**Feature101 Vivado resolved an obsolete BaseJump RAM wrapper (2026-09-05):** the first admitted route failed during elaboration because BlackParrot requested `ram_style_p` while the reconstructed top level still pinned a wrapper without that parameter; local Verilator had resolved the compatible nested copy. Build readiness now checks the exact top-level wrapper Vivado uses, and the candidate must pin the known BRAM-feature BaseJump revision rather than dropping the block-RAM attribute.

**Historical model build used an incomplete collateral root (2026-09-05):** the first feature101 RAM-style validation build stopped before Verilator because its isolated test-only `ZP_RISCV_DIR` lacked `bootrom.none.riscv`. Model builds must use the known-complete `/home/coyang/zynq-parrot/riscv` collateral root; test ELFs may remain isolated and be selected only for the subsequent run stage.

**Final Linux demo intentionally contains context-CSR instructions (2026-09-05):** applying the raw NBF collision scanner to `linux-ctxtsw-tiny-init.nbf` reports CSR `0x801`/`0x802` because the embedded acceptance program deliberately executes them. Run the collision guard against the unmodified baseline Linux image, then use `linux-tests` image validation to prove that the only added executable is the byte-identical context-switch PID 1; do not require the final demo image itself to be collision-free.

**Recursive historical submodule initialization fetched irrelevant SDK trees (2026-09-05):** a fresh candidate worktree used `submodule update --recursive`, which began cloning the complete SDK ecosystem and still could not fetch an archived nested BaseJump object. Stop that operation cleanly; initialize only the top-level and BlackParrot dependencies named in `LINUX_FEATURE_BISECT.md`, and fetch an unavailable pinned nested object from the trusted local seed checkout.

**Filtered simulator output masked an RTL fatal (2026-09-05):** the testing recipe piped the recursive simulator through `grep`, so a deterministic `$fatal` still returned status zero when `grep` matched earlier progress lines. The testing Makefile now uses Bash with `pipefail`; require both the guest marker and the unmasked recursive exit status before accepting a run.

**Ordinary local timing hid the physical FE handoff race (2026-09-05):** the U-mode nonresident guest passed both old and fixed RTL because the local I-cache accepted the pending redirect before stale source instructions could dispatch. A simulation-only invariant now directly checks that BE remains active whenever FE still owns the captured redirect; the old FSM fails it and the fixed FSM passes, while the routed `ABX` result remains the functional physical reproduction.
