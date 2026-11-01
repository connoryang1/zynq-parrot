This directory records the protocol and accepted FPGA result for steady-state mode-6 instruction replay with one persistent Linux task pair. It keeps that production-like retained-buffer question separate from the per-trial `fence.i` experiment, which measures a deliberately cold first-switch mechanism ceiling. The current table produces a resolved 1.76% pooled median improvement in this best-case workload.

# Mode-6 persistent-pair protocol

## Why this experiment is distinct

The historical old-16 result in RL-063 is a valid separate-boot A/B and improves the persistent-pair median by 637.5 cycles, or 3.25%. The current exact mode-6 NBF instead contains a newly trained 16-line post-wakeup table beginning at `0x80a13840`; it is not the old-16 table beginning at `0x8023d480`. The current table therefore needs its own steady-state measurement rather than inheriting the historical percentage.

The isolated physical benchmark clears completed replay lines with a symmetric `fence.i` before every trial. That is the correct arm-isolation mechanism for a cold trigger test, but it deliberately removes the hardware's persistent 16-line-buffer behavior. This protocol uses a fresh boot for every arm, discards the first handoff as warmup, and retains the next 200 handoffs from one pinned futex pair.

## Matched control

Both threads register the same harmless shared user page because the current kernel requires physical-preview registration before any nonzero preview mode. Modes five and six never issue that registered data address. Both arms use the same exact NBF and benchmark ELF; the only runtime difference is mode zero (`disabled`) versus mode six (`wake-trigger`) on both tasks.

The benchmark records the source-to-peer window with summary-only miss counts. Recorder overflow is explicitly permitted because the elapsed endpoint remains valid; invalid recorder state remains fatal. A final `TRACE_CAPTURE_PASS` marker replaces the historical `|| true` shell escape.

## Exact prepared artifacts

- Routed bitstream SHA-256: `e97e0517d08771753e2eae96c6af95380944e5a8e2aefa0115da898b7be12381`
- Current mode-6 prefix-16 NBF SHA-256: `5e42c2f6c801d71506a3c6fc5e708aa01c0e6a46996fc72bc64236135565d2bd`
- Control-program SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- Prepared benchmark ELF SHA-256: `91f0db111470e9f3fd1a53bfd9b8d7b4404ffe8e20a792e4caa99171bbc1c0cf`
- Prepared transfer SHA-256: `b5103c89b270f5cdcee8156de0a0a6d8b98ca32ecbba7de77e5cc11a6f0f5518`
- Compiler: `/home/jhumphri/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-gcc`

The ELF disassembly contains `configure_preview` calls in both `main` and `peer_main`, and the main-thread release follows `pthread_join`. The generated guest command for an enabled arm is:

```text
/tmp/cache_miss_trace_capture_dynamic --window to-peer --samples 201 --preview-mode wake-trigger --summary-only --allow-overflow --final-addresses
```

The disabled arm changes only `wake-trigger` to `disabled`.

The first local rebuild used the Makefile's unavailable default `riscv64-unknown-linux-gnu-gcc` name and stopped before producing a result. The confirmed cause was a missing `PATH` entry, not a source failure; all accepted rebuild commands pass the explicit Buildroot compiler path shown above. Future reproductions must keep that explicit toolchain argument.

## Acceptance design

Run two fresh-boot pairs in opposite order:

1. enabled, then disabled;
2. disabled, then enabled.

Every run must have exact hash matches, 201 consecutively numbered samples, explicit preview-mode and final capture markers, runner exit zero, and CORE/BSG PASS. Only after the final timed endpoint, the benchmark reads the frozen miss recorder and prints its addresses; this cannot perturb an analyzed successor and distinguishes table mismatch from trigger-timing failure without another boot. `linux-tests/analyze_persistent_preview_ab.py` verifies the adjacent runner status and exact prefix JSON, reports configured lines demanded in that final capture, discards exactly sample one, reports per-replicate and pooled medians, and calculates both IID and circular ten-handoff block intervals for the mean of the two replicate-level median differences.

## Validation before launch

The benchmark and serialized runner changes pass all 93 discovered `linux-tests` Python tests, including compressed-log analysis with an adjacent uncompressed-name status file. The RISC-V dynamic ELF and transfer rebuild to the hashes above. At protocol preparation the board was still on the prior guest-shutdown boot; later runs recovered it through the documented local outlet fallback, waited for PYNQ readiness, and reloaded the exact overlay before every arm.

## Accepted persistent-pair result

Two opposite-order pairs used four independent fresh boots. Every arm has exact NBF/ELF/transfer/control hashes, 201 numbered samples, the expected runtime mode, final-address and capture markers, runner RC zero, and CORE/BSG PASS. Sample one is discarded as warmup, leaving 200 samples per run and 400 per arm.

The enabled-then-disabled pair measures 18,925 versus 19,033 median cycles, a 108-cycle or 0.57% reduction. The reverse-order pair measures 19,058.5 versus 19,415 cycles, a 356.5-cycle or 1.84% reduction. Pooled arm medians are 18,955 enabled and 19,295.5 disabled, a **340.5-cycle or 1.76% reduction**.

The replicate-level estimand is the mean of the two enabled-minus-disabled median differences: −232.25 cycles. Its 100,000-sample IID interval is `[-851,-58]`, favoring enabled in 99.27% of resamples. The circular ten-handoff block interval is `[-525.5,-85]`, favoring enabled in 99.69%. Both boot orders and both dependence models therefore support a persistent best-case gain.

Mechanism attribution also passes. Median I-request counts are 188 enabled versus 199 disabled when pooled. The final complete disabled traces demand 9 and 11 configured lines, with nine common to both; neither enabled trace demands any configured line. Five pipe-trained entries are absent from both disabled futex traces: `0x802469c0`, `0x80246ac0`, `0x80246b00`, `0x80246b40`, and `0x80254600`. This explains why the current result is smaller than RL-063's old-table 3.25% result and exposes a bounded futex-specific tuning opportunity.

This remains a best case for one pinned persistent task pair, not general Linux or application throughput. It shows that retaining and reusing lines works; it does not rescue the rejected policy of invalidating and refetching all 16 on every switch.

Retained artifact hashes are:

```text
rep1 enabled gzip/status:  30d010d3345357ef7de65659fca060c05ef330e09bde4108ee6ce8c6712bafd7 / 0ee579af5b506b9127bb851d77fc277e37f4cdf338c0c4f56743d65c26414636
rep1 disabled gzip/status: f2d99c2d05515ff108564a8597793713f1edaf12cfe0ed91b57dff5cbb237f0e / 673e09cd39a9e5c303054cd14a346330c7ed68f24535d1eac9169a60c4ba08d9
rep2 disabled gzip/status: b39a8b885739f7caace18389367ee4f9d9bdfe9a7cb2d809de1d65f345288310 / 673e09cd39a9e5c303054cd14a346330c7ed68f24535d1eac9169a60c4ba08d9
rep2 enabled gzip/status:  abc97ed020334ea4aab1ae27cf82899d898cc2bb5612799c4bb1ad2998371391 / 0ee579af5b506b9127bb851d77fc277e37f4cdf338c0c4f56743d65c26414636
analysis:                   d5a80284cf392a4461fd6dc2d02caad52d58ab0648a3473d18b5fdce0681d049
```

## Same-capacity futex-specific table

The bounded follow-up kept the 16-entry capacity, mode-6 wake trigger, routed
RTL, Linux payload, benchmark, and control program unchanged. It retained all
11 current-table entries demanded by either replay-disabled futex trace and
replaced only the five entries absent from both traces with common early
trap/futex lines. The exact policy is in `futex-prefix16-candidate.json` and the
generated header is in `futex-prefix16-header.h`.

The candidate NBF is SHA-256 `93b2e29d...8629`. Its strict splice uses 17,024
candidate OpenSBI records below `0x80200000` and preserves all 1,861,857
Linux/DTB records byte-for-byte from accepted mode-6 NBF `5e42c2f6...5d2bd`.
The firmware forbidden-CSR scan passes, the timer patch reports one exact DTB
write, and all six focused splice/timer tests pass. The complete Linux test
suite passes all 96 discovered tests.

Four independent fresh boots form opposite-order current/candidate pairs.
Every accepted arm has the exact NBF, transfer, ELF, control-program, and
bitstream hashes; 201 consecutively numbered samples; wake-trigger mode on
both tasks; final capture; runner exit zero; and CORE/BSG PASS. Sample one is
discarded, leaving 400 samples per table. The first current-table boot stalled
at Linux guest time 1.591 seconds before a shell and is rejected; a complete
power-cycle/readiness/overlay recovery preceded its unchanged accepted retry.

The current-then-candidate pair measures 18,735 versus 18,727.5 cycles, a
7.5-cycle candidate improvement. The reverse pair measures 18,997 versus
18,397.5 cycles, a 599.5-cycle improvement. Pooled medians are 18,908.5
current and 18,600 candidate, a **308.5-cycle or 1.63% reduction**. The
replicate-stratified candidate-minus-current estimate is -303.5 cycles; its
100,000-sample IID interval is `[-577.75,-53.75]`, and its circular ten-handoff
block interval is `[-554.75,-71.75]`. Both resolve below zero, so the candidate
passes the predeclared replacement gate. Pooled median I requests fall from
188 to 183; neither enabled table's configured lines appear as demand in its
final capture.

Several failed preparation attempts changed no accepted artifact. The first
source tree came from the similarly named `/home/jhumphri` SDK and the strict
splicer rejected a noncontiguous donor. Copying the exact `/home/coyang` source
but compiling it with the other GCC still produced a larger, differently
aligned `.text`; using the Buildroot-wrapped compiler recorded by the accepted
ELF restored `.text` size `0x15368` and the valid 17,024-record partition. One
missing compiler path, one repository-root Python import-path invocation, and
one diagnostic Python 3.8 f-string failed before acceptance. Remote staging
also filled the board filesystem; only the failed partial upload and an old
debug NBF with two local copies were removed. A wrong local transfer path was
rejected before board launch.

The retained strict analysis is `futex-candidate-table-ab-results.json`; the
deterministic gzip transcripts and adjacent statuses are under
`futex-candidate-physical/`. This comparison establishes a better table, not
its total speedup versus replay disabled. A fresh opposite-order candidate
enabled/disabled comparison is the next measurement.

## Direct candidate enabled/disabled result

The exact candidate NBF was then held constant while runtime mode six and mode
zero were compared in four more independent fresh boots. The first pair ran
enabled then disabled; the second reversed that order. All four arms pass the
same 201-sample identity, marker, status, and terminal gates. The strict
analyzer now also requires the exact transfer SHA-256, and the full 96-test
Linux suite passes after that guardrail was added.

Pair medians are 18,664.5 enabled versus 18,958.5 disabled, a 294-cycle or
1.55% reduction, and 18,467.5 enabled versus 19,146 disabled, a 678.5-cycle or
3.54% reduction. Pooled medians are 18,534.5 enabled and 19,044 disabled, a
**509.5-cycle or 2.68% reduction**. The mean replicate enabled-minus-disabled
median difference is -486.25 cycles. Its 100,000-sample IID interval is
`[-741.5,-253]`, with 99.963% of resamples favoring replay; its circular
ten-handoff block interval is `[-686,-281.75]`, with every resample favoring
replay.

Pooled median I requests fall from 198 disabled to 183 enabled. Both disabled
final traces demand the same 14 candidate lines; neither enabled trace demands
any candidate line. The two candidate slots absent from both disabled traces
are `0x8023f780` and `0x802034c0`, leaving one more bounded same-capacity tuning
question before fixed-table iteration is exhausted.

The retained analysis is `futex-total-ab-results.json`; deterministic logs and
statuses are under `futex-total-physical/`. This is the direct performance
number for the current best candidate on the synthetic persistent futex pair.
It remains neither a general Linux context-switch claim nor application
throughput evidence.

## Final manual table iteration

The two v1 entries absent from both RL-090 disabled traces were replaced by
common early lines `0x80a12500` (`irqentry_nmi_exit`) and `0x802980c0`
(`__riscv_sys_futex`). The earlier common `0x80203280` line was deliberately
excluded because it lies in freed-init or alias-prone space. V2 retains 14 of
16 v1 entries, keeps capacity and trigger timing unchanged, and reduces rather
than increases duplicate cache-set occupancy.

V2 NBF `0068529a...a817` passes the same 17,024-record OpenSBI splice,
1,861,857-record exact Linux/DTB payload check, CSR scan, and six focused
packaging tests. Four fresh boots form opposite-order v1/v2 pairs with exact
identities and complete terminal gates. The first pair favors v2 by 115.5
cycles: 18,635 versus 18,750.5. The reverse pair regresses by 286.5 cycles:
18,784 versus 18,497.5. Pooled v2 is 73 cycles slower at 18,683.5 versus
18,610.5, a 0.39% regression.

The mean replicate v2-minus-v1 median difference is +85.5 cycles. Its IID
interval is `[-136.5,355.25]`, with only 21.862% of resamples favoring v2; its
circular ten-handoff block interval is `[-125.75,328]`, with 21.505% favoring
v2. The result fails the predeclared replacement gate. V1 remains accepted,
and manual fixed-table membership tuning is closed: covering two more stable
demand lines did not improve latency.

One prelaunch post-power-cycle check found that the remotely staged v2 NBF had
changed hash without a local change. No control process was launched. The
known-bad remote file and failed partial upload were deleted, the exact local
image was atomically restaged and checked twice, and only then did the v2 arm
run. The older remote current-table image removed for staging remains
recoverable from exact local and committed evidence.

V2 policy, header, build summaries, deterministic logs/statuses, and strict
analysis are retained beside v1 evidence as `futex-prefix16-v2-*`,
`futex-v2-physical/`, and `futex-v2-table-ab-results.json`.

## Prefix-14 shrink candidate

The next bounded candidate removes v1 entries `0x8023f780` and `0x802034c0`,
which were absent from both disabled futex traces, and compacts the 14 retained
entries without adding v2's replacement traffic. This exact membership is in
`futex-prefix14-shrink-candidate.json` and its generated source form is
`futex-prefix14-shrink-header.h`. It is prepared but not built or measured; it
has no performance or stability claim. Its gate is a strict opposite-order
enabled/disabled comparison, with any terminal fault rejecting the candidate.
The generator reproduced the retained header byte-for-byte. Candidate JSON and
header SHA-256 values are `03a7ea38...e5b8e` and `af97662f...5b0d`.
