# Banyan Parity Status

This document compares the current resident hardware-thread work against the
Banyan model described in "Banyan: A New Hardware Threading Model".

## Summary

The current branch implements the core resident-context substrate: a CTXT CSR
switch path, per-context integer and floating-point register state, per-context
CSR instances, saved resume state, per-context BTB/BHT instances, and ASID-aware
TLB tags. This is enough to validate Banyan-style fast resident switching.

The remaining gaps are mostly validation and system integration:

- cross-privilege and SATP/ASID behavior needs targeted tests
- BTB/BHT are per-thread, but RAS and global history still need explicit
  characterization
- full distinct virtual-address-space switching has not yet been proven by a
  page-table remapping test
- monitor/mwait, thread descriptor tables, Linux scheduler integration, and
  cache-backed context eviction are future work

## Feature Matrix

| Banyan feature | Current status | Evidence / next action |
| --- | --- | --- |
| CTXT CSR switch (`0x081`) | Implemented | Tested by smoke, ring, throughput, and Banyan-style benchmarks. |
| Per-context integer register file | Implemented | `mt_regfile_test`, ABI preservation, GPR ring stress. |
| Per-context floating-point register file | Implemented | `mt_frf_isolation_test`. |
| Per-context CSR file | Implemented | `mt_csr_isolation_test`; wrapper instantiates one CSR file per context. |
| Per-context resume PC | Implemented | `0x082` seeding and ring/round-trip tests. |
| Different privilege modes per context | Under-tested | `mt_ctxtsw_privilege_isolation_test` validates privilege-control CSR ownership; full S/U-mode switch/resume remains future validation. |
| Different address spaces / ASIDs | Implemented but under-tested | `mt_ctxtsw_asid_translation_test` validates SATP/ASID ownership; full virtual remap test remains future work. |
| ASID-tagged TLB entries | Implemented | TLB tags include ASID; FE shadow ASID updates on context switch. |
| Per-context BTB/BHT | Implemented | `bp_fe_pc_gen.sv` instantiates per-thread BTB/BHT; benchmark coverage exists. |
| RAS isolation | Under-tested / likely shared | `mt_ctxtsw_return_predictor_test` characterizes return-path pollution. |
| Global history isolation | Under-tested / likely shared | `mt_ctxtsw_predictor_pollution` characterizes branch-history pollution. |
| `rpush` / `rpull` instructions | Partial | CSR `0x083` provides remote integer/FP register writes; no true instruction pair yet. |
| Monitor/mwait | Not implemented | Future fast-I/O and wakeup work. |
| Thread descriptor table | Not implemented | Future software-visible context management work. |
| Linux / ghOSt integration | Not implemented | Future system software work after resident substrate is stable. |
| Cache-backed context eviction | Not implemented | Future scaling work after resident-context parity is validated. |
| Current synthesis/PPA comparison | Not current | Future area/fmax sweep after correctness is stable. |

## Reporting Guidance

Keep performance claims separated:

- resident hardware handoff latency from waveform endpoints
- software benchmark throughput or round-trip timing
- Banyan paper comparison points such as `~7` cycle switch and `~139` cycle
  poller/worker round trip

Do not claim full Banyan parity until privilege, ASID/SATP, predictor, and
exception/resume behavior have all passed targeted validation.
