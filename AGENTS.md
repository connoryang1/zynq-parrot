# AGENTS

This file defines the repository-specific development, verification, and
operational rules for the BlackParrot FPGA worktree.  It keeps long-running
hardware experiments reproducible and prevents debugging shortcuts from being
mistaken for validated functional results.

> Purpose: This file defines the engineering workflow for this BlackParrot-on-FPGA checkout. It explains how to make changes, validate them safely, and preserve reproducible evidence. It also records the project conventions that keep the Linux/context-switch investigation understandable to someone joining later.

## Repository Skills

- Read the matching `codex-skills/*/SKILL.md` before acting on BlackParrot-specific workflows.
- Use `bp-targeted-verification` to select simulation gates.
- Use `bp-benchmark-validation` before interpreting context-switch measurements.
- Use `bp-fpga-synthesis` for build-readiness, background Vivado implementation, utilization,
  timing, bitstream fit, or FPGA deployment work.
- Use `bp-parallel-safe-runs` before launching concurrent or background jobs.

## Development Philosophy

- Prefer small, isolated changes over broad refactors.
- Test after each meaningful step.
- Commit only known-good states.
- If an experiment does not help or introduces ambiguity, revert it promptly.
- Keep debugging changes separate from functional fixes whenever possible.
- Do not mix performance work, correctness fixes, cleanup, and documentation in one large unverified change.

## Git Workflow

- Do new development on a dedicated branch, not on `master`.
- Create a fresh branch before substantial work whenever practical.
- Keep `master` as a stable integration branch.
- Make checkpoint commits at verified working states so there is always a clear rollback point.
- If a line of investigation fails, revert the experiment instead of stacking more guesses on top of it.
- Prefer branch-based experimentation over leaving long-lived uncommitted changes in the main worktree.
- In a new historical top-level worktree, initialize a submodule and verify that its `.git` file
  exists before running `git -C <submodule> ...`. An uninitialized but existing submodule directory
  can make Git discover the parent repository and accidentally apply the command to the top-level
  worktree instead.
- Before building a historical BlackParrot candidate, materialize and verify all three nested
  source submodules—`external/basejump_stl`, `external/HardFloat`, and `external/bedrock`—at their
  recorded gitlinks. A similarly named top-level checkout does not satisfy BlackParrot's nested
  source path.

## Testing Expectations

- Re-run the most relevant smoke test after every critical RTL or software change.
- For this project, after RTL or test-program changes use the clean target flow:
  `make clean run ... TRACE=1`.
- When using parallel Make, invoke `clean` to completion first and launch the build/run as a
  separate command. Multiple top-level goals such as `make -j12 clean run-...` may execute in
  parallel, deleting simulator artifacts while the run target is building them.
- When using the testing harness directly, prefer the equivalent `make -C testing ... TRACE=1`
  form so commands run from the repository root without changing directories.
- A direct simulator `make -C cosim/.../verilator run` only copies an existing ELF; rebuild a
  changed test through `make -C testing` before using that lower-level flow.
- Do not run testing flows concurrently by default. The testing harness and simulator flow share
  program, build, waveform, and log artifacts, so parallel runs can overwrite each other unless
  separate output/build directories have been explicitly configured and verified.
- For an expected local guest stall, use the simulator's native target-runtime limit rather than
  only a host-side `timeout`; verify no child simulator remains before another run and archive a
  waveform only after the target exits cleanly.
- If a board `control-program` run ends through its target-runtime limit, an SBI-reset terminal
  probe, or interruption, power-cycle the board and reload the overlay before another run.  The PL
  may no longer have a trustworthy reset/retirement state; never infer RTL behavior from a
  follow-on run that skipped this recovery.
- Never use `sudo -n ./control-program` with a placeholder file to test board authorization: a
  permitted command begins a real privileged run before it reads the image. Use the serialized
  runner with a verified NBF, and treat any accidental direct launch as a contaminated-board event
  requiring a power cycle and overlay reload.
- After any PYNQ power cycle, wait for `scripts/wait_pynq_ready.sh <ssh-host>` before loading an
  overlay. An open SSH port is not sufficient: PYNQ's own boot service continues for roughly a
  minute, and an early overlay load has caused invalid board runs.
- Always include `TRACE=1` for context-switch debug and performance validation runs so
  waveform evidence is available by default.
- Before a trace-enabled full rebuild, check free temporary-space capacity. Do not let a
  failed trace build fall through to an existing simulator executable: treat any result after
  a failed build as invalid, clean the target artifacts, and rerun only after the build succeeds.
- When changing shared infrastructure, rerun at least one previously known-good flow before trusting new debug results.
- Incremental tests are acceptable only for quick local checks that do not depend on
  regenerated programs, RTL, wrappers, or waveform output.
- Do require a clean rebuild at key checkpoints:
  - before waveform/debug sessions that depend on the local build wrapper
  - after substantial cross-cutting RTL or build-system changes
  - before calling a branch review-ready
  - after long stretches of incremental-only validation
- For multistep work:
  - establish a baseline
  - make one change
  - rebuild
  - rerun the targeted test
  - compare behavior before moving on
- For RTL changes that can affect FPGA area or timing, run a routed PYNQ-Z2 implementation at
  milestone checkpoints. Keep it out of the foreground iteration loop and record exact revisions,
  utilization, WNS/TNS, Vivado version, configuration, and artifact path.

## Debugging Expectations

- Localize the failing stage before changing logic.
- Prefer measurement and traces over speculation.
- For every workflow mistake, misleading result, or infrastructure failure, record a concise
  entry in the relevant persistent troubleshooting/verification log before moving on: symptom,
  confirmed or suspected cause, evidence, and the guardrail or procedure that prevents a repeat.
  Do not record a root cause as confirmed until the evidence distinguishes it from alternatives.
- When an FPGA marker localizes a Linux failure to an instruction boundary, capture the live
  architectural input at that same boundary before designing a local reproduction.  First validate
  any injected value reporter at the same PC with a known-zero source, then retain only a compact,
  dependency-safe transcript that ends in `CORE[0] PASS`; an unvalidated or stale reporter value is
  not evidence.
- For context-switch performance, track the waveform-derived added overhead
  separately from benchmark latency/throughput. The primary overhead metric is
  the number of dead or discarded cycles from architectural `commit_pkt.ctxtsw`
  / redirect to the first useful target-context FE queue or BE dispatch, with
  I-cache miss/abort/refill tails called out separately.
- Parallelize independent reads, builds, analysis scripts, and code searches whenever
  possible; use subagents for independent code or waveform analysis when they can run
  without blocking the critical path.
- Remove temporary debug instrumentation once the result is understood or checkpointed.
- If debugging changes start to break unrelated known-good flows, return to the last proven baseline before continuing.

## Iteration Log

- Maintain [`WORK_LOG.md`](WORK_LOG.md) as the chronological record of meaningful engineering events.
- Add a one- or two-sentence, self-contained entry only for substantial progress: a confirmed root cause,
  definitive fix or revert, meaningful FPGA/Linux outcome, material tooling change, or commit/push.
- Keep routine probes, repeated failures, and intermediate marker splits in retained transcripts or detailed
  status documents rather than this log. State the artifact or command when useful and distinguish confirmed
  results from hypotheses. Start every entry with a short bold milestone title such as **Linux boot progress**,
  **New reproduction**, **Fix validation**, or **FPGA build/deployment**.
- Every Markdown file created or edited in this repository must begin with a short plain-language purpose
  statement (two to four sentences) so it is understandable without prior project context.

## Cleanup / Refactor Policy

- Cleanup comes after correctness and verification, not during active bug triage.
- Only refactor once behavior is stable and there is a known-good checkpoint to compare against.
- Delete dead code and redundant wrappers incrementally, with tests after each step.
