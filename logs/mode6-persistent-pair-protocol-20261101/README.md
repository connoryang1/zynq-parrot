This directory records the protocol for measuring steady-state mode-6 instruction replay with one persistent Linux task pair. It exists to keep that production-like retained-buffer question separate from the per-trial `fence.i` experiment, which measures a deliberately cold first-switch mechanism ceiling. No new FPGA performance result is claimed here.

# Mode-6 persistent-pair protocol

## Why this experiment is distinct

The historical old-16 result in RL-063 is a valid separate-boot A/B and improves the persistent-pair median by 637.5 cycles, or 3.25%. The current exact mode-6 NBF instead contains a newly trained 16-line post-wakeup table beginning at `0x80a13840`; it is not the old-16 table beginning at `0x8023d480`. The current table therefore needs its own steady-state measurement rather than inheriting the historical percentage.

The isolated physical benchmark clears completed replay lines with a symmetric `fence.i` before every trial. That is the correct arm-isolation mechanism for a cold trigger test, but it deliberately removes the hardware's persistent 16-line-buffer behavior. This protocol uses a fresh boot for every arm, discards the first handoff as warmup, and retains the next 200 handoffs from one pinned futex pair.

## Matched control

Both threads register the same harmless shared user page because the current kernel requires physical-preview registration before any nonzero preview mode. Modes five and six never issue that registered data address. Both arms use the same exact NBF and benchmark ELF; the only runtime difference is mode zero (`disabled`) versus mode six (`wake-trigger`) on both tasks.

The benchmark records the source-to-peer window with summary-only miss counts. Recorder overflow is explicitly permitted because the elapsed endpoint remains valid; invalid recorder state remains fatal. A final `TRACE_CAPTURE_PASS` marker replaces the historical `|| true` shell escape.

## Exact prepared artifacts

- Routed bitstream SHA-256: `e97e0517d08771753e2eae96c6af95380944e5a8e2aefa0115da898b7be12381`
- Current mode-6 prefix-16 NBF SHA-256: `5e42c2f6c801d71506a3c6fc5e708aa01c0e6a46996fc72bc64236135565d2bd`
- Control-program SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- Prepared benchmark ELF SHA-256: `91f0db111470e9f3fd1a53bfd9b8d7b4404ffe8e20a792e4caa99171bbc1c0cf`
- Prepared transfer SHA-256: `b5103c89b270f5cdcee8156de0a0a6d8b98ca32ecbba7de77e5cc11a6f0f5518`
- Compiler: `/home/jhumphri/black-parrot-sdk/linux/work/buildroot/host/bin/riscv64-linux-gcc`

The ELF disassembly contains `configure_preview` calls in both `main` and `peer_main`, and the main-thread release follows `pthread_join`. The generated guest command for an enabled arm is:

```text
/tmp/cache_miss_trace_capture_dynamic --window to-peer --samples 201 --preview-mode wake-trigger --summary-only --allow-overflow --final-addresses
```

The disabled arm changes only `wake-trigger` to `disabled`.

The first local rebuild used the Makefile's unavailable default `riscv64-unknown-linux-gnu-gcc` name and stopped before producing a result. The confirmed cause was a missing `PATH` entry, not a source failure; all accepted rebuild commands pass the explicit Buildroot compiler path shown above. Future reproductions must keep that explicit toolchain argument.

## Acceptance design

Run two fresh-boot pairs in opposite order:

1. enabled, then disabled;
2. disabled, then enabled.

Every run must have exact hash matches, 201 consecutively numbered samples, explicit preview-mode and final capture markers, runner exit zero, and CORE/BSG PASS. Only after the final timed endpoint, the benchmark reads the frozen miss recorder and prints its addresses; this cannot perturb an analyzed successor and distinguishes table mismatch from trigger-timing failure without another boot. `linux-tests/analyze_persistent_preview_ab.py` verifies the adjacent runner status and exact prefix JSON, reports configured lines demanded in that final capture, discards exactly sample one, reports per-replicate and pooled medians, and calculates both IID and circular ten-handoff block intervals for the mean of the two replicate-level median differences.

## Validation and current board state

The benchmark and serialized runner changes pass all 93 discovered `linux-tests` Python tests, including compressed-log analysis with an adjacent uncompressed-name status file. The RISC-V dynamic ELF and transfer rebuild to the hashes above. The board remains on the same operating-system boot that executed the prior guest shutdown (`2026-11-01 05:09:15`, uptime 6,220 seconds at the check), and this shell has no `PYNQ_POWER_STATE_URL`; no further FPGA launch is valid until a physical power cycle, PYNQ readiness wait, and exact overlay reload.
