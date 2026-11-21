This change repairs the boundary of the mode-14 whole-cell measurement. It adds an opt-in cleanup protocol and host verification without changing the legacy build recipes. It is a benchmark-methodology fix, with no FPGA performance result or prefetch optimization claim.

# Complete policy scope

## Confirmed legacy limitation

`run_futex_cell()` writes task mode 14 before fork and leaves the parent's mode armed when returning. The old resource ELF (`ce0a21a67a36f522c46c590cf790b18bc535f09b85e8d8f20fd36e9a591cec70`) therefore executes RESULT/WHOLE/RESOURCE reporting while armed, and can enter the next nominally disabled cell's initial mmap/pipe setup before its existing setter writes mode zero. Those legacy WHOLE values are not accepted as a causal complete-cell policy comparison. Checked steady functional observations remain available with their separate endpoint and mechanism limitations; this finding does not convert incomplete board runs into evidence.

## Opt-in protocol

`BP_RESUME_COMPLETE_POLICY_SCOPE=1` requires `BP_RESUME_RESOURCE_STATS=1`. The program first clears task mode to zero and polls the reported prefix-controller status before any library/configuration output. This initial reset/drain is outside per-cell timing and establishes a clean first cell.

Every cell then runs the existing setup, warmup, timed transactions, checks, child reaping and workload frees. Before the ending resource observers and WHOLE timestamp, the parent writes mode zero and polls status bits 1 (busy), 2 (entry pending), 3 (read pending) and 54 (resident-query pending). Both arms pay this cleanup inside WHOLE. At most 4096 reads are attempted; reset/status errors or exhausted polling terminate without PASS. All result reporting and the next cell's initial setup execute after this cleanup. No fence, delay, or timing knob was added.

The once-per-program physical marker is exactly:

```text
PIPE_HINT_SCOPE version=1 mode=cell cleanup=mode0 drain=prefix-controller max_polls=4096
```

This is a **prefix-controller-only** drain. The old status does not expose all UCE response occupancy; it cannot establish that all UCE responses or memory-system requests are drained. The marker, analyzer and dedicated mode-14 comparator retain this limitation explicitly. The analyzer accepts and qualifies legacy WHOLE logs; the dedicated causal comparator requires the new marker, correct position, complete WHOLE/resource rows, and otherwise unchanged strict fixed-image/identity gates. Mixed scope configurations cannot pool as identical configurations.

## Separate build targets

- `pipe-hint-benchmark-plain-scoped-resources-dynamic`
- `pipe-hint-benchmark-zlib-scoped-resources-dynamic`
- `emit-pipe-hint-benchmark-plain-scoped-resources-compressed-transfer`
- `emit-pipe-hint-benchmark-zlib-scoped-resources-compressed-transfer`

These produce distinct files; the plain target does not link libz. All seven prior ELF recipe blocks match HEAD byte for byte. With the scope gate undefined, RV64-preprocessed C matches the archived pre-scope benchmark source across all six benchmark flag combinations (the seventh recipe is the separate unchanged probe). Explicit gate value zero also produces identical host binaries to the undefined gate for four plain/zlib/resource combinations.

The coordinator's new RV64 outputs were independently reproduced using the pinned Buildroot GCC 13.2.0 compiler, with separate output paths and no SDK changes. All seven legacy ELFs also reproduce their exact pre-scope hashes. `compiled/manifest.json` binds the source snapshots, actual Make invocation, expanded compiler commands, build stdout/stderr, readelf output, reference and rebuilt binaries, compiler/tool identities, and both transfers. The source and original output hashes remained unchanged throughout the rebuild. `archive_builds.py` refuses to replace an existing archive.

| Scoped variant | ELF SHA-256 | Gzip-transfer SHA-256 | Commands |
| --- | --- | --- | --- |
| Plain resources | `8e64b984180436ffc15504ee6f47fe678aaedec3e6a7fedbeba68b75825f14bb` | `dedced14f044f0ab9caaab4f91388d2ecca42a2749196caddc4558cb814cd138` | 32 |
| Zlib resources | `079f974d671908f6aa922122f6901b3123cf16ec244be25e3432b4df500b465b` | `580da454d65c866aa4c0a880d63fec8948f1f813ea9791128357b892eea340d8` | 34 |

Offline base64 decoding and gzip decompression reconstruct each exact scoped ELF. Readelf confirms RV64 executable files and the expected dynamic loader; only the zlib variant requires `libz.so.1`. These build results do not establish physical execution or performance acceptance. The fixed next measurement protocol is in `ADMISSION.md` and `admission.json`.

## Host validation

The focused command in `verification.json` passed 104 tests. The new real-fork suite exercises pipe and futex synchronization, parent-only and both-direction registration, scan/lookup/parse/chase/deflate, paired order reversal, and strict observer/setup mode-zero checks. A shared mocked controller has four independently reported pending states. Mock-only poll latency proves queued cleanup cost is inside WHOLE; host nanoseconds are software verification, not BlackParrot cycles. Stuck controller, reset failure and status failure tests fail without PASS. A compile-negative case rejects scope without resource timing.

Analyzer tests reject duplicate, malformed, reordered and runner-mismatched scope markers. The dedicated comparator rejects legacy unscoped WHOLE input while legacy analysis remains qualified. After making the comparator's controller-only limitation explicit, all 18 dedicated comparator tests passed again. Python compilation and `git diff --check` passed.

An initial mock assertion counted only startup plus cleanup mode-zero writes and overlooked the two existing disabled-cell setup writes. That test expectation was corrected to seven writes for the two-repeat futex case (five for pipe); the implementation was not changed to satisfy it. No failed test run, mock timing, or incomplete board run is a performance result.

No images, shared SDK files, board sessions, RTL, host runners, staging scripts or transfer emitter were changed by this task. The coordinator owns subsequent reserved physical runs.
