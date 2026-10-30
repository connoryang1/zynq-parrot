This experiment turns the accepted physical Linux cache-miss records into a deadline-aware replay model. Its purpose is to choose between early shared-prefix replay, dispatch replay, small per-context retention, and a hybrid before implementing more RTL.

# Linux context-resume trace model

## Inputs and method

The model uses two complete, non-overflow sliced demand windows from the PYNQ-Z2
miss-recorder run and one preceding complete full-window run for training. The
three raw logs were recovered from the board and accepted only after their
SHA-256 values matched `logs/linux-cache-miss-trace-20261006/README.md`:

| Input | SHA-256 |
| --- | --- |
| source to peer | `066b633faa245c4ec436b6240d399179b1884d5febbb68702fff85261b75abf9` |
| peer to source | `2fc9456151b17163a03da2da8fb47a3ab48e5752800e710a2023ffa7f73e88e2` |
| preceding full-window training run | `98b23d3c1b3f36024e6534a0be8479812aebac1b7b69b7f1ed1bb33320210022` |

For each predicted 64-byte line, the simulator schedules request issue, first
and final response beats, serialized installation, and the first measured
demand. The primary case uses four outstanding slots, a 41-cycle
request-to-first-beat proxy, eight response beats, and the measured 19-cycle
FPGA-facing simulator installer median. The 41-cycle value is not a measured
detached full-line endpoint, so `results.json` also sweeps 41--200 cycles, one
to five slots, and 17/19/25-cycle installation.

The shared-prefix predictor takes privileged instruction lines from the prior
full-window trace, retains the eight most recent lines per cache set, and
replays that selected set in prior first-use order. Retention uses the prior
phase's first 1/2/4 unique lines. Dispatch replay is deliberately given the
current trace's future address order, making it an oracle timing ceiling rather
than an implementable predictor. The hybrid uses the trace-trained shared
prefix plus four oracle-retained immediately needed lines.

## Primary result

The two physical windows contain 266 instruction-demand records and 263 unique
instruction lines. Under the primary timing assumptions:

| Mechanism | Ready unique | Late unique | Unused prediction | Upper-bound cycles saved |
| --- | ---: | ---: | ---: | ---: |
| Dispatch replay, oracle order | 260 | 3 | 0 | 6,534.5 |
| Syscall-entry shared prefix | **175** | **2** | 34 | **4,397.7** |
| Trained retention, 1 line | 1 | 0 | 1 | 24.8 |
| Trained retention, 2 lines | 3 | 0 | 1 | 74.5 |
| Trained retention, 4 lines | 6 | 0 | 2 | 149.1 |
| Shared prefix + oracle retention of 4 lines | 179 | 0 | 34 | 4,497.1 |

The shared prefix predicts 211 lines across the independent windows. Of those,
177 are demanded and 175 are installed by first demand: 83.9% of predictions
are useful and 82.9% are timely. It covers 177 of 266 demand records in time,
or 66.5% of the recorded instruction-miss stream. Proportionally scaling the
separately measured 6,609-cycle cold-instruction penalty gives a 4,397.7-cycle
upper bound. This is a planning estimate, not an end-to-end speedup: the trace
contains request acceptance but not miss completion, and eliminating one miss
would move later execution timestamps.

The oracle dispatch row proves that a late trigger can still help later lines,
but it does not supply a realizable address predictor. The trace-trained
retention rows are much smaller: four retained lines add only six timely unique
lines, or an upper-bound 149 cycles. Even giving the hybrid four perfect
immediate lines adds only about 99 cycles over shared replay. On this workload,
retention is a complement for the first few deadlines rather than the primary
Linux mechanism.

## Sensitivity and decision

The shared-prefix conclusion survives pessimistic timing:

| First-beat latency | Slots | Timely unique | Late unique | Upper-bound cycles saved |
| ---: | ---: | ---: | ---: | ---: |
| 41 | 1 | 168 | 9 | 4,223.8 |
| 41 | 2 | 175 | 2 | 4,397.7 |
| 82 | 2 | 166 | 11 | 4,174.1 |
| 82 | 4 | 173 | 4 | 4,348.0 |
| 164 | 4 | 166 | 11 | 4,174.1 |
| 200 | 4 | 164 | 13 | 4,124.4 |
| 200 | 5 | 166 | 11 | 4,174.1 |

At the primary 41-cycle latency, changing installation from 17 to 19 or 25
cycles changes timely coverage from 176 to 175 lines. With a 200-cycle first
beat, four slots still cover 164 unique lines, while one slot covers only 44.
The decisive resource is therefore enough independent transport to begin the
stable shared prefix early; installer rate and a tiny retained store are
secondary for this recorded demand order.

The model selects an **early, independent, demand-priority shared instruction
replay lane with at least four full-line slots** as the next RTL architecture.
It should trigger at syscall/scheduler entry without waiting for the incoming
task identity. A small retained-line entry may be added later for immediate
private lines, but it should not replace the shared replay lane. The next RTL
gate should implement only the shared physical privileged prefix and measure
issued, timely, late, consumed, unused, and dropped lines against the same
recorder-disabled control.

## Reproduction and limits

Run:

```sh
python3 -B logs/cache-resume-trace-model-20261029/test_model.py
python3 -B logs/cache-resume-trace-model-20261029/model.py
```

`results.json` contains per-window events, trigger/translation sensitivity, and
the full timing sweep. Important limits are retained there: the full-line
physical latency and instruction installer remain unmeasured, the two sliced
windows are independent fresh boots, demand timestamps are not rescheduled
after modeled hits, and the cycle estimate is proportional rather than a
cycle-accurate Linux execution prediction.
