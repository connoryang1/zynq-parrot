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
