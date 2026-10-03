This experiment measures whether choosing a BlackParrot hardware context through a register makes user-mode handoff materially slower than using a compile-time immediate context ID. It isolates the dispatch instruction needed by a runtime scheduler from the separate software cost of finding a ready context.

# Dynamic context-target cost

The exact image is top `680cdf149f003a808bb9322c334f1d039af89a66`, BlackParrot `518d2fca78d5cf6aaa68af717e2a3b2ba7be936f`, and bitstream SHA-256 `b8742813c52ac980eca34a2eaab4779adac605e3c90bf7c3819f1cd162460de4`. The Linux shell NBF SHA-256 is `af22d24ff969cac6d639f98542ff3a48778e19c4f0ba8f3c4218bf7e023f2bd3`; the probe ELF SHA-256 is `9b6137caf0cbf37f45f43d94245ec6ce3701b3ea6f82bb2dd4ce16abc2243ddd`.

Each of four modes ran 128 aggregates of 256 handoffs, for 131,072 timed handoffs total. The immediate and register forms use otherwise matched unrolled rings. Disassembly confirms 64 static source-ring `csrw 0x800,t1` instructions across the resident and nonresident dynamic functions and 32 peer-ring `csrw 0x800,t4` instructions; their four-iteration loops execute 128 handoffs on each side per aggregate.

| Target form | Resident cycles/handoff | Nonresident cycles/handoff |
| --- | ---: | ---: |
| Immediate CSR target | 5.098 | 9.141 |
| Register CSR target | 5.125 | 9.164 |
| Register minus immediate | +0.027 | +0.023 |
| Relative overhead | 0.54% | 0.26% |

The register-target form therefore retains essentially the full direct-handoff advantage. Against the separately measured 5,496–5,595-cycle Linux same-mm handoff, the runtime-compatible register instruction remains approximately 1,073–1,092× lower latency when resident and 600–611× lower when nonresident.

One immediate-resident and one register-resident aggregate had a large outlier, consistent with asynchronous Linux work; this run did not trace the interrupts. All remaining resident aggregates and every nonresident aggregate form tight clusters, and the median comparison is unaffected.

The target ID was loaded into a general-purpose register before each timed ring. This measurement does not include scanning a ready bitmap, dequeuing a runnable context, checking ownership, or recording wait/wakeup state. Those software-policy operations are now the relevant fast-path overhead to measure; the dynamic hardware dispatch itself is not a limiting factor.

The run passed endpoint-aware target-register seeding, source and peer register checks, completion counts, peer Linux syscalls, guest ELF hash, native exit zero, and `CORE[0] PASS`. The guest and physical FPGA were powered off after evidence collection.
