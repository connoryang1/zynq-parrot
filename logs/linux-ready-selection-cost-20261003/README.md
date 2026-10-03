# Ready-target selection cost

This experiment isolates the cost of choosing a context before the context-switch CSR. Each result covers 256 hardware handoffs in the two-resident-slot, four-logical-context simulator.

| Target source | Resident cycles/handoff | Nonresident cycles/handoff |
| --- | ---: | ---: |
| Target already in a register | 5.156 | 9.160 |
| Hot memory word containing target | 10.168 | 14.117 |
| Hot ready bitmap, `load; ctz; csrw` | 11.125 | 15.137 |

Loading the target adds 5.012 resident cycles or 4.957 nonresident cycles. Applying `ctz` to the loaded ready bitmap adds only 0.957 or 1.020 more cycles. The complete hot-bitmap selector therefore adds almost exactly six cycles to either form of switch.

Relative to the measured 5,496-cycle same-address-space Linux handoff, ready-bitmap selection plus switching is 494x faster for a resident target and 363x faster for a nonresident target. This comparison isolates scheduling/handoff machinery; it is not an end-to-end application speedup.

The accepted run is `sim-run-gp-fixed.log`, SHA-256 `6b3197bd3845c59d7aa1bcb9f86ff628284e042972ebdc2159fd3bac28ceebd1`. It reached `CORE PASS` and `BSG PASS`; the subsequent DPI final-block failure is the established simulator teardown artifact. The ELF and NBF hashes are recorded in `sim-analysis.json`.

Earlier simulator attempts in this directory are invalid. One reused a stale NBF. Two later attempts omitted the peer context's global pointer, so linker-relaxed GP-relative result accesses faulted after the handoff loop. The accepted benchmark seeds the peer GP and byte-matches the intended ELF before NBF generation.


## FPGA qualification and dependency localization

The exact routed image passed CTZ arithmetic independently, but the no-NOP Linux ready-bitmap ring stalled at the first bitmap mode. The original Linux binary also exposed a separate compiler issue: without `-ffixed-s11`, GCC reused the benchmark's state sentinel register. `build-linux.sh` records the corrected reproducible flags.

Three controlled FPGA variants localize the remaining hardware dependency:

| Sequence | Result |
| --- | --- |
| `load; ctz; csrw` | stalls at resident bitmap mode |
| `load; nop; ctz; csrw` | stalls at resident bitmap mode |
| ready register `ctz; csrw` | stalls at resident bitmap mode |
| `load; ctz; nop; csrw` | **PASS**, all six modes and state checks |

Thus neither CTZ arithmetic nor the load-to-CTZ dependency is faulty. The early context-switch target read sees a CTZ destination one cycle before it is safe. The verified one-NOP sequence measures the same useful medians as simulation within rounding:

| Target source | Resident cycles/handoff | Nonresident cycles/handoff |
| --- | ---: | ---: |
| Register | 5.14 | 9.16 |
| Hot loaded target | 10.12 | 14.15 |
| Ready bitmap with safe CTZ spacing | 11.12 | 15.13 |

The accepted FPGA workaround binary is `variants/nop-after-ctz/ready_selection_benchmark`, SHA-256 `ebc795e8e0e6f16c5692145f3b27126021cd6106ebd536c2304794f6df6ec8bd`. It passed guest hash verification, all timed rings and state checks, native exit zero, `CORE[0] PASS`, and runner exit zero. `variants/nop-after-load` and `variants/ctz-register-source` are negative localization controls and are not performance results.

The RTL candidate extends the existing computed-target dependency interlock with one lightweight tail stage (valid, thread ID, and register ID). The existing 46-case register-target simulator regression passes after this change. A newly routed no-NOP FPGA rerun remains the acceptance gate.
