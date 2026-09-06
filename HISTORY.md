This file explains how to navigate the project's accepted integration and recover the longer research history. Old experiments are preserved for provenance, but they are not instructions for the current checkout.

# History and review

Start with [CURRENT_CHECKOUT.md](CURRENT_CHECKOUT.md), then the architecture and
test guides it links. The supported result is the accepted FPGA endpoint, not
the union of every experimental branch.

## Historical documentation

Both repositories have checkpoint tag `archive/docs-before-cleanup-20260906`.
In the top-level repository it preserves the full old `WORK_LOG.md`,
Linux bisect/status diaries, register-cache plan, resident-substrate plan,
Banyan comparison, DMA experiment log, PR guide, and earlier architecture/research
notes. Inspect a document without restoring it into the checkout:

```sh
git show archive/docs-before-cleanup-20260906:WORK_LOG.md
git show archive/docs-before-cleanup-20260906:REGISTER_CONTEXT_CACHE_PLAN.md
```

These documents contain superseded claims, failed experiments, and instructions
for worktrees that no longer exist. Current guidance takes precedence.

## Integration policy

Top-level `master` integrates the accepted snapshot as one concise commit, while
the published `consolidated-linux-context-switch` branch and checkpoint tags
retain the original authorship and detailed history. Never squash abandoned candidates
into the accepted source or claim that history cleanup is new hardware validation.

The RTL fork's `master` (`01c134e0a` at cleanup) has 29 upstream-only commits
absent from the accepted branch, touching CSR/interrupt behavior, CCE logic,
and the BaseJump dependency among other files. Keep the tested gitlink until
those changes are reviewed and validated; do not force-push or silently merge
unrelated RTL merely to make branch names match. The local RTL `master`
(`f91010f65`) includes twelve additional upstream commits and is also unchanged.

Cleanup replaced 65 top-level and 55 RTL local branch names with verified
exact-tip tags under `archive/branches-20260906/`. These branch-archive tags are
local; the pre-cleanup documentation checkpoint is also published on each fork.
Remote experiment branches are retained to avoid
disrupting collaborators. The [directory archive](EXPERIMENT_ARCHIVE.md)
separately preserves dirty files and build evidence that ordinary Git commits
do not contain.
