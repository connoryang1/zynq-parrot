# Atomic ready-selector cost

This experiment asks whether a realistic hardware-managed scheduling handoff
still fits the paper's projected 15--25-cycle fast path.  Each timed operation
atomically claims a ready-context bitmap, finds the selected context, and
switches to it:

```text
amoswap.d.aqrl -> ctz -> CSR 0x800
```

The conservative comparison inserts `fence rw,rw` between the AMO and `ctz`.
`sim-disassembly.txt` confirms these are the only instructions that differ in
the measured loop.

## Accepted simulator result

The accepted simulator run uses top-level commit `facd5189cc4a4ede633fd10656f3246db503565d`
and BlackParrot commit `57302ca5b0ccd03d282a7cab798b9e7fbeb1664f` with two
resident and four logical contexts.  The ELF SHA-256 is
`d1835bea54027e3350f8347faf0c405a0f2e0a79cf9d130f235f825f2760d4f3`.

Sixteen alternating samples execute 128 round trips, or 258 context switches
per timed sample.  Excluding each mode's first cold sample, the complete rows
that were not split by the simulator heartbeat give:

| Sequence | Parseable steady samples | Median cycles/operation | Range |
| --- | ---: | ---: | ---: |
| `amoswap.aqrl; ctz; csrw` | 12 | 18.06 | 18.06--18.12 |
| `amoswap.aqrl; fence rw,rw; ctz; csrw` | 12 | 19.07 | 19.04--19.10 |

The full fence costs about 1.01 cycles per operation, or 5.6% relative to the
unfenced atomic selector.  The benchmark itself validates every one of the 32
samples before printing `[BSG-PASS] atomic fence cost`: context 2 executed,
the peer completed, the ready word became context-2's bit, and the source
returned to context 0.  Six otherwise valid rows were split by asynchronous
heartbeat text, so they are omitted from the table rather than reconstructed.
`CORE PASS` and the custom pass marker are both present.  The later Verilator
DPI final-block abort is the known teardown artifact after successful core and
host completion.

## Accepted FPGA result

The physical run uses the routed ten-context image at the same RTL revision.
Its bitstream SHA-256 is
`9704dd6e0265654adbca272a08a3aae0830bef1893716c6ce25ed80bf2f55ccf`.
The physical program was rebuilt for the endpoint's four-bit context ID using
the reviewed integer FPGA CRT, `BP_FPGA_PROGRAM`, `-nostartfiles`, and the NBF
configuration/debug preamble. The runner, ELF, and NBF SHA-256 values are:

```text
be771785b8eb343fbaac2f5c5610437a764c7ff92413f20b26235969aab3616e  control-program
c56d585b20332b9f0d4e85cf0b56948d7d0398f6f344ebf880e7de830fd22694  mt_atomic_fence_cost_benchmark_fpga.riscv
f1846cb06071020af349d2b8f9487005e444f38f3132c5fbf23debab12dfbe7d  mt_atomic_fence_cost_benchmark_fpga.nbf
```

All 32 physical samples are parseable and pass the five per-trial checks. The
custom `[BSG-PASS] atomic fence cost`, `CORE[0] PASS`, and runner exit zero are
present.

| Sequence | Steady samples | FPGA median cycles/operation | FPGA range | Simulator median |
| --- | ---: | ---: | ---: | ---: |
| `amoswap.aqrl; ctz; csrw` | 15 | 18.04 | 18.04--18.09 | 18.06 |
| `amoswap.aqrl; fence rw,rw; ctz; csrw` | 15 | 19.06 | 19.06--19.07 | 19.07 |

The physical full fence costs 1.02 cycles per operation, or 5.65% relative to
the atomic selector. At the routed image's 18 MHz clock, 18.04 cycles is about
1.002 microseconds. Compared with the measured 5,496--5,595-cycle Linux
same-address-space handoff, the complete atomic selection mechanism is
304.7--310.1 times smaller. It is 8.88 cycles above the separately measured
9.16-cycle direct nonresident handoff, which quantifies the ready-word atomic,
selection, and loop cost instead of assuming that policy is free.

## Resident versus nonresident decomposition

The same experiment was repeated with context 1, the other resident register
bank, instead of nonresident context 2. The instruction sequence, 128-round-trip
sample size, alternating fence order, FPGA image, and five correctness checks
are unchanged. All 32 resident FPGA samples pass before
`[BSG-PASS] atomic resident selector`, `CORE[0] PASS`, and runner exit zero.

| Peer state | Atomic scheduler | With full fence | Direct register-target switch | Selection over direct |
| --- | ---: | ---: | ---: | ---: |
| Resident | 14.06 | 15.08 | 5.125 | 8.94 |
| Nonresident | 18.04 | 19.06 | 9.164 | 8.88 |

The complete atomic scheduler's nonresident premium is 3.98 cycles. The
separately measured direct register-target switch has a 4.04-cycle nonresident
premium. Their 0.06-cycle difference is 1.5% of the roughly four-cycle
residency penalty. Thus the evidence supports a simple additive decomposition:
ready-word claim and selection cost about 8.9
cycles regardless of residency, while moving a nonresident context adds about
4.0 cycles. The FPGA resident result is 14.06 cycles versus 14.05 in simulation;
the FPGA nonresident result is 18.04 versus 18.06 in simulation.

For an ordinary coherent ready word, the AMO's acquire/release ordering is the
relevant publication and claim primitive.  This result does not justify
removing fences needed for unrelated MMIO or device ordering.

## Rejected and incomplete runs

The first simulator run used a stale `prog.riscv`/`prog.nbf`, whose peer context
lacked a valid initialized global pointer.  It produced stable timing but ended
with the custom failure marker and is rejected.  Rebuilding all run collateral
from the corrected ELF produced the accepted result above.

The physical Linux multisample attempt completed both warmups and then stalled
while reseeding context 2 before the first measured row.  A reduced two-trial
attempt never reached the benchmark because the board's management SSH session
closed during the runner's DRAM initialization. Subsequent direct NBF attempts
were also rejected before measurement when the board had its post-power-cycle
default overlay or when the program used simulator startup collateral. These
failures are lifecycle and infrastructure evidence only. The corrected FPGA-CRT
run above is the accepted physical mechanism measurement; an in-Linux
integration measurement remains separate work.

## Artifact hashes

```text
d1835bea54027e3350f8347faf0c405a0f2e0a79cf9d130f235f825f2760d4f3  mt_atomic_fence_cost_benchmark.riscv
e1232cb371cc5f449ccc275daaad9bf5cd4d6228b3d3e21fb35c15348b02f66e  mt_atomic_fence_cost_benchmark_sim.c
76e51984c4c8681cd18f5c942ab2b0482657777b31a44ce473fbfa41546a4086  mt_atomic_fence_cost_benchmark.c
05a0105f38ab7344a93c1b0a7ebea8688aa14a9101f27c691b7130df12cf65ac  sim-run-accepted.log
c9758f777822e2e5a6a1c7074ef1e23d97a4482294ec95be43ad56b9aab086c9  sim-disassembly.txt
c56d585b20332b9f0d4e85cf0b56948d7d0398f6f344ebf880e7de830fd22694  mt_atomic_fence_cost_benchmark_fpga.riscv
f1846cb06071020af349d2b8f9487005e444f38f3132c5fbf23debab12dfbe7d  mt_atomic_fence_cost_benchmark_fpga.nbf
04333c882c4b84d5204b68c87157c4561aa4e155312716745426b9010bf2c9e9  physical-baremetal.log
efae3a82b6edefc049e65f2c71e7744435e927415d496d7907d299cc37938cc0  physical-disassembly.txt
3b27da23615ff0dac42f00d8065f490d91091edd5ffc300dfed5763e4d8f4eee  mt_atomic_resident_selector_benchmark.c
9a46e7440cf592e84bd10980451d3dc5a1a4ae623eb27017d0d0ab689a1b42e0  mt_atomic_resident_selector_benchmark.riscv
8d5551b8d93a861cd3b2842f471cc48df1e5a5593a727f10e1afb31566c9d7c3  resident-sim-run.log
14043100ca59a5873f88f723a01fcb44ac4e88f1b1805cad933aa81558be5f4e  mt_atomic_resident_selector_benchmark_fpga.riscv
9cbcf311e8e3b91dfcdc396ee20b2e1e938e8c61420d506ca7fe31e5dda3dd37  mt_atomic_resident_selector_benchmark_fpga.nbf
cb9d3124a86cca832762196da4f3997de4603e53f2f5748fdbc927084452b33b  resident-physical.log
72b25e7732569884c3802b281fa4732b0320b932c2512e08b1a3cf180aa6174f  analyze_atomic_selector.py
bffc7ac870f48941c8acdd4ad7a5b3c5d8df98484eb784f25532d5ed68fb852c  analysis.json
ee40d2b976beb6f63c3c2b10c4051d577a7e4fd3828468240277d5126bd2c9a1  atomic_fence_cost
bbd804800b68125cb7abf1996cfd4a217f5528cc26ecad3930bb255b9719061c  atomic_fence_cost.c
```
