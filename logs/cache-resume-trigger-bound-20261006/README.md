# Resume-replay trigger timing bound

The aggregate transport and installer rates are sufficient only if replay begins early. This model combines the four-slot shared-path bound with the physically measured hot Linux scheduler breakdown.

The complete conservative target—175 kernel instruction, 144 kernel data, and 160 application data line-equivalents—takes **5,825 cycles** using the measured 19-cycle median of the banked FPGA-facing wrapper under the conditional four-slot/41-cycle model. The measured hot combined resume window is 5,551 cycles, so the strict whole-footprint target misses by **274 cycles even when replay starts at yield entry**. The earlier 334-cycle trigger deadline applies only to the serialized direct path's 17-cycle rate, which the concurrent banked implementation does not sustain.

Here 41 cycles is a scenario input, not measured detached full-line latency. The
physical result is critical load-to-use. This trigger calculation becomes a
physical prediction only after request-to-final-beat and installation timing
is measured for the 64-byte replay path.

The 64-bit banked trace has a 19-cycle median and 25-cycle maximum. The maximum
would put whole-footprint completion at 7,649 cycles. Trigger timing therefore
cannot rescue this strict target by itself; replay must prioritize a smaller
prefix, retain some lines, or increase installation throughput.

The measured alternate-thread increment beyond a no-peer `sched_yield` is
2,139–2,238 cycles. Even granting the replay engine the larger 2,238-cycle
interval in full—an optimistic assumption because the interval itself includes
selection—the transport can complete at most **214 mixed lines**, only 44.7%
of the 479-line target and 67.1% of the 319-line kernel-only target. The full
kernel-only target needs 3,374 cycles at the measured median and must begin
within 2,177 cycles of yield entry. The generous late window is 61 cycles too
short even before realistic interference.

| Trigger window | Window | Maximum mixed lines | Fraction of 479 |
|---|---:|---:|---:|
| Yield entry to hot dispatch | 5,551 cycles | 537* | 112.1%* |
| Generous selection/switch/return interval | 2,238 cycles | 214 | 44.7% |
| Worker-direction interval | 2,139 cycles | 204 | 42.6% |
| Resident hardware handoff | 5.13 cycles | 0 | 0% |
| Nonresident hardware handoff | 9.26 cycles | 0 | 0% |

`*` Capacity rather than requested work; the target itself is 479 lines. The
capacity row assumes balanced use of the separate I/D installers, while the
actual target contains 304 data lines, so its measured-median completion is
still 5,825 cycles.

This separates the architectural choices:

- An explicit userspace hint immediately before yielding can expose nearly the full window.
- A kernel hook that names the incoming task only during `switch_to` is too late for whole-footprint replay, though it can still cover a prioritized subset and continue into application execution.
- An automatic syscall-entry trigger can start common kernel-line replay early, but it cannot choose incoming task-private data unless the predictor already knows the likely target.
- Five-to-eleven-cycle hardware handoffs cannot replay even the first cold line; resident contexts require retained state or a pre-existing background replay.

The decisive next evidence is ordered line identity and demand time. It will show whether the first 204–214 prioritized lines capture most of the benefit or whether the late-trigger shortfall is fatal.

Reproduce with:

```sh
python3 logs/cache-resume-trigger-bound-20261006/model.py
```
