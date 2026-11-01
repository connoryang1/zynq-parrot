This simulator-only diagnostic explains why the initial C++ coroutine control
plateaus near 98 cycles per useful node. It compares scheduler implementations
without changing RTL or using the FPGA, and keeps every accepted transcript and
hash needed to reproduce the conclusion.

# Coroutine scheduler discrepancy

All variants use the same synthetic 200-cycle pipelined AXI model, two physical
threads, ten logical contexts, ten detached-prefetch slots, and model SHA-256
`799c1dd29297e27312a070ea4a5f60f63d0d02c7d072862dc408fd179414ad78`.
They are implemented on diagnostic branch `experiment/nano-coro-overhead` at
commit `d9cf0c65`. Every retained row passes result, checksum, guest, core, and
host checks.

| Variant | N=5 cycles/node | N=9 cycles/node | Actor bytes |
| --- | ---: | ---: | ---: |
| Checked 10-entry queue | 98.055 accepted baseline | 100.061 same-source diagnostic | 410 |
| Checked 16-entry queue | 85.745 | 85.253 | 342 |
| Nishanov-style head/tail queue | 76.709 | 76.475 | 302 |
| Direct symmetric-transfer ring | 64.655 | 63.798 | 254 |
| Matched batch, exact direct-ring ELF | 81.000 | 59.758 | n/a |

The initial queue uses capacity ten. Each suspension performs two `% 10` index
updates, and RISC-V GCC lowers each to multiply/shift arithmetic. Changing only
the physical queue capacity to 16 makes both updates masks and reduces N=9 from
9,906 to 8,440 cycles. Nishanov's original scheduler uses a 256-entry queue and
only head/tail state; removing the hot-path count and overflow/underflow checks
reduces it further to 7,571 cycles. Direct transfer eliminates the queue and
reaches 6,316 cycles, only 6.8% behind the exact-binary N=9 batch at 5,916.

At N=5 the Nishanov-style queue takes 4,219 cycles versus batch at 4,455, a
5.3% coroutine advantage. Direct transfer takes 3,556, a 20.2% advantage,
close to Nishanov's reported 24.4% coroutine advantage over his state machine.
The original ordering discrepancy is therefore scheduler implementation, not
failed latency hiding or inherent compiler-coroutine cost.

`-O2 -flto` leaves the 410-byte queue actor unchanged and measures 9,914 cycles
at N=9 versus 9,906 without LTO. A first plain `-O3` build was rejected because
function cloning duplicated the benchmark's global assembly load labels; it was
not run or interpreted. This is a benchmark-label compatibility issue, not an
optimization result.

Executable SHA-256 values are:

- checked queue: `9fbd22c60e5acf6bf5ffd11bce713606e584e92ebd531658b60ffe1d9c86bf01`
- checked queue with LTO: `bce469449d970882473397647670d31b67b40eb4e6a9dc0ab6aeb73a7aef2d6e`
- checked 16-entry queue: `0be4d9a62ce4b0eb1ffe4fd0294d55e80ea0dc0a018a96b804eacffd79bbdc5c`
- Nishanov-style queue: `8166e57a54512e2ca56314db8cac4b9b5563bb3549ef5db27326a7ba8c9d8322`
- direct ring: `88d6ef9e0861b6786285455647a9400c8dbee2ec8e0b829a0c0adfc6ca635041`

The direct-ring and alternate queues remain diagnostics rather than replacing
the accepted comparison. A production change should choose the safety contract,
rerun the complete 2--10 sweep, and retain a trace-qualified request/consume
check before changing the headline hardware/coroutine ratio.
