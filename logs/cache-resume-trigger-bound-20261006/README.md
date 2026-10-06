# Resume-replay trigger timing bound

The aggregate transport and installer rates are sufficient only if replay begins early. This model combines the four-slot shared-path bound with the physically measured hot Linux scheduler breakdown.

The complete conservative target—175 kernel instruction, 144 kernel data, and 160 application data line-equivalents—takes at least **5,217 cycles** under the conditional four-slot/41-cycle model. The measured hot combined resume window is 5,551 cycles. To have the entire target ready at first user dispatch, the incoming context must therefore be identified and replay started within roughly **334 cycles of yield entry**.

Here 41 cycles is a scenario input, not measured detached full-line latency. The
physical result is critical load-to-use. This trigger calculation becomes a
physical prediction only after request-to-final-beat and installation timing
is measured for the 64-byte replay path.

That is much earlier than ordinary Linux task selection. The measured alternate-thread increment beyond a no-peer `sched_yield` is 2,139–2,238 cycles. Even granting the replay engine the larger 2,238-cycle interval in full—an optimistic assumption because the interval itself includes selection—the transport can complete at most **214 mixed lines**, only 44.7% of the 479-line target and 67.1% of the 319-line kernel-only target. The full kernel-only target needs 3,308.5 cycles, so it must start within 2,242.5 cycles of yield entry, before the late switch/return interval.

| Trigger window | Window | Maximum mixed lines | Fraction of 479 |
|---|---:|---:|---:|
| Yield entry to hot dispatch | 5,551 cycles | 537* | 112.1%* |
| Generous selection/switch/return interval | 2,238 cycles | 214 | 44.7% |
| Worker-direction interval | 2,139 cycles | 204 | 42.6% |
| Resident hardware handoff | 5.13 cycles | 0 | 0% |
| Nonresident hardware handoff | 9.26 cycles | 0 | 0% |

`*` Capacity rather than requested work; the target itself is 479 lines.

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
