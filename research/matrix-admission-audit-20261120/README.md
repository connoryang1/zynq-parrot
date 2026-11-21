This directory records the offline admission gate for the fixed scoped mode-14 matrix. The implementation and tests use synthetic fixtures only; no primary effect logs have been opened or audited by this task. A successful protocol audit establishes the eligibility of the declared evidence, not a performance conclusion.

# Fixed matrix admission

The generic mode-14 comparator deliberately accepts any internally matched supported experiment. It does not by itself enforce the exact preregistered 64/32/4 configuration, all four workloads, the acquisition chronology, or the frozen host scripts. `linux-tests/audit_admitted_matrix.py` supplies that separate gate without changing the comparator, runners, source-eight set, images or fixed protocol.

The audit pins admission SHA `501d6b12eb0fa10b9f1d298a2be6cb365695c2be7aac96b0984ea4ffe5f4a360` and the exact frozen eight host-source hashes, including guest runner `ea566381...` and session wrapper `8d527a48...`. `verification.json` records a current-byte check of all eight sources before any future edits. At final audit time, the hash of the completed acquisition JSON is recorded rather than hardcoded, so later visit/provenance fields are retained and bound.

## Input and execution

Each `acquisition.json` visit has these required fields, in the eight preregistered reservation slots:

```json
{"label": "A1-first", "session_manifest": "/absolute/path/to/session.json"}
```

An optional `session_sha256` is checked when present. Other acquisition metadata remains bound by the complete acquisition-file hash. The acquisition must retain `created_utc`, `admission_sha256` and the exact `host_sources` map. No override for a different protocol or source freeze is exposed by the CLI.

Only after the complete matrix is terminal, the coordinator can run:

```sh
python3 linux-tests/audit_admitted_matrix.py \
  --acquisition research/complete-policy-scope-20261120/acquisition.json \
  --output research/complete-policy-scope-20261120/protocol-accepted.json
```

This command has **not** been run on the primary acquisition. It refuses an existing output path. Incomplete visits or noncomplete sessions fail before guest results are parsed; a rejected audit creates no accepted manifest.

## Gates

The audit requires eight complete released session manifests and sixteen complete guest executions. Labels, images and the wrapper plan must follow A1/B1 forward, B2/A2 reverse, with at most two executions in each reservation. Session times must have explicit time zones, start after the freeze, be increasing and not overlap. Each session must identify the agreed lock, all three acknowledgments, one common host, the frozen source-hash map, and actual byte-identical regular source snapshots. Frozen wrapper semantics establish plan order as execution order; the declared chronology is provenance, not a hardware attestation.

Every wrapper cell must have the exact ELF, transfer, bitstream, runner, workload, 32KiB input, 64 loops, 32 warmup, four repeats, futex-early/futex/plain and terminal/delivery shape. Actual NBF and transfer files are hashed; the gzip transfer is decoded and bound to the expected ELF. Fixed embedded46 image proofs are checked with the maintained verifier. Every log/status is bound to its index and workload in its own session directory. Transcript and session paths/inodes are unique, transcript contents are unique, and status paths/inodes are unique. Status contents may legitimately repeat across same-image/workload boots: the runner status has no run timestamp or measured timings.

The maintained parser enforces one fresh Linux boot, exact once/ordered scope-v1 marker, all eight paired RESULT/WHOLE/resource cells, terminal completion, runner exit zero and controller drain/drop/counter invariants. The audit additionally pins the parsed guest configuration and all identities to the protocol, checks the actual guest ELF hash reply and exact guest command, and requires actual 46MiB allocation/Linux total/DMA32/FDT runtime evidence. It hashes every input and detects a change between validation and manifest completion.

The accepted manifest binds the admission, completed acquisition, audit/validator sources, all session manifests and frozen snapshots, delivery artifacts, sixteen logs and statuses, image proofs and actual bounds. It supplies the four predetermined per-workload comparator input lists. It calculates no image contrast; the dedicated comparator runs only afterward, separately per workload, using its preregistered deterministic hierarchical bootstrap.

## Endpoint and statistical limits

Source review found no new mismatch between the scoped WHOLE endpoint and the registered endpoint. Whole timing includes the post-steady release wake, child checks/free/exit and reaping, parent checks/free, mode-zero cleanup, controller polling and ending resource observers. The initial startup reset and observer printing remain outside the cells. Scope v1 polls controller bits 1/2/3/54; it cannot certify all UCE responses or memory-system requests have completed.

Mode-zero cleanup also does not invalidate already completed retained cache lines. Accepted BP `684e5d8` keeps detached replies until replacement or fence.i; task-mode clearing only stores the mode. The next cell's fence follows its initial mmap/pipe/fork/allocation. The registered repeated-crossover schedule can therefore carry completed lines into reporting and next initial setup. This is a scope limit, not authorization to add a fence/delay or modify the fixed collection plan, and it precludes interpreting the contrast as an isolated cold-cell or pure prefetch-versus-capacity experiment.

The parent-only early-hook source lower bound is `4 * (32 + 64 + 1) = 388` opportunities, including the four final release wakes outside steady timing but inside WHOLE. Both image arms therefore saturate the eight-bit accepted-trigger counter at 255 on a valid run. Those counters cannot quantify removed late-selection triggers or localize admission timing. The control's mechanism comes from the byte-bound single-instruction proof; minimum admissions and zero drops are consistency gates rather than an isolated effectiveness metric.

The comparator resamples independent boots and then complete paired blocks, using the same sampled blocks for WHOLE and steady results; it contrasts median paired benefits, not enabled medians. That matches the preregistered calculation. Two boots per image remain weak between-boot evidence, and the ordered within-boot repeats may retain serial drift. Bootstrap intervals describe this small fixed experiment and do not establish broad application throughput. Per-boot order and resource diagnostics must remain visible, including null or adverse outcomes across the four workloads.

## Verification

The focused fixture/parser/comparator suite passed 59 tests. Mutations cover incomplete sessions before parsing, changed protocol/freeze, wrong chronology/order, wrapper and guest parameter changes, mismatched identities, actual NBF/transfer mutation, corrupted source snapshots, duplicate evidence, missing scope/resource/terminal/bounds/hash replies, runner failure, controller drops, changing inputs during audit and output replacement. Fixtures intentionally use small stand-in delivery hashes via test-local patches; the production admission hash is separately checked, and no such override exists in the tool's CLI. The first audit-test run exposed Python 3.8's missing `Path.hardlink_to`; using `os.link` fixed the fixture compatibility issue. No primary data or board operation was involved.
