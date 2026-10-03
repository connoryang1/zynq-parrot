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

## Accepted result

The accepted run uses top-level commit `facd5189cc4a4ede633fd10656f3246db503565d`
and BlackParrot commit `57302ca5b0ccd03d282a7cab798b9e7fbeb1664f` with two
resident and four logical contexts.  The ELF SHA-256 is
`d1835bea54027e3350f8347faf0c405a0f2e0a79cf9d130f235f825f2760d4f3`.

Sixteen alternating samples execute 128 round trips, or 258 context switches
per timed sample.  Excluding each mode's first cold sample, the complete rows
that were not split by the simulator heartbeat give:

| Sequence | Parseable steady samples | Median cycles/operation | Range |
| --- | ---: | ---: | ---: |
| `amoswap.aqrl; ctz; csrw` | 12 | 18.06 | 18.06--18.12 |
| `amoswap.aqrl; fence rw,rw; ctz; csrw` | 11 | 19.07 | 19.04--19.10 |

The full fence costs about 1.01 cycles per operation, or 5.6% relative to the
unfenced atomic selector.  The benchmark itself validates every one of the 32
samples before printing `[BSG-PASS] atomic fence cost`: context 2 executed,
the peer completed, the ready word became context-2's bit, and the source
returned to context 0.  Seven otherwise valid rows were split by asynchronous
heartbeat text, so they are omitted from the table rather than reconstructed.
`CORE PASS` and the custom pass marker are both present.  The later Verilator
DPI final-block abort is the known teardown artifact after successful core and
host completion.

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
closed during the runner's DRAM initialization.  These logs are lifecycle and
infrastructure evidence only; no physical timing is claimed here.  A physical
confirmation remains pending once the board runner is stable.

## Artifact hashes

```text
d1835bea54027e3350f8347faf0c405a0f2e0a79cf9d130f235f825f2760d4f3  mt_atomic_fence_cost_benchmark.riscv
e1232cb371cc5f449ccc275daaad9bf5cd4d6228b3d3e21fb35c15348b02f66e  mt_atomic_fence_cost_benchmark.c
05a0105f38ab7344a93c1b0a7ebea8688aa14a9101f27c691b7130df12cf65ac  sim-run-accepted.log
c9758f777822e2e5a6a1c7074ef1e23d97a4482294ec95be43ad56b9aab086c9  sim-disassembly.txt
ee40d2b976beb6f63c3c2b10c4051d577a7e4fd3828468240277d5126bd2c9a1  atomic_fence_cost
bbd804800b68125cb7abf1996cfd4a217f5528cc26ecad3930bb255b9719061c  atomic_fence_cost.c
```
