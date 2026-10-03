# Linux hardware-group request integration

This experiment moves the existing two-context random-request workload into the
current ten-context Linux image. Linux owns one process and its address space;
the hardware modes use contexts 0 and 1 inside that process and bypass the
Linux scheduler on every request. All four modes use the same 8,192 requests,
2 MiB data set, cache-displacement pass, and checksum:

- `linux-threads-demand`: two ordinary pinned pthread workers;
- `batched-prefetch-load`: one Linux thread batches two hints and loads;
- `resident-demand-handoff`: two resident hardware contexts switch before each
  demand, without a hint;
- `resident-prefetch-yield-load`: each hardware context issues its own hint,
  switches, and consumes the demand when resumed.

The routed image is bitstream
`9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf` at
18 MHz. The Linux NBF is
`af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`.
The benchmark was rebuilt with `BP_NUM_CONTEXTS=10`; disassembly confirms the
hot path is `prefetch.r; csrw 0x800; ld`.

## Full unprimed result: rejected

All four warmups passed. In measured sample 1, batching completed in 884,697
cycles and the hardware demand control completed in 611,739 cycles, both with
the expected checksum. The following hardware-prefetch mode never returned.
The manager stopped it at the declared 600-second runtime limit after the core
had continued retiring instructions. This is a measured workload stall, not an
accepted timing result.

An isolated hardware-prefetch invocation independently produced a load page
fault after eight handoffs. The post-handoff load was the faulting instruction.
That first symptom motivated register-preservation probes, but the matched
controls below show that eight handoffs are not the actual capacity boundary.

## Reduced physical controls

The reduced probe gives each of two contexts a distinct array. Each context
publishes its intended address, issues `prefetch.r`, switches, compares `t0`
immediately after return, and only then performs the demand load.

A phased run passed 1, 2, 4, 8, 9, 16, and 64 iterations per context, then did
not return from phase 256. A fresh matched single-phase comparison gives:

| Launch preparation before phase 256 | Data lines read | Page coverage | Result |
| --- | ---: | ---: | --- |
| None | 0 | 0 | stall |
| `fence rw,rw` only | 0 | 0 | stall |
| Four lines in the first page of each array | 8 | 2 pages | pass |
| One line from each of four pages in each array | 8 | 8 pages | pass |

Both passing controls report zero source or peer register mismatches, probe exit
zero, `CORE[0] PASS`, and runner exit zero. The single-page result rejects the
initial hypothesis that covering all eight translations is required. The fence
result shows that architectural ordering alone is insufficient. A few demand
reads prepare some cold cache/memory-path state that the hint-plus-immediate-
handoff sequence currently requires; these measurements do not yet identify
that state.

## Bounded launch-read attempt: also rejected

The full benchmark was extended with an explicit diagnostic option that reads
four request lines per hardware context outside timing. This prepares only 8 of
8,192 requests, or 0.098%. It allowed the prefetch warmup and measured samples
1--3 to complete, but sample 4 again stopped at
`resident-prefetch-yield-load`. The run therefore remains rejected.

The completed rows are useful diagnostics only:

| Mode | Complete samples | Partial median cycles | Cycles/request |
| --- | ---: | ---: | ---: |
| Linux threads demand | 4 | 684,291 | 83.53 |
| Batched prefetch/load | 4 | 826,605.5 | 100.90 |
| Hardware demand handoff | 4 | 610,788.5 | 74.56 |
| Hardware prefetch/handoff | 3 | 619,992 | 75.68 |

On these incomplete rows, hardware demand is 1.120x and hardware prefetch is
1.104x faster than the Linux-thread median. These are not paper speedups: mode
sample counts differ and the required seven-sample benchmark does not complete.
Prefetch is also slightly slower than the hardware demand control in the
completed subset.

## Implication

The result narrows the integration risk. Direct user-mode switching, ready-word
selection, ordinary hardware-demand handoffs, checksums, Linux entry, and the
ten-context register encoding all work. The failure requires sustained
`prefetch.r` plus immediate hardware handoff under a cold/displaced cache state.
A few demand reads postpone it but do not make it lifecycle-safe.

The fifth prefetch invocation in the bounded-prime run is consistent with
finite hint/cache state accumulating between launches; with ten side-buffer
entries, roughly two unreclaimed entries per launch is one possible model. That
occupancy was not directly observed, so it remains a hypothesis. The next RTL
experiment should expose or trace D-cache side-buffer valid bits, UCE prefetch
slot validity, matching-demand joins, and ordinary fallback requests across at
least five complete launches. Until that passes, the project should not claim
an integrated Linux hardware-group application speedup or that the prefetch
runtime makes Linux scheduling redundant end to end.

`analyze.py` regenerates `analysis.json`, checks every stated control outcome,
and labels the partial timing summaries as incomplete. `request_benchmark.c`
now supports an explicit mode mask and optional hardware launch-read count;
both default to the original behavior when omitted.
