# Post-switch bubble sweep

This experiment inserts 0, 1, 2, 4, or 8 explicit `nop` instructions after
each non-final context-switch CSR write and before the resumed context's next
dependent pointer load.  It tests whether a short post-switch interlock is
enough to suppress the instruction-spacing-sensitive physical corruption.

Recompiling the variants exposed a causality confound: linker relaxation
changes many instructions even for the one-bubble source, despite preserving
the relevant symbol addresses. The multi-point curve below therefore measures
the cost of delay but is not the preferred physical pass/fail control.

The decisive one-bubble control instead patches the exact original failing
NBF in place. At address `0x80000584`, its four-byte `j` becomes a two-byte
`c.nop` followed by a two-byte `c.j` to the same target. The complete NBF diff
is one 64-bit memory record at `0x80000580`; no address, surrounding
instruction, data, or configuration changes. The exact patched image is
`exact-inplace-bubble-n1.nbf`, SHA-256
`da075999c56bd29d82b8a0bd50dcb7dc55b8315a2676bc3cee94087cf4502e55`.

A matched branch-encoding control places the same compressed jump first and
an unreachable compressed NOP second (`c.j; c.nop`). It also changes only the
record at `0x80000580`, passes simulation in exactly the original 89,284
cycles, and has SHA-256 `0eead35c...ce65`. Thus `c.nop; c.j` versus `c.j;
c.nop` cleanly separates an executed delay from compressed-jump encoding.

The zero-bubble NBF has the same memory image as the exact failing 124-step,
ten-stream, context-4-hint NBF.  The older artifact appended a host patch of
`benchmark_config`; this rebuild puts the same `0x0000000004d80a03` value in
the initial image instead.  A diff of the NBF records confirms that this is
the only effective zero-bubble memory-image difference.

Simulator construction controls:

| Bubbles | Result | Measured cycles | Increment |
|---:|---|---:|---:|
| 0 | pass | 89,284 | 0 |
| 1 | pass | 90,480 | 1,196 |
| 2 | pass | 91,691 | 2,407 |
| 4 | pass | 94,103 | 4,819 |
| 8 | pass | 98,924 | 9,640 |

The exact in-place one-bubble image also passes simulation in 90,476 cycles,
1,192 cycles or 1.34% above the exact unmodified image. It is the preferred
FPGA comparison against original NBF SHA-256
`cfa9ededb6cc73c65acb0d7b5cc61100031e08908237db5af0c9c44f912cc7df`.

Two additional same-size, single-record controls separate bubble placement:

| Exact control | Placement | NBF SHA-256 | Simulator cycles | Increment |
|---|---|---|---:|---:|
| post-switch | after switch, before backward jump | `da075999...e55` | 90,476 | 1,192 |
| pre-switch | after hint logic, before switch | `1903ba3a...3d3` | 90,485 | 1,201 |
| body | after payload load, before hint logic | `0f08524e...afd` | 90,486 | 1,202 |

The pre-switch image replaces `mv a0,t0` with the same-size `c.mv a0,t0;
c.nop`; the body image similarly replaces `add a6,a6,t1` with `c.add a6,t1;
c.nop`. Each complete NBF differs from the original at one record. Their FPGA
outcomes distinguish mechanisms: post-switch-only recovery implicates the
incoming demand boundary; pre-switch-only recovery implicates settling the
outgoing hint before the handoff; all three recovering would indicate broader
loop-period sensitivity rather than a uniquely placed interlock.

## Fast two-stream cost control

The exact physical two-stream performance NBF was patched with the same
single-record `c.nop; c.j` method. Its unmodified simulator result is 19,258
cycles, only four cycles below the measured FPGA result of 19,262. The patched
simulator result is 20,536 cycles: exactly 1,278 additional cycles for its
1,278 non-final handoffs, or 6.64% of hardware runtime. Applying that measured
increment to the physical result predicts 20,540 cycles and a 2.925x speedup
over the 60,077-cycle demand baseline, down from 3.119x.

This is the cost of an unconditional software-visible bubble in the most
switch-intensive passing workload. A hardware repair conditioned on the
specific hazardous prefetch state could cost less, but that condition should
be designed only after the physical placement matrix identifies the relevant
boundary. The exact fast control is under `fast-k2-control/`; its original and
patched NBF SHA-256 values are `92b0bdbe...a5b0c` and `94ca62c3...39f89`.
The fast `c.j; c.nop` encoding control likewise reproduces the original
19,258 simulator cycles exactly; its NBF SHA-256 is `b0d538e5...af02e`.

There are 1,240 dynamic hot handoffs. The observed increments are nearly
linear but slightly below `1,240 * bubbles`, because some added instructions
occupy cycles that were already frontend or memory stalls. One bubble costs
1.34%, two cost 2.70%, four cost 5.40%, and eight cost 10.80% in this
switch-intensive workload.
The simulator already passed the original workload, so these runs validate
the generated binaries and quantify cost; they cannot decide whether the
bubble fixes the physical-only race. Fresh-overlay FPGA runs of the exact
original and three exact single-record images are the next decisive
measurements. The recompiled larger-delay images are secondary diagnostics.

## Final-lap prefetch-state trace

The retained exact 124-step FST was re-extracted across the final 3,800
cycles. All ten final switch dispatches see `mem_busy=0`, `mem_ordered=1`, and
`ctxtsw_order_haz_v=0`. The final lap contains zero detached request accepts,
response accepts, completed fills, or side-buffer writes. The last fill
completes 616 cycles before the context-2 demand that marked the lightweight
physical corruption boundary; the last side-buffer write is 614 cycles before
it.

One valid side-buffer entry remains from context 4's prior-lap hint. Context 4
consumes its two words later in the final lap; contexts 0, 1, and 2 do not hit
it. Consequently, an interlock conditioned only on active detached transport
would not fire around the observed context-2 boundary in this schedule. If a
bubble proves corrective physically, useful conditions include retained
side-buffer state or a narrower request/context transition, rather than merely
waiting for AXI responses to drain. The simulator does not reproduce the
corruption, so this is a temporal constraint on candidate repairs rather than
the physical root cause.

Retained prefetch state is present at 38 of 48 switch dispatches in the trace
(79.2%). It remains present for the first four final-lap dispatches, including
the context-2 boundary, and clears when context 4 consumes the entry. Thus
`pfvalid != 0` would cover the observed boundary, but it is not a rare-event
condition: in this interval it avoids a bubble at only 10 of 48 handoffs. If
the one-cycle cost scaled with those counts, it would recover about 20.8% of
the unconditional bubble overhead here. This is an upper-level selectivity
estimate, not a physical correctness result.

`handoff-timeline.tsv`, `handoff-timeline-analysis.json`, and the retained
extractor source provide the exact evidence.

The same extraction classifies every final pointer demand. Nine of ten are
ordinary L1 misses, and every one replays as a hit exactly 13 cycles later.
Contexts 0 and 1 therefore execute the same miss/replay pattern before the
lightweight physical checkpoint still reads the stack correctly; context 2 is
the third such miss, and context 3 repeats the pattern afterward. Context 4 is
the sole side-buffer hit. Context 2 is neither the first ordinary miss nor
latency-distinct, further weakening any claim that its set-7 load is itself the
corrupting operation. A repair conditioned on “first post-switch demand miss”
would also trigger for nine contexts and offers little performance selectivity.

## Reproducible physical matrix

`run_physical_matrix.py` pins all eight NBF hashes, the selected bitstream, the
board control program, and the installed interactive helper. It uploads each
unique NBF through hash-verified base64 over SSH, then runs the ten-comparison
matrix below with a fresh overlay before every target invocation:

1. original k10, branch-encoding control, post-switch bubble;
2. original k10 repeat, pre-switch bubble, body bubble, post-switch repeat;
3. original k2, branch-encoding control k2, post-switch bubble k2.

The repeated original and post-switch runs detect board-state carryover. The
k2 tail directly measures the physical performance cost. The script writes
every overlay and target transcript plus an incrementally updated JSON result.
Its offline `--dry-run` validates every local hash and prints the exact plan;
that validation passes. Execution remains pending because this environment
currently denies the SSH socket before the board can be contacted.
