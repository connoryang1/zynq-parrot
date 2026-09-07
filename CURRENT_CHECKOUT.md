This file is the entry point for the supported BlackParrot FPGA checkout. It records what has been validated, where to run tests, and how to recover the older experiments without confusing them with the current implementation.

# Supported checkout

Use `/home/coyang/zynq-parrot` and its `import/black-parrot` submodule.
Both fork repositories integrate on `master`; start new work on dedicated branches.
The top-level gitlink selects RTL `6c97bcc0a`. It adds a narrowly
scoped source-register writeback wait to parent `1b9e611d4`, whose hardware and
dependency content is identical to FPGA-accepted
`25089713baa090aba719ec0f18f82ff9214d5f0d`. The new fix passes the identical local
regression ELF that fails on its parent. On the FPGA, the same regression NBF
fails on the old accepted bitstream and passes on the new one; Linux and the
physical performance gates also pass. The identities below select the new fix.

The initial reviewable history has twelve top-level commits separating integration,
correctness tests, translated handoffs, benchmarks, waveform tools, Vivado builds,
board operation, the Linux demo, image diagnostics, synthesis-farm orchestration,
workflow guidance, and project documentation. Seven RTL commits separate
dependencies/loading, streamed-write credit accounting, MPRV data privilege,
storage primitives, coupled pipeline integration, the global counter, and docs.
The pipeline integration remains the largest commit because its FE/BE/CSR
interfaces must change together; known fixes stay with the features they repair.
These organize the accepted endpoint, not seven separate FPGA/Linux acceptances.
Separate upstream changes from the old fork master were not merged into this
accepted source.

## Stable-branch policy

`master` contains the accepted implementation, focused regressions, and reusable
operational tools. Exploratory application benchmarks remain on experiment
branches; SQLite is retained at `archive/sqlite-progress-screen-20260907`, not in
the maintained suite. Neither cleanup nor a passing smoke test makes this a
general production threading facility.

The supported scope is cooperative integer-context execution on the fixed
PYNQ-Z2 topology below. Production use would additionally need an explicit safe
ABI/FP policy, isolation and privilege enforcement where contexts are untrusted,
OS lifecycle/preemption integration, and broader fault/stress qualification.
Do not infer those guarantees from the Linux demonstration.

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
The maintained suite has 14 tests; its README explains the invariant each covers.
Core-wide CSR `0xCC0` measures elapsed cycles across context switches; do not
substitute a context-restored `mcycle`.

Stable integration verification is retained in `logs/stable-master-20260907/`:
all 14 programs compile for the default 2/4 topology; a clean traced model passes
the register-target regression, resident smoke, translated nonresident data
handoff, and the unchanged 5.13/11.13-cycle ring benchmark. Ten isolated harness
test groups also pass, covering failed builds/stale logs, safe defaults, and
configuration-stamp transitions. These are new local checks, not a new FPGA run;
the FPGA identities below still refer to the exact previously accepted RTL.

The register-target fix has a clean traced two-bank/four-context model and seven
runtime passes: its new 46-case regression, resident smoke, register isolation,
late writeback, translated nonresident data handoff, logical CSR readback, and
the overhead benchmark. On the earlier fix branch, all 19 test programs compile; the byte-identical ring
ELF still reports 5.13/11.13 cycles per resident/nonresident switch. Evidence is
in `logs/register-target-fix-20260906/`. The routed build of top `8ecb909a` / RTL
`6c97bcc0a` passes timing and fit. Its FPGA passes the register-target regression,
translated handoff, Linux PID-1 context-switch demo, unchanged overhead benchmark,
and the original scan workload without its immediate-target workaround.
Board evidence is in `logs/register-target-fpga-20260907/board-fixed/`;
the old-bitstream failure is in the adjacent `board-baseline/` directory.

The prior clean simulator baseline is 5.13 resident and 11.13 nonresident
cycles/switch, with two matching runs in `logs/docs-integration-20260906/`.
Final suite/history validation is retained in `logs/reviewable-integration-20260906/`.
All 13 tests compile; the clean traced handoff and resident smoke pass, and both
benchmark repeats match the prior 5.13/11.13-cycle result.
Guest success must precede the known GPIO `fini()` teardown assertion; these are
not claims of warning-free simulator shutdown.

The finer history split is checked in `logs/refined-history-20260906/`: isolated
storage/CSR/UCE modules and complete cores before pipeline integration and before
the global counter pass Verilator lint/elaboration. These intermediate checks
establish elaboration, not runtime correctness or Linux boot acceptance.
The top-level stages also pass test-source/helper prerequisite checks, shell
syntax checks, and Python compilation; the harness introduces 9, then 12, then
13 tests as their sources become available.
Fresh endpoint evidence is in `logs/commit-split-validation-20260906/`: clean
model build, all 13 programs compiled, resident smoke and translated data handoff
passed, and both benchmark repeats still report 5.13/11.13 cycles per switch.
No new FPGA run is claimed for this history-only rewrite.

## FPGA acceptance identities

The register-target acceptance route uses top
`8ecb909ae316f6c0daaafe455b6ac61f5212c168` and RTL `6c97bcc0a`, with Vivado
2024.2 and static `e_bp_unicore_zynqparrot_cfg`: 47,042 LUTs, 21,446 registers,
80 BRAM tiles, 11 DSPs, WNS +2.969 ns, TNS 0, WHS +0.023 ns, and THS 0.
Physical benchmark spacing remains 5.10 resident / 11.12 nonresident cycles
per switch, distinct from waveform handoff latency and cold-cache tails.
The parent route used 46,851 LUTs with the same BRAM/DSP counts and WNS +1.781 ns;
the extra 191 LUTs fit, and no frequency increase is claimed from the timing margin.

| Artifact | SHA-256 |
| --- | --- |
| Packed FPGA image | `81dc436aa6b68b278b5841a9cf3128b34e63deae9837ae354e18c075e32eefa9` |
| Extracted bitstream | `7dd91dac345937daa96442411c57c9023d66e5563fdb8532083369910b0db9d5` |
| Register-target regression | `0b37b9007f5e73e728f34303d183398cc3da0030a5091c733a91e1ecf5628b9b` |
| Linux PID-1 image | `0728cd34650d49c4fe38522d6e139befb51732b426be1b1d1eec11d3ced36959` |
| Translated bare-metal handoff | `6cbee152430e0aa5ec471664cf8e1874487d166a459fcce69c38c8082e69bb01` |
| FPGA global-cycle benchmark | `da85ec1f46c8217241adacb0b8c801bef65968db2c6f25d09bfca8fd337152f2` |
| Original register-target scan | `af4b7aaeb45e84d4091764612659efcbbb747d27330ff489222d9826cb92694e` |

The package and retained route reports are under
`logs/fpga/20260907T021217Z-8ecb909a/`. Fresh bare-metal inputs, CRT/build recipes,
disassembly, hash manifests, and the serialized board ladder are under
`logs/register-target-fpga-20260907/`; the unchanged Linux image remains
`linux-tests/out/linux-ctxtsw-tiny-init.nbf`. The runner hash is
`be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e`.
All five runs reload the verified overlay and require their guest marker plus
`CORE[0] PASS`; a zero host exit alone is insufficient. No power cycle was needed.

Parent acceptance evidence remains in
`logs/pynq-validation/translated-handoff-recovery-20260906/` and its package in
`logs/fpga-farm/bp3/20260906T032705Z-032420c3/`. Fresh benchmark and translated
handoff NBFs are byte-identical to that baseline; the Linux NBF is also unchanged.

## History and recovery

Original commits and authorship are retained at published tags:
`archive/pre-review-series-20260906` preserves the full pre-split snapshot in
each fork; `archive/docs-before-cleanup-20260906` preserves the older plans
and investigation diaries. `archive/pre-logical-split-20260906` preserves the
subsequent five/three-commit review series before the finer logical split.
For example:

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
