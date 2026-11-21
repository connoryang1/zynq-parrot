This protocol fixes the next scoped whole-cell experiment before performance collection. It compares the existing bounded image pair using one unchanged scoped ELF and transfer. The short session18 check is a functional pilot; neither it nor session17's legacy WHOLE results belongs to this performance configuration.

# Scoped mode-14 control admission

## Fixed question and inputs

The question is whether removing the historical incoming-task-selection trigger improves the complete checked cell, including setup, allocations, fork, warmup, steady transactions, checks, reaping, frees, mode-zero cleanup, bounded reported-prefix-controller drain, and resource observers. The intervention is the previously reviewed one-byte mode-14 kernel instruction control. It is not an RTL change, a new address table, or a general-application performance result.

Use only fixed selector `embedded46` in `compare_scheduler_pipe_hint_mode14.py`:

| Arm | Existing NBF SHA-256 |
| --- | --- |
| A, historical combined early+selection policy | `2e5ccc94a801fe724fd5b8787f5086fb6e939795c4ec98e49ef7a702ad9c024a` |
| B, early-only one-byte control | `32db338b492964d3e1aecdc35fbb9dc77a7b1959740f9717a71f689a144d0efa` |

The ELF is plain scoped resources SHA `8e64b984180436ffc15504ee6f47fe678aaedec3e6a7fedbeba68b75825f14bb`; the gzip transfer is SHA `dedced14f044f0ab9caaab4f91388d2ecca42a2749196caddc4558cb814cd138`. Keep the same transfer, ELF, accepted bitstream SHA `f0910fa4ee537963088cbeb6b21379ddb6b237af900a0aea7b12b87c0426fc3d`, runner SHA `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`, host source snapshot and all other identity/configuration fields across arms. The existing rootfs still embeds legacy ce0, so this study must use the new hash-verified gzip ELF rather than the embedded legacy resource file. No new image is needed.

For each of scan, lookup, parse and chase, fix `working_set_kib=32`, `loops=64`, `warmup=32`, `repeats=4`, `policy=futex-early`, `sync=futex`, `profile=plain`, `terminal_handshake=1`, and complete-policy scope v1. Do not select workloads, sizes or repeat counts after viewing effects. Deflate and the zlib-scoped ELF are separately prepared but excluded from this fixed four-workload experiment.

## Acquisition order and reservations

Collect four independent fresh boots for every workload in image order **A B B A**, giving at least two complete boots per image/workload. Workload order across these image waves is **forward, forward, reverse, reverse**: scan/lookup/parse/chase for A1 and B1, then chase/parse/lookup/scan for B2 and A2. Retain chronological acquisition order. A reservation contains at most two guest executions and is released before the next reservation. The maintained wrapper performs recovery before each guest execution, so even the two cells sharing one reservation have independent fresh boots.

| Reservation label | Image/replicate | Guest executions, in order |
| --- | --- | --- |
| A1-first | A1 | scan32, lookup32 |
| A1-second | A1 | parse32, chase32 |
| B1-first | B1 | scan32, lookup32 |
| B1-second | B1 | parse32, chase32 |
| B2-first | B2 | chase32, parse32 |
| B2-second | B2 | lookup32, scan32 |
| A2-first | A2 | chase32, parse32 |
| A2-second | A2 | lookup32, scan32 |

These are plan labels, not preassigned physical session numbers. The coordinator uses the existing read-only-open global flock, existing three-agent acknowledgments, staging, recovery, maintained runner, immutable source checks and a new output directory for each reservation. No parallel board actions are authorized by this document.

## Complete-run gates

Admit a log only after runner status PASS, strict PIPE_HINT/CORE/BSG terminal markers and runner exit zero, exact identities, one complete independent boot, all configured paired cells, ordered WHOLE/resource rows, and the exact once-before-cells SCOPE marker. Require physical boot evidence for the 46MiB allocation: runner allocation 48,234,496 bytes, Linux total 47,104KiB and DMA32 ending `82dfffff`, as already enforced by the fixed embedded46 comparator. Retain all controller drain/drop/counter invariants; saturation does not establish early-only attribution.

Scope v1 checks reported prefix-controller bits 1/2/3/54 only. It does not establish all UCE response or memory-system request completion. That limitation remains in every interpretation. The initial startup reset/drain is outside the cell timers; cleanup reset/drain is inside them. The measured application is this checked synthetic request-processing harness, not a complete production application.

Never admit timed-out, hung, signaled, drain-exhausted, partially printed, nonzero-exit or incomplete-transfer runs, even if some cells show favorable numbers. Preserve every failure and attempt in chronological order. Complete the predetermined ABBA matrix without result-dependent stopping. A failed scheduled execution may be retried in the same arm/workload slot after recovery; retain the failed attempt and retry rationale, and do not replace a valid complete execution according to its effect. If safe completion is blocked, report an incomplete study and preserve the fixed plan rather than claim a performance result.

## Analysis and decision

Run the dedicated comparator separately for each workload, with both A logs and both B logs and `--image-pair embedded46`. Use its deterministic hierarchical bootstrap across independent boots and paired blocks. Primary contrast: **B-minus-A difference in paired off-on WHOLE benefit per cell**. A positive value favors removal of the late selection trigger. Secondary contrast: corresponding steady round-trip benefit. Retain every boot effect, enabled-order pattern, resource delta and uncertainty interval; interpret four workloads together, including null or adverse effects. A positive controller/cell count alone is not a performance benefit.

Do not pool across workloads, image selectors, scope versions, ELFs, transfer shapes, configurations, or legacy ce0/session17. Session18 (`8` loops, `4` warmup, `2` repeats) remains a functional pilot and is excluded. Report a confidence interval that includes zero as unresolved at this sample size; do not declare a general application win from a favorable point estimate. A supported kernel-only improvement requires complete valid execution and a consistent complete-cell benefit with an explicit scope limit, not a steady-loop-only or incomplete-run effect.
