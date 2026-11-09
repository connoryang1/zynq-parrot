This page maps the protected-RPC pull requests across the ZynqParrot and BlackParrot repositories. It records their dependency order, review scope, integration choices, and the exact branches that preserve the pre-review history.

# Protected-RPC review stack

## Dependency map

```text
BlackParrot review base
  └─ black-parrot #6: protected-RPC RTL
             │
             └── pinned by ZynqParrot #4: programs, evidence, and design
                                      └─ ZynqParrot #5: asynchronous verification
```

| Layer | Pull request | Base → head | Dependency and scope |
| --- | --- | --- | --- |
| RTL mechanism | [black-parrot #6](https://github.com/connoryang1/black-parrot/pull/6) | `review/protected-rpc-base` → `feat/protected-rpc` | Implements the minimal fixed-entry `pcall`/`preturn` mechanism. |
| Top-level evaluation | [zynq-parrot #4](https://github.com/connoryang1/zynq-parrot/pull/4) | `review/protected-rpc-base` → `feat/protected-rpc` | Pins the BlackParrot feature commit and adds tests, evidence, performance interpretation, and the bounded Linux design. Depends on BlackParrot #6. |
| Verification tooling | [zynq-parrot #5](https://github.com/connoryang1/zynq-parrot/pull/5) | `feat/protected-rpc` → `tools/rpc-background-verification` | Adds the isolated asynchronous simulation ladder. Depends on ZynqParrot #4. |

The stack is therefore partially linear rather than a single same-repository chain. BlackParrot #6 and ZynqParrot #4 are a cross-repository pair, while ZynqParrot #5 is a conventional stacked PR above #4.

## Review and integration order

1. Review BlackParrot #6 first because it defines the hardware contract.
2. Review ZynqParrot #4 against that exact RTL because it owns the software contract, adversarial tests, measurements, and retained evidence.
3. Review ZynqParrot #5 last because its launcher executes tests introduced by #4.

The two protected-RPC PRs currently target dedicated review-base branches rather than `master`. They expose only the recent RPC range for review; merging them into those bases alone does not integrate the feature into `master`. After review, either retarget them to the intended integration branches or open final integration PRs from the reviewed heads.

ZynqParrot #4 pins BlackParrot commit `f2f5f246a`. Prefer a BlackParrot merge method that preserves this exact commit. If BlackParrot #6 is squash-merged or otherwise rewritten, update the top-level submodule gitlink to the resulting integrated commit and rerun the scoped validation before integrating ZynqParrot #4.

Once #4 is integrated, retarget #5 from `feat/protected-rpc` to the resulting ZynqParrot integration branch. Its displayed diff should remain limited to the asynchronous verification infrastructure and publication records.

## Current status and recovery

As of 2026-10-19, all three PRs are open, non-draft, cleanly mergeable, and backed by clean local worktrees. No PR has been merged yet.

The pre-reword histories remain recoverable from:

- ZynqParrot `archive/rpc-history-before-reword-20261019`
- BlackParrot `archive/rpc-history-before-reword-20261019`

The reworded commits are source-tree-identical to their archived counterparts. Fast validation covered shell syntax, five launcher unit tests, repository skill validation, `git diff --check`, and Git object integrity; the history-only rewrite did not require another simulator or FPGA run.

The final protected-RPC endpoint remains accepted in traced simulation but still needs its closing routed/physical FPGA check. That run should occur once after the review state is settled, not inside the normal software iteration loop.
