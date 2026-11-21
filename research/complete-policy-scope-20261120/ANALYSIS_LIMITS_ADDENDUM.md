This addendum fixes interpretation and descriptive reporting requirements for the registered scoped mode-14 experiment. It was recorded at 2026-11-21T00:51:10Z, during the A1 wave and before any B-image collection or image contrast, without reading primary effects. It does not change the fixed acquisition plan, primary estimator, workload set, timing endpoints, fences, acceptance gates or stopping rules.

# Analysis limits and absolute-cost crosschecks

The primary remains the preregistered **B-minus-A difference in paired off-on WHOLE benefit per cell**, calculated separately for each workload using the existing hierarchical bootstrap. The four-workload ABBA collection and forward/forward/reverse/reverse workload order remain unchanged. The new requirements below are descriptive and decision crosschecks, not replacement primary outcomes, alternative collection rules or permission to select favorable subsets.

## Repeated crossover interpretation

Scope-v1 mode-zero cleanup prevents additional task-mode-14 triggers during reporting and the next cell's initial setup. It does not invalidate completed retained instruction lines. Those lines may carry into reporting and the next initial mmap/pipe/fork/allocation before that cell's existing fence.i. Therefore the primary contrast describes the registered repeated crossover schedule with possible retained-line carryover; it is not an isolated cold-cell effect or a pure prefetch-versus-retained-capacity effect.

The bounded drain checks only reported prefix-controller bits 1/2/3/54. It does not prove that all UCE responses or memory-system requests have completed. No added fence, delay, cache flush, timing knob or new trial is authorized to remove either limitation in this fixed experiment.

## Required absolute reporting

For **every complete admitted boot**, report the following alongside its paired WHOLE benefits and uncertainty for the unchanged primary contrast:

- All eight absolute WHOLE cell costs, retaining repeat, order and enabled state in acquisition order.
- The four absolute enabled costs and four absolute disabled costs, with each arm's median and sum. Preserve individual values rather than reporting only their difference.
- The sum of all eight WHOLE cell costs and the identity `eight_cell_sum = enabled_sum + disabled_sum`.
- Enabled order by repeat and the already required resource diagnostics, so drift and carryover can be assessed without selecting cells.

Retain these reports separately for each boot, image and workload; do not pool different workload costs. Each WHOLE value includes that cell's declared setup/warmup/work/check/teardown/reset/controller-observer scope. The eight-cell sum is the sum of those measured intervals: it excludes startup and inter-cell printed output, and must not be relabeled full process wall time.

Any later helper may derive these values from the existing complete-cell pair/row records and may add clearly labeled secondary bootstrap summaries of absolute enabled costs using the same boot and paired-block strata. It must retain the original primary calculation, all boot values, acquisition order and hash-bound admitted inputs. Resampling or reporting must not replace difficult boots, choose a favorable order, alter collection, or introduce result-dependent stopping.

## Decision crosschecks

A positive paired-benefit contrast alone does not establish a kernel optimization. It can arise because nominal disabled costs increased, even when the absolute enabled execution became slower. Do not make a kernel-optimization claim from that contrast if the absolute enabled costs regress, or if the boot/order evidence leaves carryover or drift unresolved. Report the discrepancy and preserve the candidate as unresolved or adverse under the stated scope; do not replace the primary with whichever crosscheck looks favorable.

The per-boot absolute enabled/disabled costs and eight-cell sums are required context for that judgment, including null and adverse findings across all four workloads. They do not create a new production-application throughput claim. Two independent boots per image/workload remain limited between-boot evidence, even when a small-sample bootstrap interval excludes zero.

## Counter and mechanism limits

The parent-only early-wake source lower bound for this configuration is `4 * (32 + 64 + 1) = 388`, including final release wakes outside steady timing and inside WHOLE. Thus a valid complete run saturates the eight-bit accepted-trigger counter at 255 in either image. Saturated counts cannot quantify the removed scheduler-selection triggers or establish their timing, overlap or utility.

Minimum admission, exact configured entries and zero-drop/drained-controller identities remain mandatory consistency gates. Aggregate admitted/resident counts cannot assign usefulness to a particular phase or prove independent per-cell cache state. The difference in trigger mechanism remains established by the reviewed exact one-byte image control, not by a saturated status count. These limits apply regardless of the sign of the eventual performance contrast.
