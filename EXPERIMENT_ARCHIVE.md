This file explains where superseded BlackParrot experiment directories were preserved during cleanup. It records how to inspect their source and evidence without replacing the supported checkout or losing uncommitted work.

# Experiment archive — 2026-09-06

The archive is `/home/coyang/blackparrot-experiment-archive/20260906`, outside
the canonical `/home/coyang/zynq-parrot` checkout. The canonical source, installed
tools, current FPGA artifacts, and board configuration are not cleanup targets.
No remote VM or FPGA-board directories are removed by this local cleanup.

Cleanup completed for all 114 registered historical worktrees: 47 home-directory
top-level experiments, 35 standalone RTL experiments, and 32 temporary synthesis
snapshots. There are 114 completed archives with matching checksums and identity
records, and no partial archives. Filesystem free space increased from roughly
24 GB to 38 GB while preserving recoverable backups.

Each removed worktree has:

- `<name>.tar.gz`: its complete directory and Git administrative directory,
  including dirty files, ignored outputs, and nested repository object databases;
- `<name>.tar.gz.sha256`: checksum of the compressed archive;
- `<name>.identity`: original source/admin paths, parent repository, and HEAD;
- `<name>.status`: staged, unstaged, and untracked file status before archiving;
- a parent-repository tag `archive/worktrees-20260906/<name>` preserving its HEAD.

Archives do not follow symlinks into shared installations. The cleanup helper
compares the archive against the original before permitting `git worktree remove`.
Branches are retained, including accepted `linux-user-handoff-fix`; removal of a
worktree is not deletion of its commits. These archives and tags are local backups,
not automatically uploaded to GitHub.

## Inspect or recover

Verify the archive checksum and list its contents first. Extract into a fresh
temporary directory, not over the canonical checkout. Archive member names retain
their original path relative to `/`, such as `home/coyang/zp-...`.

For a clean committed reconstruction, use `git worktree add` from the appropriate
parent repository and the recorded tag. For uncommitted experiments, inspect the
extracted source and `.status` record and restore the intended files to that new
worktree. Do not blindly copy archived `.git` files: they contain the original
worktree locations. Nested Git objects are also archived if a historical submodule
commit is no longer obtainable upstream.

The non-Git `zp-feature110-rfbypass-validation` evidence directory is retained
directly under the archive root rather than removed. Its contents are unchanged.

## Accepted artifact relocation

The two exact FPGA NBFs formerly under
`/home/coyang/zp-linux-user-handoff-fix/riscv/bp-tests/` are additionally retained in
`logs/pynq-validation/translated-handoff-recovery-20260906/accepted-images/`:

| File | SHA-256 |
| --- | --- |
| `mt_umode_nonresident_sv39_handoff_test_fpga.nbf` | `6cbee152430e0aa5ec471664cf8e1874487d166a459fcce69c38c8082e69bb01` |
| `mt_ctxtsw_nonresident_overhead_benchmark_fpga.nbf` | `da85ec1f46c8217241adacb0b8c801bef65968db2c6f25d09bfca8fd337152f2` |

Historical logs retain their original paths; this table records relocation without
rewriting past evidence. Current generated files in `riscv/bp-tests/` are not
necessarily byte-identical replacements. The canonical local BlackParrot submodule
URL and tracked `.gitmodules` entry now point to
`git@github.com:connoryang1/black-parrot.git`, not an experiment directory that
cleanup can remove or the upstream repository that does not own our feature branch.
