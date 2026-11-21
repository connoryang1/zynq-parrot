This helper implements the final analysis plan using admitted complete evidence and the registered absolute-cost addendum. Development and verification use synthetic fixtures only; no primary acquisition, primary effect log or image contrast has been read or run by this task. The fixed collection, primary estimator, timing endpoints and frozen host sources remain unchanged.

# Admitted matrix analysis

`linux-tests/analyze_admitted_matrix.py` accepts only the output of the strict fixed-matrix audit. It rehashes every nested binding, checks the exact four workload lists and two boots per image/workload, reruns the strict audit from its bound acquisition file, and requires exact equality with the supplied audit. It pins the analysis-limits addendum SHA `501901af3a15442c743afac451b73717048521c6215efddc29b5612845e95902`. Inputs and audit hashes are checked again before returning a result; rejected or changing evidence cannot produce an accepted analysis file.

After the coordinator completes and audits the fixed matrix, the intended invocation is:

```sh
python3 linux-tests/analyze_admitted_matrix.py \
  --audit research/complete-policy-scope-20261120/protocol-accepted.json \
  --output research/complete-policy-scope-20261120/admitted-analysis.json
```

This invocation has **not** been run on primary data. Existing output files are refused. There is no CLI override for the protocol, images, workloads or 20,000 bootstrap draws.

## Unchanged primary

The helper calls the existing `compare(..., image_pair='embedded46', bootstrap_samples=20000)` separately for scan, lookup, parse and chase. Each returned comparison is retained unchanged. Its primary remains **B-minus-A difference in paired off-on WHOLE benefit per cell**, with positive values favoring removal of the late-selection trigger. Its secondary steady contrast, all boot effects, orders, identities and existing limits remain present. Workloads are never pooled.

## Joint absolute-cost crosschecks

For each image, the existing `_strata` records are extended with the absolute enabled cost, absolute disabled cost and their total for that complete paired repeat. The unchanged `_draw` and `_median` helpers sample boots and then paired repeats; all outcomes in a chosen repeat stay together. The seed and sequence of boot/pair choices match the primary comparator. The helper asserts that both the primary point and bootstrap cycle interval remain exactly identical after extending the rows.

The added contrasts are **B-minus-A absolute costs**, where negative favors B and positive is a cost regression. Point estimates are medians across the paired-repeat rows with independent boot strata. Their joint hierarchical intervals preserve between-boot and within-boot variation. The pair-total median is labeled per pair; it is not relabeled a median or confidence interval for the eight-cell boot sum.

Every admitted boot separately retains all eight absolute WHOLE cells in repeat/order order, all four enabled and four disabled values, arm medians and sums, the exact eight-cell sum, paired benefits, enabled order, identities, resource rows, memory-bound evidence and trigger-accounting limits. The eight-cell sum equals the enabled sum plus disabled sum. It excludes startup and printed intervals, as required by the addendum, and is not a complete process wall-time claim.

A positive primary with an absolute enabled regression, uncertain enabled-cost interval, or no absolute enabled reduction is explicitly flagged. Only a positive primary point/interval together with a negative absolute enabled point/interval is eligible for further carryover/drift review. The helper always leaves `kernel_optimization_claim_established=false` and requires that review; it does not convert a small-sample interval into an optimization claim. Thus disabled-cost increases alone cannot establish a kernel improvement. These are descriptive/decision crosschecks, not a replacement primary or permission to select outcomes.

## Material limits

The fixed repeated crossover schedule can retain completed instruction lines into reporting and initial setup before the next existing fence. Scope v1 drains only reported prefix-controller activity, not all UCE responses or memory-system requests. The helper therefore makes no isolated cold-cell, pure prefetch-versus-capacity, or general-application throughput claim, and adds no measurements, fences, delays or trial-selection rule.

The known parent early-wake lower bound is 388 opportunities per complete configured run, saturating the eight-bit accepted-trigger counter at 255. Saturated counts cannot quantify removed late-selection triggers or place admissions in a phase. Mechanism attribution still comes from the reviewed exact one-byte control. Two boots per image/workload provide limited between-boot evidence; raw boot/order/resource context remains mandatory even when an interval excludes zero.

## Fixture verification

The tests use a complete synthetic acquisition with small stand-in delivery hashes through test-local patches. They verify four fixed unchanged primary calls, exact raw boot costs and sums, positive paired benefit despite absolute enabled regression, disabled-only cost increases, positive primary despite between-boot absolute-cost uncertainty, within-boot sampling with joint enabled/disabled/total identities, mutated/wrong audit rejection, exactly four workloads, changed source/log bindings, mutation during analysis and refused CLI overrides/output replacement. Production CLI constants remain fixed; synthetic tests reduce bootstrap draws to 100 for runtime only.

The focused admission/parser/comparator tests and final helper tests are recorded with source hashes and actual logs in `verification.json`. No frozen host source, runner, kernel, RTL, rootfs, image, collection protocol or board session was changed.
