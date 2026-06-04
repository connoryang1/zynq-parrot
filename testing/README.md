# Testing

This directory contains small bare-metal programs for validating and measuring
the BlackParrot resident context-switch work. Use the top-level test harness:

```bash
make -C testing help
make -C testing run-<test> TRACE=1
```

Run tests serially. The harness uses shared simulator/program artifacts under
`cosim/black-parrot-minimal-example/verilator`, including `prog.riscv`,
`prog.mem`, `prog.nbf`, and waveform output.

## Smoke Tests

- `mt_ctxtsw_smoke_test`: minimal T0->T1->T0 handoff sentinel. Use first when
  checking whether context switching still works at all.
- `mt_regfile_test`: basic remote seeding and integer register isolation across
  a T0/T1 switch.
- `mt_csr_isolation_test`: per-thread CSR state isolation using `mscratch`.
- `mt_frf_isolation_test`: per-thread floating-point register state isolation.
  It checks for non-aliasing and preservation, not reset-to-IEEE-zero, because
  FP register storage may use recoded values internally. This is also the
  current regression for the FE/I-cache duplicate-hit context-switch bug: the
  run resumes T0 at a halfword PC immediately after `csrw 0x081`, and the fixed
  I-cache must not feed a multi-hot instruction data select even if raw
  duplicate tag hits appear in the waveform.

## Correctness Tests

- `mt_abi_preservation_test`: verifies ABI-visible integer state, especially
  `gp` and callee-saved `s*` registers, survives a T0->T1->T0 switch.
- `mt_ctxtsw_asid_translation_test`: verifies per-context `satp`/ASID
  ownership across switch-out and resume. This is an ASID-state probe, not yet a
  full distinct virtual mapping test.
- `mt_ctxtsw_4ctx_ring_isolation`: checks CSR isolation across the default
  four-context ring, T0->T1->T2->T3->T0. It intentionally prints only after the
  ring completes, because pre-ring host MMIO stores can interact with the
  thread-body fences and turn this into a host-I/O ordering test.
- `mt_ctxtsw_gpr_ring_stress`: checks live GPR preservation across a full
  four-context ring.
- `mt_ctxtsw_late_wb_hazard_test`: regression for late writeback and
  wrong-thread scoreboard/hazard clearing around a context switch.
- `mt_ctxtsw_privilege_isolation_test`: validates per-context ownership of
  privilege-control CSRs such as `mstatus`, `mepc`, and `mscratch`. It is
  intentionally bounded and does not yet execute the switched context in S/U
  mode.
- `mt_ctxtsw_pure_ring_stress_test`: dense four-context ring with consecutive
  immediate context-switch CSRs and no loop bookkeeping in the switched stream.

## Benchmarks And Focused Probes

- `mt_ctxtsw_roundtrip_benchmark`: primary minimal T0->worker->T0 round-trip
  timing benchmark. Use this for the warm round-trip / single-switch estimate.
- `mt_ctxtsw_gap8_benchmark`: controlled-gap timing probe for the current
  context-switch performance investigation.
- `mt_ctxtsw_ring_throughput_benchmark`: primary steady-state ring throughput
  benchmark with loop bookkeeping amortized across multiple switches.
- `mt_ctxtsw_ring_overhead_benchmark`: compares dense ring switching against a
  no-switch control stream to estimate normalized added overhead.
- `mt_ctxtsw_single_overhead_benchmark`: measures one inserted context switch
  between hot straight-line instruction streams.
- `mt_ctxtsw_banyan_poll_worker_benchmark`: Banyan-style poller/worker
  comparison that includes shared-memory request/response and synthetic work.
- `mt_ctxtsw_predictor_pollution`: checks whether a switched-to context's
  branch pattern affects the resumed context's predictor behavior.
- `mt_ctxtsw_return_predictor_test`: characterizes call/return predictor timing
  before and after a switched-to context exercises a return-heavy call chain.

## Scale Tests

- `mt_ctxtsw_8ctx_ring_throughput_benchmark`: eight-context version of the ring
  throughput benchmark. Build the simulator with `make -C testing
  rebuild-sim-8ctx` before running it.
- `mt_ctxtsw_16ctx_ring_throughput_benchmark`,
  `mt_ctxtsw_32ctx_ring_throughput_benchmark`, and
  `mt_ctxtsw_64ctx_ring_throughput_benchmark`: parameterized scale variants of
  the same ring benchmark. Build the matching simulator first, for example
  `make -C testing rebuild-sim-16ctx TRACE=1`.

Scale benchmark knobs:

- `SCALE_SWITCHES`: measured switches per context. Use larger values for
  throughput reporting; small values are mostly smoke tests.
- `SCALE_WARMUP`: unmeasured switches per context before `rdcycle` timing.
  This warms the ring path and reduces cold-start inflation.
- `SCALE_UNROLL`: number of straight-line `csrw 0x081,next` operations per loop
  iteration. This trades loop bookkeeping against instruction footprint.

Recommended 16-context best-case throughput repro:

```bash
make -C testing rebuild-sim-16ctx TRACE=1
make -C testing run-mt_ctxtsw_16ctx_ring_throughput_benchmark \
  TRACE=1 SCALE_SWITCHES=256 SCALE_WARMUP=64 SCALE_UNROLL=8
```

On the 2026-06-03 traced 16-context model this reported `0x4a0e` cycles for
`16 * 256` switches, or about 4.63 cycles/switch. The benchmark prints this as
integer software throughput:

```text
Total cycles:         0x0000000000004a0e
Total switches:       0x0000000000001000
Measured throughput cyc/switch: 0x0000000000000004
Excess cycles over 4/switch: 0x0000000000000a0e
Expected TRACE hot first-instr dispatch: 0x0000000000000004
```

The throughput line is measured with `rdcycle` around the ring loop and includes
benchmark loop/control spacing. The exact ratio is `Total cycles / Total
switches`; for this run, `0x4a0e / 0x1000 = 18958 / 4096 = 4.63`. The excess
line shows how far the software throughput run is from an ideal 4-cycle-per-
switch total. The expected TRACE line is the hot hardware handoff metric to
verify from waveform analysis; it is not directly measured by the bare-metal
program.

For the hardware latency metric, convert or preserve the TRACE waveform and run:

```bash
python3 tools/ctxtsw_perf_report.py path/to/dump.vcd \
  --elf riscv/bp-tests/mt_ctxtsw_16ctx_ring_throughput_benchmark.riscv \
  --run-log cosim/black-parrot-minimal-example/verilator/run.log
```

The report auto-finds the first timed-loop `csrw 0x081` after `rdcycle` and
parses `Total cycles` from the run log. Use `d_first_instr_dispatch` as the
primary hardware metric: ctxtsw dispatch to first target-context instruction
dispatch. Use `d_next_ctxtsw` only for benchmark throughput, since it includes
loop/control instructions before the next `csrw 0x081`.

For FE/I-cache context-switch regressions, especially illegal-instruction
failures after a switch, also check the I-cache hit-select path:

```bash
python3 tools/ctxtsw_icache_select_scan.py path/to/dump.vcd \
  --fail-on-bad-select
```

This scanner reports raw duplicate hit samples separately from bad data-select
samples. Raw `hit_v_tv_r` can be multi-hot after an aborted miss/refill
sequence; the correctness condition is that `ld_data_way_select_tv` remains
one-hot on I-cache hit cycles. On the 2026-06-03 `mt_frf_isolation_test` TRACE
run, the scan observed 17 raw duplicate-hit samples and
`bad_data_select_on_hit=0`.

For D-cache UCE credit regressions, especially `counter underflow` messages
during scale runs, scan the D-cache UCE credit path:

```bash
python3 tools/dcache_uce_credit_scan.py path/to/dump.vcd \
  --min-cycle <cycle> --max-cycle <cycle>
```

This scanner flags the hardware underflow condition directly: a reverse final
beat accepted while the RTL credit count is zero and no same-cycle first
forward beat allocates credit. On the 2026-06-03 pre-fix 16-context throughput
waveform it reported one underflow at cycle 326917 in the old failing window;
on the fixed waveform the same window reports `rtl_underflows=0`.

Do not blindly increase `SCALE_UNROLL`. A same-day sweep with
`SCALE_SWITCHES=256` and `SCALE_WARMUP=64` measured:

| `SCALE_UNROLL` | cycles/switch | note |
| --- | ---: | --- |
| 4 | 5.26 | compact default, more loop bookkeeping |
| 8 | 4.65 | best measured point |
| 16 | 4.87 | still prints `4`, slightly slower than 8 |
| 32 | 6.38 | slower from frontend/I-cache footprint |
| 64 | 6.64 | slower from frontend/I-cache footprint |

Waveform evidence for the unroll-32 slowdown showed ctxtsw commit latency still
at 3 cycles, but FE queue latency stretched and the hot window included long
old-miss / target-miss gaps. The slowdown is therefore frontend footprint, not a
slower context-switch commit path.

## Demo

- `multithreading_demo`: older end-to-end demonstration of CSR `0x081`,
  `0x082`, and `0x083` thread seeding and switching. Keep it as a user-facing
  demo, not as the primary regression signal.

## Experimental Tests

- `mt_ctxtsw_sv39_asid_remap_test`: experimental repro for full SV39/ASID
  remap validation. It maps one virtual address to different physical pages in
  T0 and T1, then uses `mstatus.MPRV` with `MPP=S` for translated data access
  while keeping control flow in M-mode. As of 2026-06-01 it compiles but times
  out under `TRACE=1`; the run reaches the banner and then wedges before
  completing the first remap check. Keep it out of the normal correctness set
  until the DTLB/PTW/cache path is understood.

## Suggested Order

1. `mt_ctxtsw_smoke_test`
2. `mt_regfile_test`, `mt_csr_isolation_test`, `mt_frf_isolation_test`
3. `mt_ctxtsw_late_wb_hazard_test`
4. `mt_abi_preservation_test`, `mt_ctxtsw_4ctx_ring_isolation`,
   `mt_ctxtsw_gpr_ring_stress`
5. `mt_ctxtsw_roundtrip_benchmark`, `mt_ctxtsw_ring_throughput_benchmark`
6. Focused probes only when relevant to the change under test
