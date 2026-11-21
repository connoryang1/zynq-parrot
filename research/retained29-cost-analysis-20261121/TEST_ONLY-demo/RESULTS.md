TEST ONLY — synthetic, no physical admission. This reports the fixed complete-COST cohort estimator and preserves all raw paired costs. Joint15 WHOLE is primary; I9/D6 are diagnostics and steady timing is secondary.

Joint15 WHOLE on/off geometric ratio: **1.000000000** (cost change **+0.000000%**).
Each configuration has three independent workload boots; rows below show their actual estimates and range, not confidence intervals.

| Workload | KiB | Three boot WHOLE ratios | Declared GM | Boot min–max |
| --- | ---: | --- | ---: | --- |
| scan | 32 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| scan | 128 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| lookup | 32 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| lookup | 128 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| parse | 32 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| parse | 128 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| chase | 32 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| chase | 128 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| regex | 32 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |
| regex | 128 | 1.000000000, 1.000000000, 1.000000000 | 1.000000000 | 1.000000000–1.000000000 |

| Policy | Endpoint | Role | Equal-ten ratio |
| --- | --- | --- | ---: |
| ordinary-i | whole | diagnostic | 0.500000000 |
| ordinary-i | steady | secondary | 0.500000000 |
| ordinary-d | whole | diagnostic | 2.000000000 |
| ordinary-d | steady | secondary | 2.000000000 |
| ordinary-joint | whole | primary | 1.000000000 |
| ordinary-joint | steady | secondary | 1.000000000 |

A ratio below one means fewer on cycles; neutral and regressing configurations remain included. The hierarchy is four paired repeat ratios per boot, three boots per configuration, then equal weight across ten workload × size configurations. Boot clusters retain both footprints and all masks; raw on/off cycles, resources and order are in CSV/JSON.

This estimates incremental demand-retention activation/lifecycle cost on one hardware image. Common maintenance and ordinary fences remain; crossover cache/allocator carryover is retained. Old2dd observes no per-application retained hits or occupancy. Declared control writes are source telemetry; no advisory-prefetch, controller-absent or simulation-to-FPGA claim follows.

Complete-gate SHA: `TEST_ONLY-no-physical-admission`. Full input/source/run identities are bound in `analysis.json` and `manifest.json`.
