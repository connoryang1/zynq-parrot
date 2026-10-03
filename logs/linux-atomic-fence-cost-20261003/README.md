# Atomic ready-selector cost

This experiment asks whether hardware-managed scheduling still fits the
paper's projected 15--25-cycle fast path. The first sequence atomically
exchanges one known ready peer with the source context, finds that peer, and
switches to it:

```text
amoswap.d.aqrl -> ctz -> CSR 0x800
```

This is a one-ready-peer mailbox. Because `amoswap` replaces the whole word, it
does not preserve additional runnable bits and is not by itself a general
ready-bitmap scheduler. The conservative comparison inserts `fence rw,rw`
between the AMO and `ctz`.
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

## One-ready-peer resident versus nonresident decomposition

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

## General multi-ready selector

A second benchmark uses an LR/SC update that selects the lowest runnable
context, clears only that target bit, adds the source context, and preserves all
other runnable bits before switching. Context 3 remains ready as a spectator
through every handoff, so the final word must be `0xa` for resident peer 1 or
`0xc` for nonresident peer 2. Each sample also counts SC retries independently
in the source and peer contexts.

```text
lr.d.aq -> ctz -> clear selected bit -> add source bit -> sc.d.rl -> CSR 0x800
```

| Peer state | FPGA cycles/handoff | FPGA range | Simulator | Over mailbox | Over direct switch |
| --- | ---: | ---: | ---: | ---: | ---: |
| Resident | 17.03 | 17.03--17.06 | 17.04 | 2.97 | 11.91 |
| Nonresident | 22.03 | 22.03--22.06 | 22.05 | 3.99 | 12.87 |

Both physical NBFs produce all 16 rows, preserve the spectator bit in every
row, observe the requested peer and return source, record zero SC retries, and
finish with the custom pass marker, `CORE[0] PASS`, and runner exit zero. This
is the paper-safe general-group result. It stays within the projected 25-cycle
budget without new scheduler hardware. At 18 MHz it takes about 0.946
microseconds resident or 1.224 microseconds nonresident. The latter is still
249--254 times smaller than the measured Linux same-address-space handoff.

The zero-retry result covers the intended uncontended single-pipeline handoff.
It does not measure interference from another core writing the same ready word.
A fused select-and-switch instruction could target the measured 11.9--12.9
cycles above direct dispatch, while a third resident register bank would remove
about five cycles from the general nonresident path.

## Fair three-context round robin

Selecting the lowest ready bit is correct but is not fair: a repeatedly
runnable low-numbered context can starve a higher-numbered one. A third
benchmark therefore rotates the ready bitmap past the current context before
`ctz`, then uses the same LR/SC update to claim the selected context and return
the source bit. With ready contexts 1 and 3, it must repeatedly execute the
order `0 -> 1 -> 3 -> 0`. Each timed sample contains 386 handoffs; contexts 1
and 3 each complete 128 scheduler iterations and set their completion bits.

```text
lr.d.aq -> read source -> rotate ready word -> ctz -> clear target
        -> add source -> sc.d.rl -> CSR 0x800
```

| Platform | Parseable steady samples | Median cycles/handoff | Range |
| --- | ---: | ---: | ---: |
| Simulator | 11 | 26.60 | 26.58--26.67 |
| FPGA | 15 | 26.59 | 26.58--26.64 |

All 16 physical samples have the expected `0xa` ready and completion words,
return to context 0, record zero SC retries in contexts 0, 1, and 3, and finish
with the custom pass marker, `CORE[0] PASS`, and runner exit zero. Four simulator
rows were split by heartbeat text; every complete row passes the same checks,
and the simulator and FPGA medians differ by 0.01 cycle.

Fair round-robin policy costs 4.56 cycles beyond the closest fixed-priority
nonresident result of 22.03 cycles. It is 1.59 cycles above the projected
25-cycle group-decision budget, or 1.477 microseconds at 18 MHz, while remaining
206.7--210.4 times smaller than the measured Linux handoff. Thus general
selection is already practical in software, but a fused fair-select-and-switch
instruction is justified if 25 cycles is a hard architectural target. This
comparison combines changed selection policy with a continuously rotating
three-context schedule; it is not an instruction-by-instruction attribution of
the 4.56-cycle difference.

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
dd30d203b8c7d85506265e751b6a77f8b231bd1e24b4210622c2098e4d8c8b36  mt_atomic_multiready_selector_benchmark.c
2e8fbe15948284c3a77d0252fcb664cf26eb46e1f93c076d4040423d1c7ce18a  mt_atomic_multiready_resident_benchmark_fpga.riscv
99ccc25c57c7d5b5728018a548ae0daff6f29af89f7aecbff8172b6e7ac6cbf0  mt_atomic_multiready_resident_benchmark_fpga.nbf
0581a8cbcc07d16d95f53fa15695936b04c20757b02f6b211c725bb3e92db1ab  mt_atomic_multiready_nonresident_benchmark_fpga.riscv
1dd073113f4671d22435450e20a2732897156903264a71e41c1f8cceff10c3fd  mt_atomic_multiready_nonresident_benchmark_fpga.nbf
84c824187fd19ad7fc947137ab2fc6529cc745f56cb22677c47d9668283fbdd7  multiready-resident-physical.log
f6c3e37e79b7e364e67a475afcdde00f7319ce581f4fb1854ef076b287d4f2db  multiready-nonresident-physical.log
0ca4e607f6c3682f2da3a949e9f1039e22eb7e3d082a58e6cda85bcb0509280c  analyze_atomic_selector.py
139be42351bf81f5d6f75a9e6fd824fb187021f318605e718c058c0da02319c3  analysis.json
ee40d2b976beb6f63c3c2b10c4051d577a7e4fd3828468240277d5126bd2c9a1  atomic_fence_cost
bbd804800b68125cb7abf1996cfd4a217f5528cc26ecad3930bb255b9719061c  atomic_fence_cost.c
b0b5ae35d3d4741c6855a58cb238457a80798482a35f9f0463640625cf781100  mt_atomic_round_robin_selector_benchmark.c
fcc2902fcc915cd4512980e654ac7256ac31e42bd4450ebdc83f8ec915e63b00  mt_atomic_round_robin_selector_benchmark.riscv
be5f15bba4262026b9fa54da65d3a2ce484a0dc54caa16ff5eba64c1ab79cc7d  mt_atomic_round_robin_selector_benchmark_fpga.riscv
a075e9440ff17e2c8783a0c8579707fe63bb55aa9b10e1533daa73def478bdc5  mt_atomic_round_robin_selector_benchmark_fpga.nbf
b83e6dfe393eb47f13d43159c4e9bf470f33101d0bb693194707e0158e60bd0e  roundrobin-sim-run.log
5d23b4425782cd31ace842288c55abc4eb3965898a8cc98c15dcac63d9ab8304  roundrobin-physical.log
d350ee6692dfde8810254860a053b5b21bff83809916caccadb41b277de6eb11  roundrobin-sim-disassembly.txt
f6aa8d655166fa830d9dd0732575f8d8382387625a28d3d7a463fbf6b6e11fa7  roundrobin-physical-disassembly.txt
e1f54f97499479b35f33293847c08b364c6401119d4d6068a9d8f8b7f6b83918  roundrobin-physical-status.json
e55b612fb71f4c8dc86f10de3bb8195b78a0705ceb8eecb70e85649be995f1a1  run_physical_roundrobin.py
```
