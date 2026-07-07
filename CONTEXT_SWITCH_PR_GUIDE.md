# Context-Switch PR Guide

Use this when preparing or reviewing a PR for the resident context-switch work.

## Recommended Structure

1. Purpose and claim
   - What the PR changes.
   - What behavioral or performance claim it supports.
   - What kind of review is needed.
2. Software model
   - `CSR 0x081`: switch to a target resident context.
   - `CSR 0x082`: seed a dormant context's entry/resume PC.
   - `CSR 0x083`: seed remote architectural register state.
3. Architecture
   - BE owns architectural switch finalization.
   - The current `ctxtsw-isd-repair` branch may perform early FE
     sideband/token work, but BE ownership still finalizes through the
     context-switch commit path.
   - FE receives an explicit restart/context-switch command.
   - Per-thread state covers registers, CSR/control state, saved PC,
     privilege, translation, ASID, and FE thread identity where implemented.
4. Implementation areas
   - `import/black-parrot`: RTL implementation.
   - `testing/`: smoke, correctness, hazard, and benchmark programs.
   - `tools/`: waveform/cycle-analysis helpers.
   - top-level docs: status, plan, troubleshooting, and validation evidence.
5. Validation
   - Exact commands.
   - Pass/fail output.
   - Benchmark numbers.
   - Waveform-derived cycle deltas when making timing claims.
6. Risks and limits
   - Tests not rerun.
   - Dirty worktree or submodule caveats.
   - Known performance tails.
   - Claims that apply only to warm/minimal benchmark shapes.

## Evidence Checklist

- top-level branch and SHA
- `import/black-parrot` branch and SHA
- `git status --short` for both repos
- test commands and outputs
- VCD path and analysis command for cycle claims
- measured endpoints, not just a single cycle number
- explanation of I-cache miss/abort/refill tails when present

## Review Focus

- context-switch event ownership is singular
- rollback/cancel paths are explicit
- thread IDs follow issue, hazard, replay, writeback, and side effects
- target-context instructions cannot issue unsafe side effects before the old
  context-switch is architecturally safe
- performance claims subtract benchmark setup, printing, loop overhead, and
  unrelated miss/refill latency
- debug scaffolding is removed or clearly isolated
