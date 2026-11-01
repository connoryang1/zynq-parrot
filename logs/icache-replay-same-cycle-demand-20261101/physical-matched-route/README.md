This directory preserves the recovery-qualified FPGA/Linux comparison of the corrected replay RTL against its disabled mode. It uses the exact timing-clean four-context bitstream and immutable futex-v1 benchmark artifacts declared in the parent evidence record; results are accepted only after all four opposite-order fresh-boot arms and the strict analyzer pass.

# Matched corrected-RTL FPGA comparison

All four accepted arms completed on fresh board boots in the predeclared
enabled-disabled / disabled-enabled orders. Each status binds 201 samples, the
exact NBF, ELF, transfer, control program, and routed bitstream, and ends with
runner exit zero plus guest/host pass markers. The analyzer discards one
warmup per arm and compares 200 samples per arm per replicate.

The strict result is:

| replicate | enabled median | disabled median | enabled - disabled | reduction |
| --- | ---: | ---: | ---: | ---: |
| enabled then disabled | 18,705.5 | 19,212.5 | -507 | 2.639% |
| disabled then enabled | 18,447.0 | 19,381.0 | -934 | 4.819% |
| pooled, 400 samples/arm | 18,594.5 | 19,250.5 | -656 | 3.408% |

The fresh-boot-stratified estimand, the mean of the two within-replicate median
differences, is -720.5 cycles. Its 100,000-resample IID bootstrap 95% interval
is `[-930.25, -478.5]` cycles and its 20,000-resample circular block bootstrap
interval, using blocks of ten, is `[-937.5, -485.75]`; the latter puts 99.995%
of resamples on enabled being faster. The complete machine-readable result is
`analysis.json` (SHA-256
`1b6a7eb359d553d9eaa2f62483f17d8710922048d42dce30c5965d67e01b34c9`).

The enabled arms have median recorded instruction-miss counts of 182.5 and
182, versus 198 and 197 disabled. None of the configured prefix lines appears
as an architectural instruction demand in either enabled arm, while thirteen
appear in each disabled arm. The 256-entry instruction recorder overflows in
48--61 of 200 analyzed samples, so those counts are censored telemetry rather
than complete traffic totals. They establish that replay is active and shifts
instruction demand, but they do not observe either new drop predicate. The
3.408% result therefore belongs to the complete corrected RTL checkpoint; it
must not be attributed specifically to the resident-overtake or same-edge fix.

This is an instruction-prefix, persistent pinned-pair futex best case. It is a
reduction in the measured `to-peer` handoff interval, not whole-application or
general Linux throughput, and it does not yet include the independent data
preview path.

The first attempt at the fourth arm did not reach the guest shell. Linux boot
ended after `Starting network: OK` with control-program reporting `Errant write
to 1dbd18`; the host then exited cleanly with `BSG PASS`, but no benchmark
samples were issued and the capture status is `FAIL`. The raw attempt is
preserved as `rep2-enabled-boot-failure.log` with its status sidecar. Its cause
is not established; it is excluded from the comparison. The board was then
power-cycled, brought through the full readiness gate, restaged, hash-checked,
and reloaded. The replacement `rep2-enabled.log` completed all 201 samples and
all terminal gates and is the only fourth-arm input to `analysis.json`.
