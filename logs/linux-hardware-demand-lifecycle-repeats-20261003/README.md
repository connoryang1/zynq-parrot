# Repeated hardware-demand lifecycle outcomes

These physical-board repeats distinguish a deterministic code-placement bug
from an intermittent sustained-handoff hazard. Every run uses the exact same
qualified bitstream and Linux shell. The functional `source_demand` and
`peer_demand` opcode sequences are identical in every ELF.

| ELF / placement | Complete samples | Next sample | Outcome |
| --- | ---: | ---: | --- |
| Exact newer ELF, mixed modes | 16 per mode | 17 | Post-run verification failure |
| Exact newer ELF, demand-only run A | 26 | 27 | Post-run verification failure |
| Exact newer ELF, demand-only run B | 2 | 3 | In-loop nonreturn |
| Diagnostic ELF, functions +32 bytes | 64 | — | Clean pass |
| Original checks, functions 64-byte aligned | 50 | 51 | In-loop nonreturn |
| Older ELF control | 32 | — | Clean pass |

The exact newer ELF fails on all three attempts, but the failure point varies
from sample 3 to 27. More decisively, placing both hardware loops exactly on
64-byte boundaries does not eliminate the problem: that controlled build
stalls in sample 51. The earlier shifted diagnostic's 64-sample pass therefore
does not prove a frontend/cache-line-placement fix.

Across the four demand-only new-family runs there are 142 complete launches
and three failed launches. An intentionally simple constant independent-hazard
model estimates a 2.07% failure probability per launch and gives a 26.2%
chance of observing 64 consecutive successes. The model's assumptions are not
established—the ELFs differ—but it demonstrates why one 64-sample pass is
compatible with an intermittent lifecycle bug.

Two terminal symptoms are now measured: some runs return to C with an invalid
context/completion record, while others stop inside the handoff loop. The next
useful instrumentation is therefore a bounded progress record written by both
contexts during the assembly loop. It should record the last source iteration,
last peer iteration, and current context without relying on normal return.

Reproduce the cross-run audit with:

```sh
python3 -B logs/linux-hardware-demand-lifecycle-repeats-20261003/analyze.py \
  > logs/linux-hardware-demand-lifecycle-repeats-20261003/analysis.stdout
cmp logs/linux-hardware-demand-lifecycle-repeats-20261003/analysis.json \
  logs/linux-hardware-demand-lifecycle-repeats-20261003/analysis.stdout
```
