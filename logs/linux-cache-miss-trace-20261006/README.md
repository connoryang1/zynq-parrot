# Linux scheduler handoff cache-miss capture

This experiment measures accepted L1 instruction- and data-cache demand misses
during a same-CPU Linux futex handoff on the physical PYNQ-Z2 recorder image.
All accepted runs used a fresh overlay load and the corrected non-debug Linux
shell NBF.

## Exact identities

- recorder bitstream SHA-256:
  `f4a183d8f900170ce5a6eb59366d56609cbe0f492063ea5a41b791d807306c5a`
- non-debug Linux NBF SHA-256:
  `892b19f7a9d697bfc84adc2853e2fe9165a92ced7305a4971d2bb7577c8b1438`
- board control program SHA-256:
  `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- full-window/prefix-dump ELF SHA-256:
  `83f973ec3223b5d5c7c101253e2d85029f427fc14c2fa00f1a064d5b3642d20a`
- sliced-window ELF SHA-256:
  `ccbc7a5661edd00ba51798918fdb7ef2f40f4c22dd1d3be6985c23cff7c40600`

The maintained source gained a `peer_wake` timestamp after these board runs;
that additional marker does not change the window endpoints, but its rebuilt
ELF has a different hash. The hashes above identify the exact measured ELFs.

## Complete sliced result

| Fresh-boot window | Cycles | I misses | D misses | Overflow | Runner |
| --- | ---: | ---: | ---: | --- | --- |
| source to peer entry | 11,379 | 48 | 3 | none | PASS |
| peer entry to source resume | 28,883 | 218 | 10 | none | PASS |
| sum | 40,262 | 266 | 13 | none | — |

The independent leg sum is within 412 cycles (1.01%) of the complete
non-overflow full-window run at 40,674 cycles. Both sliced runs printed
`TRACE_PASS`, exited zero, powered Linux down with `poweroff -f`, reached
`CORE PASS`, and have `RUNNER_EXIT=0`.

Disarm is a retired CSR write rather than a combinational recorder gate. One
source-to-peer instruction request was accepted 43 cycles after the peer-entry
timestamp while disarm propagated; it is retained in the 48-record count. In
the reverse run, Linux dispatched the source inside `FUTEX_WAKE`, so the
post-wake `peer_block` sample occurred after source resume. The window start,
peer-entry, and source-resume endpoints remain ordered and are the boundaries
used above. The analyzer reports any such post-boundary records separately in
`unassigned_record_counts` instead of silently dropping them from its phase
totals.

The exact retained board-side logs are:

- `cache-miss-trace-to-peer.log`, SHA-256
  `066b633faa245c4ec436b6240d399179b1884d5febbb68702fff85261b75abf9`
- `cache-miss-trace-from-peer.log`, SHA-256
  `2fc9456151b17163a03da2da8fb47a3ab48e5752800e710a2023ffa7f73e88e2`
- their full runner logs have SHA-256
  `ab17324d37063994eb16b3b621fc4e4034ad6ca83b30286abfd6a041d0e72088`
  and
  `8ed1c0f178114c2edd7cb38a714c00290de3d1bb6509929cecfcc08b2f69be6e`.

## What the records show

The source-to-peer leg contains 46 kernel-text instruction misses, two
instruction misses outside the fixed kernel/OpenSBI executable ranges, and
three data misses. The reverse leg contains 209 kernel-text instruction
misses, seven OpenSBI instruction misses, two other instruction misses, and ten
data misses. Thus 262 of 266 sliced instruction misses (98.5%) are shared
kernel/OpenSBI code rather than private userspace code.

The L1 I/D caches are 64 sets, eight ways, and 64-byte lines (32 KiB each).
The source-to-peer trace has 48 unique instruction lines; its most occupied set
contains ten lines, two beyond associativity. The reverse trace has 215 unique
instruction lines; its most occupied set contains nine lines, one beyond
associativity. Data footprints are small and fit their sets. An exact restore
must therefore retain recency per set rather than install every remembered
instruction line indiscriminately.

Across three earlier full-window captures, the two saturated instruction
prefixes shared 224 lines, about 88% of each prefix. Simulating an eight-most-
recent-lines-per-set predictor from one run to the next covered 222 of 256
instruction-miss records (86.7%), while it covered only 14 of 35 data-miss
records (40.0%). The stable opportunity is primarily the privileged
instruction footprint. A shared kernel slice plus a small per-task data/recent
instruction slice is better supported by this evidence than duplicating the
entire observed footprint for every software thread.

## Full-window depth result

Full captures varied from 40,674 to 58,880 cycles. One run fit with 221 I and
11 D records; two runs filled the 256-entry I history while D remained at 29
and 35 records. The capture tool now prints all retained records as
`TRACE_TRUNCATED` and exits nonzero on overflow. This preserves analyzable
prefixes without treating them as complete histories. Use
`tools/analyze_cache_miss_trace.py` for deterministic count, timing, unique-line,
and interarrival summaries.
