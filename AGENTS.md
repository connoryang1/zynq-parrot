# AGENTS

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

## Testing Expectations

- Re-run the most relevant smoke test after every critical RTL or software change.
- For this project, after RTL or test-program changes use the clean target flow:
  `make clean run ... TRACE=1`.
- When using the testing harness directly, prefer the equivalent `make -C testing ... TRACE=1`
  form so commands run from the repository root without changing directories.
- A direct simulator `make -C cosim/.../verilator run` only copies an existing ELF; rebuild a
  changed test through `make -C testing` before using that lower-level flow.
- Do not run testing flows concurrently by default. The testing harness and simulator flow share
  program, build, waveform, and log artifacts, so parallel runs can overwrite each other unless
  separate output/build directories have been explicitly configured and verified.
- Always include `TRACE=1` for context-switch debug and performance validation runs so
  waveform evidence is available by default.
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

## Cleanup / Refactor Policy

- Cleanup comes after correctness and verification, not during active bug triage.
- Only refactor once behavior is stable and there is a known-good checkpoint to compare against.
- Delete dead code and redundant wrappers incrementally, with tests after each step.
