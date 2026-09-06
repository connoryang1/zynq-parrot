This file is the entry point for the supported BlackParrot FPGA checkout. It records what has been validated, where to run tests, and how to recover the older experiments without confusing them with the current implementation.

# Supported checkout

Use `/home/coyang/zynq-parrot` and its `import/black-parrot` submodule.
Both fork repositories integrate on `master`; start new work on dedicated branches.
The top-level gitlink selects RTL `70a27d32b`, whose hardware and dependency
content is identical to FPGA-accepted `25089713baa090aba719ec0f18f82ff9214d5f0d`.

The reviewable history has five top-level commits (build integration, regressions,
Linux demo, operational tooling, documentation) and three RTL commits
(dependencies/loading, the coupled context-switch implementation, documentation).
These organize the accepted endpoint; they are not claims that every synthetic
intermediate was separately run on the FPGA. Separate upstream changes from the
old fork master were not merged into this accepted source.

## What works and what is not claimed

- PYNQ-Z2, static two resident register banks and four logical integer contexts.
- Private on-chip integer backing memory and translated U-mode 0→2→0 handoff.
- Linux boots through OpenSBI to a PID-1 C program, performs a target-context
  syscall, verifies logical ID and independent/restored `s11`, then powers off
  with `CORE[0] PASS`.
- Ordinary floating-point execution remains. Complete nonresident FP preservation,
  independent Linux scheduling of contexts, and untrusted-context isolation are
  **not** accepted features. The PID-1 test is not an interactive-shell acceptance
  test.

See [architecture](CONTEXT_SWITCH_ARCHITECTURE.md), [tests](testing/README.md),
and [Linux demo](linux-tests/README.md). Keep protocol rationale near the RTL and
use commit messages to explain changes, rather than adding another status diary.

## Verification

Preserve existing logs/waveforms, finish each clean command, then build/run:

```sh
make -C testing clean
make -C cosim/black-parrot-minimal-example/verilator clean
make -C testing run-mt_umode_nonresident_sv39_data_handoff_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

Use the available CPU/memory budget for inner build jobs, but serialize guests.
The maintained suite has 13 tests; its README explains the invariant each covers.
Core-wide CSR `0xCC0` measures elapsed cycles across context switches; do not
substitute a context-restored `mcycle`.

The prior clean simulator baseline is 5.13 resident and 11.13 nonresident
cycles/switch, with two matching runs in `logs/docs-integration-20260906/`.
Final suite/history validation is retained in `logs/reviewable-integration-20260906/`.
All 13 tests compile; the clean traced handoff and resident smoke pass, and both
benchmark repeats match the prior 5.13/11.13-cycle result.
Guest success must precede the known GPIO `fini()` teardown assertion; these are
not claims of warning-free simulator shutdown.

## FPGA acceptance identities

The 2026-09-06 accepted route used top `032420c33624d08df2a5852da9d0c49394fa1cef`
and RTL `25089713b`: 46,851 LUTs, 80 BRAM tiles, 11 DSPs, WNS +1.781 ns,
TNS 0. Physical benchmark spacing was 5.10 resident / 11.12 nonresident
cycles/switch, distinct from waveform handoff latency and cold-cache tails.

| Artifact | SHA-256 |
| --- | --- |
| Packed FPGA image | `ffbb0142dcac50ff2d3406cc0d56a85cd4bf6457c2e7506f599f408160d998c9` |
| Extracted bitstream | `9ce659b764213adbf7ca1b347b8c43e4a58c6661e092a35b12ca1ceb9a3b9824` |
| Linux PID-1 image | `0728cd34650d49c4fe38522d6e139befb51732b426be1b1d1eec11d3ced36959` |
| Translated bare-metal handoff | `6cbee152430e0aa5ec471664cf8e1874487d166a459fcce69c38c8082e69bb01` |
| FPGA global-cycle benchmark | `da85ec1f46c8217241adacb0b8c801bef65968db2c6f25d09bfca8fd337152f2` |

Packages are under `logs/fpga-farm/bp3/20260906T032705Z-032420c3/`;
board evidence is under `logs/pynq-validation/translated-handoff-recovery-20260906/`.
That directory's `accepted-images/` retains the exact bare-metal NBFs formerly
in the removed handoff worktree. Generated test files elsewhere are not necessarily
byte-identical substitutes.

## History and recovery

Original commits and authorship are retained at published tags:
`archive/pre-review-series-20260906` preserves the full pre-split snapshot in
each fork; `archive/docs-before-cleanup-20260906` preserves the older plans
and investigation diaries. For example:

```sh
git show archive/docs-before-cleanup-20260906:WORK_LOG.md
git show archive/pre-review-series-20260906:testing/mt_ctxtsw_gap8_benchmark.c
```

Obsolete remote branch tips are preserved under
`archive/retired-branches-20260906/<branch>` before pruning; earlier local-only
tips remain under `archive/branches-20260906/`. Old fork/upstream master tips
are separately archived in the RTL repository. Use a fresh branch/worktree to
inspect historical code rather than applying it over the accepted checkout.

Full backups of 114 removed local worktrees remain in
`/home/coyang/blackparrot-experiment-archive/20260906`. Each has a `.tar.gz`,
checksum, identity, and dirty-file status record; tar members include source and
Git administration data relative to `/`. Verify checksums and extract into a
fresh directory, not the live checkout; archived `.git` files contain old paths.
The non-Git `zp-feature110-rfbypass-validation` folder is preserved there too.
These filesystem backups are local, not uploaded.

Earlier uncommitted changes are also preserved locally in each repository's
`archive/pre-consolidation-dirty-20260906` stash tag. No installed tools, remote VM
directories, or board state were removed by this cleanup.
