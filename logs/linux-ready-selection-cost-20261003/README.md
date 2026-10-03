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
