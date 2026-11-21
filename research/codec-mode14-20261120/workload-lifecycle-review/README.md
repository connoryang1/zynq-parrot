This directory preserves host-only memory and lifecycle diagnostics after the codec A1 functional pilot failed. The failed FPGA boot and its three printed complete cells remain excluded from performance evidence. No benchmark source, bound target ELF/library, frozen runner or board state was changed by this review.

# Workload lifecycle review

The frozen C/header used by the target match the reviewed copies exactly: C SHA `b242d76a3bc5fb754ea92a6167ede622397e19630c7b9e5a415715deb085378e`, header SHA `5d4766cb71b144a93e2b896acf970fce05b349688233a0fae1a5b3458ebe6caa`. Actual guest ELF/library hashes matched their bindings before execution. Target libz is SHA `e2c082d208dc2c6041fdef01579e1e86a441bb0dbc930e13fe8e2eee9eedc63b`, with runtime version 1.2.13.

## Bounds and ownership

The workload allocates a 32KiB immutable corpus, eight expected block CRCs, a 4110-byte `compressBound(4096)` destination, and a 4096-byte decoded destination. Each request uses at most 4096 input bytes, resets destination capacities before the library calls, checks return codes and decoded length, and computes a CRC over the resulting output. Library failures remain sticky through final total verification. The expected CRCs come from pristine input before timing, and host reference tests independently calculate them.

Parent and child allocate private workload state after fork. Each child verifies/frees its state before exit; the parent waits for successful child exit before unmapping the shared handoff state and checking/freeing its own buffers. No live zlib stream is intentionally inherited or shared across fork. No bounds, use-after-free or double-free error was identified in this source review.

Actual RV64 library disassembly retained here shows `compress2` calling `deflateInit_`/`deflateEnd`, and `uncompress2` calling `inflateInit_`/`inflateEnd` for each request. Upstream [zlib 1.2.13 compression source](https://github.com/madler/zlib/blob/v1.2.13/compress.c), [decompression source](https://github.com/madler/zlib/blob/v1.2.13/uncompr.c) and [deflate allocation source](https://github.com/madler/zlib/blob/v1.2.13/deflate.c) were consulted for API/lifecycle semantics. The default deflate implementation allocates four 64KiB arrays plus stream state. The prepared SDK did not retain a matching libz source build directory; this is not a bit-exact library rebuild/source-validation claim.

## Host checks and their limits

`report.json` records exact compile commands and runs. ASan/UBSan checks passed 10,000 normal 32KiB requests for each actual process seed, zero/small/tail/257KiB corpora, input/output corruption and injected `Z_MEM_ERROR`. A real-fork/futex run of the frozen benchmark at the exact `64 4 futex-early 32 futex plain 32 deflate` configuration passed all eight cells, using existing shared controller/prctl mocks. Source copies, mock/driver sources, compiler logs, output and event logs are retained here; host diagnostic binary hashes are recorded rather than committing the binaries.

Host libz is **1.2.11**, whereas target libz is **1.2.13**. The host libz DSO itself was **not instrumented**; application instrumentation/interceptors are not exhaustive validation of library internals. LeakSanitizer failed because the execution environment uses ptrace. That unavailable-check attempt is retained in `report-lsan-unavailable.json` and `run-0.stderr`; successful address/undefined checks explicitly disabled leak detection. There is **no leak-check result**, no exact RV64-library sanitizer result and no target correctness/performance proof.

## Resource-demand interpretation

Each complete configured cell performs 96 codec requests per process, or 192 across parent and child. The three printed FPGA cells reported 3718, 3720 and 3755 minor faults, approximately 19.4 per codec request, with zero major faults. This is substantially more kernel/allocator demand than the input-corpus size alone describes.

A separate normal-allocator host run of the exact eight-cell configuration also passed. Its first three minor-fault counts were 3734, 3721 and 3757, with roughly 3.7–3.9k per cell throughout. Those host counts are a diagnostic crosscheck, not predicted FPGA numbers; host kernel/glibc/library versions differ, and the host run reported one major fault per cell. Repeated stream allocation/free and metadata initialization are a concrete mechanism for substantial page-fault/VM activity. The high counts alone are not evidence of a leak, out-of-memory condition or memory corruption, and the workload footprint must not be labeled simply 32KiB.

## Failure hypotheses and decisive next diagnostic

The retained Oops excerpt reports kernel PC zero and RA `ffffffff8000a77c`, but stops before the full register set, cause/bad-address/status fields and call trace. Printing three cell triplets does not localize the failure to a specific subsequent setup, request, teardown or reporting instruction. No callee is named from a different kernel's symbols, and no kernel/hardware cause is assigned.

An obvious userspace lifecycle defect is not supported by the checked source and host tests, although target-specific behavior remains unvalidated. Allocation/page-fault pressure is a supported stress dimension that could expose a problem elsewhere; it is not an identified root cause. The minimum decisive next step is the coordinator's bounded full-Oops capture using unchanged target inputs, followed by register/callsite resolution against the exact byte-bound accepted kernel ELF. Capture the remaining registers (including s7), EPC/RA, cause, bad address, status, call trace and instruction bytes before deciding on a focused follow-up. No repeated performance sweep, modified benchmark, changed codec parameters or alternative replay tuning is justified by this incomplete failure.
