This file identifies the accepted BlackParrot context-switch and prefetch sources and their verified FPGA image. It records reproducible checks, remaining production limits, and historical artifact identities.

# Supported checkout

Use `/home/coyang/zynq-parrot` and its `import/black-parrot` submodule.
Both forks integrate on `master`; develop on dedicated branches. The accepted
RTL is `f7eedd955`, routed from top `fd5a7872` with static
`e_bp_unicore_zynqparrot_prefetch_cfg`. Its exact image passes six bare-metal
gates and shell-launched Linux resident/nonresident switching, register and
syscall checks, process exit, a subsequent shell command, and clean poweroff.

This adds nonfaulting prefetch hints and independent L2-bank responses to the
previously accepted resident initialization and refill/replay ownership fixes.
The current image and historical resident baseline are identified below.

Development branch `fix/linux-request-lifecycle` pins RTL `f6e004283`. It orders
NPC seeds before handoffs, serializes remote-register seeds to prevent lost
ordinary writebacks, and updates the interrupted PC when reseeding an initialized
inactive resident context. The same pending-interrupt binary fails on `d18f16849`
with the old parked PC and passes with this correction, preserving private state.
Six final traced full-system gates pass; the earlier two ordering fixes also pass
nine gates. All three raw prefetch benchmark samples remain unchanged.
This candidate has completed routed implementation and all nine physical FPGA
gates. The unchanged Linux request executable now passes its original one-request
case and the seven-sample, two-worker comparison, including all four modes,
checksums, exit zero, a usable shell, and clean poweroff. The combined corrections
resolve the observed hang; the directed tests do not isolate which correction
was necessary in Linux. The previous shell resident/nonresident compatibility
gate remains to be rerun before integrating this candidate into `master`.

Candidate route `20260909T015657Z-dc6d0e89` uses 51,518/53,200 LUTs (96.84%),
22,671 registers, 81 BRAM tiles, and 11 DSPs. WNS is +1.619 ns, TNS 0, WHS
+0.024 ns, and THS 0; all 79,534 routable nets are routed, with zero routing
or bitstream DRC errors. The inherited 42 no-clock pins and 50 unconstrained
internal endpoints remain; this is not complete timing-constraint coverage.
The verified bitstream SHA-256 is
`b82832901d6a4e45e2e245be3f669aa2b32d3e7db6b8eaa257394b0f1cd35673`.
Evidence is retained under `logs/linux-request-lifecycle-20260908/` in `route/`,
`board-qualified/`, `linux-one-request/`, `linux-matched2/`, and
`linux-reference10/`; see the
[Linux guide](linux-tests/README.md#independent-random-request-comparisons)
for the application measurements and their limits.

## Scope and readiness

The maintained configuration is PYNQ-Z2 with two resident register banks and
four logical integer contexts sharing one pipeline. Accepted FPGA evidence
covers nonresident translated U-mode 0→2→0 handoff, a target-context syscall,
logical identity, register restoration, and Linux shutdown. A separately
transferred shell executable also passed on `6c97bcc0a`. The current image
retains verified resident 0↔1 initialization, repeated handoffs/reseeding, and syscalls;
see the
[Linux guide](linux-tests/README.md) for that evidence and its one-run-per-boot
restriction.

This is a cooperative integer-context prototype. Production readiness still
requires:

- A defined ABI and complete FP-state policy; ordinary FP and resident FP tests
  do not establish nonresident FP preservation.
- Context allocation, teardown, and reuse across Linux process exit, traps,
  timer preemption, and scheduling. Hardware contexts currently are not
  independently scheduled Linux tasks.
- Permission enforcement and address-space isolation for untrusted contexts.
- Broader fault/stress qualification, including NPC reseeding from a context
  with different privilege/SATP/ASID. Static review found that `bp_be_top.sv`
  updates target fetch metadata from the caller on reseed while retaining the
  initialized target CSR image; a differing-environment regression is needed
  before changing that protocol or claiming it safe.

See [architecture](CONTEXT_SWITCH_ARCHITECTURE.md), [tests](testing/README.md),
and [research direction](PAPER_DIRECTION.md). Application experiments belong on
experiment branches; SQLite remains at
`archive/sqlite-progress-screen-20260907`.

## Accepted prefetch implementation

The implementation adds nonfaulting L2 hints with two UCE request slots
and an equal-capacity two-bank L2 (top `fd5a7872`, RTL `f7eedd955`). The response
controller permits a ready bank to reply past a pending hint while preserving
ordinary order. The full simulator passes hint correctness, resident switching,
U-mode Sv39 permissions, and the independent-request benchmark. Traces now
prove two concurrent cold-data requests in both batch2 and the resident worker
schedule. Median resident time is 3867 cycles versus 5079 for its matched
control in three controlled simulator samples; see
[the experiment](PAPER_DIRECTION.md#removing-the-l2-response-bottleneck).

This checkpoint has passed routed fit and the selected FPGA/Linux gates.
PYNQ-Z2 job `20260908T221834Z-4425a9d3` was canceled after Vivado exposed an
undriven implicit bank-select net caused by declaration order. A declaration
move passed targeted old/fixed Vivado synthesis and the clean simulator gates.
Replacement job `20260908T223358Z-fd5a7872` completed successfully on bp2 with
top `fd5a78727a4c85b5ffb66e063995778aaf6a6d0e`, RTL
`f7eedd9556215b91c288b77de077c67d137e998a`, static
`e_bp_unicore_zynqparrot_prefetch_cfg`, and Vivado 2024.2. It uses 51,334/53,200
LUTs (96.49%), 22,659 registers, 81 BRAM tiles, and 11 DSPs. Routed WNS is
+2.905 ns, TNS 0, WHS +0.020 ns, and THS 0; final routing and bitstream DRC
report zero errors. The high-utilization advisory leaves 1,866 LUTs of headroom.
The implicit bank-net warnings are gone; the remaining warnings were reviewed
against the earlier accepted baseline.

| Routed prefetch artifact | SHA-256 |
| --- | --- |
| Packed FPGA image | `1a1b4dfffa54ee015d2ecff295cf208810fa806feb6db9da13304362575afee1` |
| Extracted bitstream | `c365bbc08e7e653c874a8bcef62c91418b2016434ae25ffa267dcc9d6c835617` |

Route records and package verification are retained in the canonical checkout
under `logs/nonblocking-prefetch-20260908/route/` and
`logs/nonblocking-prefetch-20260908/package-verification.txt`. The board loaded
this exact image. An initial detached runner was lost without a target
transcript and provided no validation result; recovery preceded a foreground
smoke run that passed.

**Board qualification:** all six bare-metal gates pass: resident smoke, hints,
U-mode Sv39 hints, the matched worker benchmark, computed targets, and
translated nonresident data handoff. Three measured board samples give median
2398 resident-prefetch cycles versus 3164 matched-control cycles (24.2% fewer).
This is a 64-load bare-metal workload; that checkpoint did not qualify the
Linux request-pool comparison. The later lifecycle candidate's Linux results
are linked above.

The unchanged Linux shell NBF and benchmark ELF identified below also pass on
this exact prefetch image. Guest ELF SHA, both resident/nonresident correctness
markers, `BENCH_EXIT=0`, `uname -m=riscv64`, clean `CORE[0] PASS` poweroff, and
runner exit zero are retained in `logs/nonblocking-prefetch-20260908/linux-shell/`.
The seven 256-switch samples match the previous image exactly: resident
`1311 1307 1307 1307 1307 1307 1307`, nonresident
`2857 2853 2853 2853 2853 2853 2853`. Median spacing remains 5.10546875 and
11.14453125 cycles/switch. That run ended with the guest powered off.

The Linux request benchmark at commit `a6b2349d` on `feat/nonblocking-prefetch`
was excluded from that integration because its second resident launch hung.
The shell regression did not qualify that application's argument-reseeding
lifecycle; the current candidate's successful rerun is recorded above.
Reproduce the new gates using [the testing guide](testing/README.md#full-simulator-and-waveform-evidence).

## Verification

Preserve existing logs/waveforms, finish each clean command, then build/run:

```sh
make -C testing clean
make -C cosim/black-parrot-minimal-example/verilator clean
make -C testing run-mt_umode_nonresident_sv39_data_handoff_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

Use the available CPU/memory budget for inner build jobs, but serialize guests.
The maintained suite has 24 programs; its README explains each invariant.
Core-wide CSR `0xCC0` measures elapsed cycles across context switches; do not
substitute a context-restored `mcycle`. The runner must see the selected test's
completion marker before `CORE PASS`, plus host `BSG PASS`. The known post-PASS
GPIO `fini()` assertion remains a separately checked teardown exception.

Cleanup verification on September 8 is retained in
`logs/readiness-cleanup-20260908/`: all 15 maintained programs compile and pass
on one clean traced 2/4 model, and 21 host checks pass (13 bare-metal harness,
5 Linux build/transfer, 3 waveform-decoding checks). Disabled-switch variants of
both rings and the benchmark are rejected. An injected late illegal instruction
reproduces the legacy handoff test's false PASS and is rejected by the fixed
verdict with `mcause=2`. Logs, closed FSTs, source snapshots, and hashes are
retained; the known post-PASS GPIO teardown assertion remains.

The hardened benchmark reports 5.12 resident / 11.32 nonresident cycles per
switch and a separately truncated nonresident-minus-resident increment of 6.19.
Its timed loop instructions and counter boundaries are unchanged, but untimed
completion checks change code placement and counter destination registers.
These are new-ELF measurements, not evidence of a hardware performance change.
Rebuilding the original benchmark from `873deeb7` on the same model reproduces
5.13 / 11.13 cycles per switch, increment 6.00; its separate artifacts are in
`logs/readiness-cleanup-20260908/benchmark-original/`. No specific cache-related
cause is established for the new binary's different result.
All four Linux applications compile; the default tiny, shell, and benchmark
ELFs are byte-identical across the build-freshness fix. No new FPGA/Linux
acceptance is claimed by this cleanup.

Historical resident-fix evidence is in `logs/resident-csr-init-20260907/`:
the translated resident regression fails on the old RTL and passes after both
fixes; CSR inheritance/reseed, resident smoke, translated nonresident data
handoff, FP isolation, computed targets, and the ring benchmark pass locally.
The unchanged simulator benchmark reports 5.13 resident / 11.13 nonresident
cycles per switch. The September 7 work-log entry records the routed candidate
`20260907T225642Z-873deeb7`: 47,640 LUTs, 80 BRAM tiles, WNS +1.973 ns and TNS 0;
this exact candidate passed the September 8 Linux shell acceptance below.

Baseline acceptance evidence remains in
`logs/register-target-fpga-20260907/board-fixed/`, with its old-bitstream
regression failure in adjacent `board-baseline/`. The identical computed-target
regression fails on parent RTL `1b9e611d4` and passes on `6c97bcc0a` in simulation
and on FPGA. Stable integration checks are in `logs/stable-master-20260907/`.
Earlier history-split verification is retained in the dated artifact directories
and Git history, rather than repeated here as current suite counts.

## FPGA acceptance identities

Current prefetch identities and acceptance are recorded above. The following
records preserve the earlier images and their original measurement scope.

The historical accepted resident RTL also passes the September 8 software load-ahead
correctness test and four-schedule microbenchmark on FPGA. Their clean traced
simulator runs and the resident smoke pass; the new analyzer has 19 passing host
controls. The helper's final refactor produces byte-identical simulator and
FPGA ELFs to those exercised. Full-refill overlap, critical-beat limits, exact
raw cycle totals, and the single-series measurement scope are recorded in
[research direction](PAPER_DIRECTION.md) and `logs/resident-cache-overlap-20260908/`.
This adds a faulting software load-ahead helper, not a new ISA hint or multiple
outstanding misses. Existing simulator GPIO teardown behavior is unchanged.

The historical resident-fix route is job `20260907T225642Z-873deeb7`, top
`873deeb7c9aa6ec7165ee29d71d229699340d5e9` / RTL
`aad56bd922c5246ad90d6f4d58d90e56c85bd121`, Vivado 2024.2 and static
`e_bp_unicore_zynqparrot_cfg`: 47,640 LUTs, 21,446 registers, 80 BRAM tiles,
11 DSPs, WNS +1.973 ns, TNS 0, WHS +0.007 ns, THS 0.

| Historical resident acceptance artifact | SHA-256 |
| --- | --- |
| Packed FPGA image | `aa73d6e28c67c3fbba20552ce948fce13561a0adeb3f5ce1817cab3cbc16a461` |
| Extracted bitstream | `10b8c179c35d1938da1103b33f4f1ba7842ffbef4f54a557846f93b429da886a` |
| Linux shell NBF | `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3` |
| Shell benchmark ELF | `d3351f9de2c3567cd40c31453b8101781195fbb0bf797a10253323c25b2146f9` |

Evidence is in `logs/linux-resident-shell-20260908/`: package/revision/route
records, exact source/ELF/disassembly, transfer integrity checks, readiness and
overlay-load logs, the reproducible `run_shell_acceptance.py`, and closed local
and board-retained transcripts. The board was power-cycled with authorization,
passed the PYNQ startup/90-second gate, and loaded the verified bitstream.
The reviewed runner SHA remains
`be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e`.

The first resident warm-up checks initialization; all 14 resident and 14
nonresident trials check target identity, independent/restored `s11`, completion,
and matching target `getpid`. Seven measured 256-switch samples were
`1311 1307 1307 1307 1307 1307 1307` resident and
`2857 2853 2853 2853 2853 2853 2853` nonresident. Medians are 5.10546875 and
11.14453125 cycles/switch, difference 6.0390625. These are loop-inclusive Linux
measurements with interrupts enabled, not isolated redirect latency or scheduler
speedups. Guest ELF SHA, both PASS markers, `BENCH_EXIT=0`, `uname -m=riscv64`,
`CORE[0] PASS`, and host exit zero all passed. That acceptance run ended with
Linux powered off and no runner remaining. Context lifecycle
limits still require one demonstration process per fresh overlay/Linux boot.

### Earlier register-target acceptance

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

This cleanup moved 46 retired or superseded `.riscv`/`.mem`/`.nbf` experiment artifacts out of
`riscv/bp-tests` into
`logs/readiness-cleanup-20260908/retired-test-artifacts/`. Its `manifest.json`
records original paths and verified SHA-256 values; freshly rebuilt simulator tests remain active. Older FPGA variants of the
hardened handoff tests and benchmark were also archived so they cannot be
mistaken for the new checks; accepted board evidence remains at the paths above. The older FPGA guide is recoverable with
`git show archive/pynq-recipes-before-cleanup-20260908:codex-skills/bp-fpga-synthesis/references/pynqz2-flow.md`.
That tag and the artifact archive are local; no publication is implied.


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
