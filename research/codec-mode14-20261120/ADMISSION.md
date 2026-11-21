This is a fixed pretarget codec extension, separate from the running plain four-workload matrix. It uses existing zlib and the already built scoped zlib ELF; no new table, address/layout tuning, library build, kernel/rootfs image or source8 change is introduced. The codec pilot follows the plain16-boot matrix; the primary codec comparison follows the successful excluded pilot. This offline task executes no model or board and reads no primary data.

## Fixed identities and workload

| Artifact | SHA-256 |
|---|---|
| Scoped zlib/resource ELF | `079f974d671908f6aa922122f6901b3123cf16ec244be25e3432b4df500b465b` |
| Exact gzip ELF transfer | `580da454d65c866aa4c0a880d63fec8948f1f813ea9791128357b892eea340d8` |
| Unmodified host/embedded libz.so.1 | `e2c082d208dc2c6041fdef01579e1e86a441bb0dbc930e13fe8e2eee9eedc63b` |
| A: bounded embedded combined-mode14 NBF | `2e5ccc94a801fe724fd5b8787f5086fb6e939795c4ec98e49ef7a702ad9c024a` |
| B: bounded embedded early-only NBF | `32db338b492964d3e1aecdc35fbb9dc77a7b1959740f9717a71f689a144d0efa` |
| Accepted bitstream | `f0910fa4ee537963088cbeb6b21379ddb6b237af900a0aea7b12b87c0426fc3d` |
| Accepted package | `b139be87bdadf965f2d5e7eb7cd290bc56be76753a2377dc25f5c690a69d5ab1` |
| Immutable46 MiB control program | `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30` |
| Actual board helper, every boot | `de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90` |

Use `--embedded-zlib-library` **and** exact host library path `/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/libz.so.1`. The fixed copy is `cp /opt/bp-resume/libz.so.1 /tmp/libz.so.1`; actual guest library SHA must match before ELF transfer, then actual guest ELF SHA must match before execution. The gzip ELF transfer remains gzip; it is not an embedded ELF declaration. `LD_LIBRARY_PATH=/tmp` selects the copied library. No alternate library/path/delivery or helper-version transition is admitted within this cohort.

The workload is checked `compress2`/`uncompress`/CRC work on rotating up-to4096-byte blocks using a private **32 KiB INPUT CORPUS** per process. That corpus size is not the total D working set: codec workspace, internal allocations, buffers and library code are additional, and their actual allocation/computation/cleanup cost belongs in WHOLE. No workspace byte count or cache-capacity estimate is invented.

Fix `workload=deflate`, `policy=futex-early`, `sync=futex`, `profile=plain`, `loops=64`, `warmup=32`, `repeats=4`, terminal handshake1, scope v1 and resource statistics1. No retention CSR telemetry is used on this old-bitstream experiment. Runtime library metadata must be zlib1.2.13, block4096, input corpus32 KiB. No size/loop/order change follows from an observed effect.

## Acquisition, gates and exclusions

First collect one **A-image8/4/2 baseline functional pilot**, using the same ELF/library/delivery/configuration apart from loops8/warmup4/repeats2. It must return normally through shell, CORE/BSG and runner0, with all other gates. It is excluded from every primary estimate and uncertainty interval, regardless of timing. It does not select a new workload or tuning parameter.

Then collect four independent complete fresh boots in **A1, B1, B2, A2** order, exactly **one guest boot per reservation**, two independent boots per image. All five executions, including the pilot, require the same de54 helper. Use existing whole-session flock and board-side lock, source8 snapshots, fresh power/recovery/overlay and new output paths. `commands.json` and `COMMANDS.md` specify the exact five future commands; none has been executed by this task. Pilot and primary reservations cannot share a boot.

Every admitted run requires exact source/artifact/CLI identities, actual guest library hash followed by actual guest ELF hash before execution, fixed embedded-library encoding, actual46 MiB memory evidence, exactly one Linux boot, correct CONFIG/SCOPE, all paired RESULT/WHOLE/RESOURCE rows, checked codec outputs, normal shell return, CORE PASS, BSG PASS, runner exit0 and de54 executed-source marker after program completion. Require both48,234,496-byte allocation messages, `Memory limited to 46MB`, Linux47,104 KiB, DMA32 last byte`0x82dfffff`, Next Arg1`0x82200000` and `mem=46M`. No timeout, signal, hang, partial print, missing hash/return, controller/drain/drop failure or transfer mismatch is admitted.

The historical session6 PIPE_HINT_PASS without normal return/complete host termination is excluded, along with its old identities and drifting incomplete timings. It is not a codec replicate or permission to accept partial output. Do not infer that library delivery resolves any prior failure or drift cause. Preserve all failures chronologically; never replace a valid run based on its effect. Failed/replacement attempts require a prospective coordinator amendment rather than silently increasing or reordering this fixed cohort. Report all negative/null outcomes; no effect-based stopping or cross-workload pooling.

## Strict codec admission and analysis

The unchanged generic mode14 comparator correctly binds printed configuration to runner fields, cross-boot identity/library consistency, library banner/block/corpus, fixed image pair, memory bounds, scope, whole/resources and complete terminal gates. It is intentionally not a study-specific preregistration audit: it permits all statuses to omit a library SHA, checks identity consistency rather than these exact ELF/bit/library pins, and does not pin the command string, embedded-library encoding or de54 marker. Host fixtures expose those limits before data collection.

`codec_admission.py` closes those gaps **only for this codec study**. It pins `admission.json`, exact files and source8, mandatory library identity, command/delivery, actual guest hash replies and de54 marker, normal shell return, excluded pilot, complete chronological independent ABBA sessions and one boot per reservation. Every session's provenance/configuration is checked before image effects. It then invokes the unchanged generic comparator with `--image-pair embedded46` semantics and its20,000 hierarchical draws; no generic comparator or plain-matrix admission is relaxed or edited. Use `acquisition.template.json` to record the completed sessions and declare all attempts; fresh output files are mandatory.

The primary is **B-minus-A difference in paired off-minus-on WHOLE benefit per cell**. Positive favors removing the selection-time trigger. Secondary is the corresponding steady-roundtrip contrast. Preserve independent-boot/pair strata and the existing seed`0x4d313443`. Report every boot's eight WHOLE cells in acquisition order, separate enabled/disabled medians and sums, and eight-cell sums. The sum excludes startup and inter-cell reporting; it is not process wall time. The unchanged absolute-cost helper jointly resamples absolute enabled, disabled and pair-total cost with the primary, preserving its exact estimate and interval.

A positive paired-benefit contrast is insufficient for a kernel-optimization claim if absolute enabled cost regresses, fails to show supported reduction or boot/order evidence leaves carryover/drift unresolved. Report those discrepancies and all adverse/null results, retaining the original primary rather than choosing a favorable cross-check. Two boots per image provide limited between-boot evidence. No automatic optimization/deployment claim is produced by the wrapper.

Scope v1 disables task-mode14 and drains only reported prefix bits1/2/3/54; it does not invalidate completed retained lines or prove all UCE/memory responses drained. Retained-line carryover can affect reporting and next setup before the existing setup fence, so this is the fixed repeated-crossover schedule, not isolated cold cells or a prefetch-versus-retained-capacity comparison. The parent-only early-wake lower bound is388 per primary boot, saturating the8-bit trigger counter; saturated counts cannot price removed selection triggers or prove their utility. Exact one-byte kernel/image provenance, minimum admissions, configured entries and zero-drop/drain gates remain mandatory. Real-library work does not remove these interpretation limits or establish complete production-application throughput.

This preregistration and wrapper use only source, immutable artifacts and synthetic host fixtures. The plain matrix audit, source8, old ELF/library/images and all target state remain unchanged.
