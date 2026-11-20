This report preserves three failed physical attempts to run checked real-zlib post-resume work. Local library checks and printed timing rows are kept distinct from complete execution acceptance: **sessions 4, 5 and 6 all have runner FAIL, and none is accepted performance evidence**. Active session 7 was not read or used.

All attempts used the old accepted bitstream `f0910fa4ee537963088cbeb6b21379ddb6b237af900a0aea7b12b87c0426fc3d`, Linux NBF `ef50be197b458b512f82ed8a9deccc0bdfcfadba760ccd119d67e46837501cf4`, workload ELF `407fd9ec2edb0e67cce2e3b7c7049cc3cfa85809189619d99d13dabc51574308`, and unmodified shared-library SHA256 `e2c082d208dc2c6041fdef01579e1e86a441bb0dbc930e13fe8e2eee9eedc63b`. The library was staged as `/tmp/libz.so.1` with `LD_LIBRARY_PATH=/tmp`; session 6 reports runtime zlib version 1.2.13. These records do not test the new first-completed retention RTL or new kernel ABI.

| Session | Furthest verified phase | Failure and acceptance boundary |
| --- | --- | --- |
| 4 | Partial raw-base64 library transfer | Guest `sh[1]` reports unhandled signal 11 at address zero in busybox during transfer. No completed library SHA, ELF staging, benchmark configuration or result rows. The planned 256 KiB second run never started. |
| 5 | Compressed library decompressed and guest SHA verified | Old raw ELF echo transfer times out after 238 complete echo commands out of 406. No guest ELF SHA or benchmark result rows. |
| 6 | Library and ELF gzip payloads decompressed and guest SHAs verified; all eight local checked cells printed | `PIPE_HINT_PASS` and zero prefix drops appear, but no guest shell return, CORE PASS or BSG PASS. The runner times out and records FAIL. |

All three session manifests record the shared reservation `/home/coyang/fpga-artifacts/pynq-session.lock`, acknowledgement by all three coordinating threads, failed session state, and recovery completed **before reservation release**. Release times are 18:10:15 UTC, 20:21:22 UTC and 20:43:06 UTC respectively. Recovery is recorded separately from benchmark acceptance; a recovered board does not convert a failed run into a performance result.

The intended ELF bytes stayed fixed while transfer encodings changed. Raw ELF transfer script SHA256 is `d3b2d9e040c1e0a0604efc7a0f8f54703c730cab840a380695bf3663784c5d53`; gzip ELF script SHA256 is `953d44b4eef1e19a8945c4614607c3b11e7109d29d80ddaafede78eb9054230f`. Offline decoding of either script yields the same 23,112-byte 407f ELF. This is an identity check, not evidence that session 5 completed its transfer.

Sessions 5/6 use the same 125-command compressed library payload: 47,981 compressed bytes, wire SHA256 `afb69663e195e3a671fa12d672eca5ccc0d6b3f5f15b0c7e285e6f25593aefe4`, decoding to 98,120 bytes with the e2c library SHA above. Session 6's 28-command compressed ELF payload has wire SHA256 `d6d66dc29619fca99cfca28dbeb41b15dc357ef651aeb5ce85b46c1819715721`. Raw console visual wrapping can split destination filenames as well as base64 text; offline payload reconstruction removes CR/LF only for command decoding, then validates decompression and exact SHA. Raw marker parsing retains line boundaries.

The requested workload is 64 timed futex roundtrips after 32 warmups, 4 paired repeats, 32 KiB private corpus per process, plain profile, `futex-early` policy and terminal_handshake=1. Each resumed request rotates over an up-to 4 KiB block and uses actual unmodified `compress2` at default level, `uncompress`, and output CRC checks. Library internal allocation/processing costs are inside requests; corpus/scratch setup and independent total checks remain outside the steady timer. No resource-count rows were emitted by this ELF.

The following are literal session 6 cell totals, **diagnostic only**:

| Repeat | Order | Enabled | Raw cycles for 64 roundtrips |
| --- | --- | --- | ---: |
| 0 | 0 | 0 | 247,118,152 |
| 0 | 1 | 1 | 249,971,850 |
| 1 | 0 | 1 | 202,928,775 |
| 1 | 1 | 0 | 136,086,280 |
| 2 | 0 | 0 | 137,149,162 |
| 2 | 1 | 1 | 137,165,781 |
| 3 | 0 | 1 | 137,597,332 |
| 3 | 1 | 0 | 137,966,761 |

The chronological change from roughly 247–250 million cycles initially to roughly 137 million later is substantial. Without complete execution acceptance, resource counts or a confirmed exit-boundary trace, its cause remains **unproven**. No paired speedup, accepted performance comparison, normalization or confidence interval is computed here. Successful local compress/decompress/CRC checks and clean prefix counters establish those local facts; they do not prove the parent returned to the shell or that the host shutdown gate completed.

[zlib-diagnostics.json](zlib-diagnostics.json) binds all three raw logs, runner statuses, session/recovery manifests, intended transfer scripts, reconstructed wire identities, old NBF/library identities and session 6's eight archived host-source snapshots by SHA256. It preserves each failure phase, literal diagnostic rows, missing terminal/resource markers and recovery timestamps. No board call, source edit, staging action or active-session read was performed for this report.
