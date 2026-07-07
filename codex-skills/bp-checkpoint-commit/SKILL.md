---
name: bp-checkpoint-commit
description: Use when working on BlackParrot or zynq-parrot changes that should be preserved as small verified checkpoints, especially after a functional fix, a debugging milestone, or a known-good test result.
---

# BlackParrot Checkpoint Commit

Use this skill when the task needs a disciplined checkpointing workflow rather than ad hoc commits.

## Goals

- keep changes small and attributable
- commit only known-good states
- separate functional fixes from debugging noise
- leave a clear rollback point before the next experiment

## Workflow

1. Inspect the current worktree before touching git.
2. Identify whether the current change is:
   - functional fix
   - debugging instrumentation
   - cleanup/refactor
   - documentation
3. Do not mix categories in one checkpoint unless the smaller split is impossible.
4. Run the most relevant verification for the changed surface.
5. Record the concrete evidence that makes the state “known-good”.
6. Stage only the intended files.
7. Commit with a message that describes the verified effect, not just the edited files.

## Verification Standard

Before committing, capture at least one of:

- targeted smoke test passed
- clean rebuild passed
- benchmark produced expected result
- runtime failure was reproduced and isolated

If the state is intentionally a debug checkpoint, say that in the commit message.

## Commit Message Pattern

Prefer:

- `fix ctxtsw retire gating in bp_be_pipe_sys`
- `restore minimal-example clean nbf load flow`
- `debug nbf post-unfreeze startup hang`

Avoid vague messages like:

- `misc fixes`
- `wip`
- `more changes`

## Staging Discipline

- stage only files that belong to the current checkpoint
- do not scoop up unrelated dirty files
- if another file is user-dirty or outside the current line of work, leave it alone

## After Commit

- note the exact test command and result in your final response
- if the checkpoint is meant to be built on immediately, say what the next experiment is

