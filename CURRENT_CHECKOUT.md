This file identifies the supported BlackParrot checkout and explains the older experiment directories. It separates the FPGA-validated implementation from historical debugging attempts and records how to recover work preserved during consolidation.

# Canonical checkout

Use `/home/coyang/zynq-parrot` for development and its `import/black-parrot` directory for RTL. Both repositories use branch `consolidated-linux-context-switch`; the RTL is exactly `25089713baa090aba719ec0f18f82ff9214d5f0d`, not the old `linux-satp-mode-filter` checkout.

The RTL-facing configuration and active test suite come from accepted top-level checkpoint `57bcd994`. Its RTL matches routed checkpoint `032420c3`; subsequent changes packaged the acceptance tests. The coordinator's host runtime limits, owned-DRAM handling, native command-line arguments, configuration stamps, farm controls, skills, Linux-image tooling, and investigation records are retained rather than replaced by older copies. The FPGA validation ladder now requires explicit test selection; stale or unsupported default FP-copy tests are no longer selected automatically.

## What is accepted

- Static PYNQ-Z2 configuration: two resident register banks, four logical integer contexts backed by on-chip storage.
- Physical FPGA: Linux reaches PID 1, whose C program switches 0→2→0, calls Linux from the target context, checks register restoration, and exits with `CORE[0] PASS`.
- Normal floating-point execution is retained. The last three nonresident FP-copy feature commits are excluded for device fit; do not claim complete FP context preservation.
- Routed fit and physical benchmark evidence: [Linux status](LINUX_BOOT_STATUS.md) and [work log](WORK_LOG.md). Consolidating files does not constitute another hardware run.

For a traced local translated handoff gate, run cleanup to completion before starting the test:

```bash
make -C testing clean
make -C cosim/black-parrot-minimal-example/verilator clean
make -C testing -j12 run-mt_umode_nonresident_sv39_data_handoff_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1
```

Archive existing logs/waveforms before cleanup. Run tests serially; `-j12` parallelizes compilation, not access to the shared simulator outputs. See [linux-tests/README.md](linux-tests/README.md) for the Linux C demonstration and image builder.

## Consolidation verification

Consolidation verification (2026-09-06): a clean traced model passed the Sv39
instruction/data nonresident handoff, resident smoke passed after preserving host
safeguards, and the Sv39 handoff passed again on that final host setup. Logs and
closed waveforms are under `logs/consolidation-20260906/`. The existing BaseJump
GPIO `fini()` teardown assertion still occurs after guest PASS; the accepted
harness explicitly handles that known post-PASS issue, so these are guest
correctness passes, not a claim of warning-free simulator shutdown.

## What the other attempts were

| Directory family | Purpose | Status now |
| --- | --- | --- |
| `zp-ce-*`, `bp-ce-overlay`, `zp-4015-original` | Historical Linux baselines and compatibility overlays | Historical comparisons, not current fixes to merge |
| `zp-feature-*`, `bp-feature-*` | Feature-prefix bisection and focused replay, CSR, cache, and register-file repair candidates | Superseded integration candidates; retain their individual evidence |
| `zp-linux-user-handoff-fix`, `bp-linux-user-handoff-fix` | Final translated userspace handoff repair and acceptance work | Source of the canonical RTL; preserved in the experiment archive |
| `/tmp/zynq-parrot-fpga-*` | Immutable inputs to individual synthesis jobs | Build evidence, not development checkouts |

The inventory found 47 `zp-*` and 35 `bp-*` registered worktrees plus 32 temporary synthesis worktrees. All 114 have now been archived, verified, and removed from their original locations; only the canonical checkout remains registered in each repository. Branches, commits, dirty files, and build evidence are preserved, not discarded. See [EXPERIMENT_ARCHIVE.md](EXPERIMENT_ARCHIVE.md) for the backup location and recovery instructions.

## Preserved work and recovery

Before consolidation, the coordinator had uncommitted host/test/probe edits and the old RTL checkout had three frontend diagnostic edits. Each repository preserves its own complete stash under the local tag `archive/pre-consolidation-dirty-20260906`; the original top-level committed state remains `e4242c1c` and the old RTL state remains `3df31a94e`.

Inspect the archive without applying it to the validated checkout:

```bash
git stash show --stat --include-untracked archive/pre-consolidation-dirty-20260906
git -C import/black-parrot stash show --stat archive/pre-consolidation-dirty-20260906
```

Recover selected files on a separate diagnostic branch, not by applying the entire stash here. Older committed probe tests removed from the active suite remain accessible in `e4242c1c`; they are historical diagnostics, not evidence that the accepted configuration supports every experimental feature. These dirty-work archives are local and are not included in the public branch push.
