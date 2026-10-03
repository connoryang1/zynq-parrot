# Repeated prefetch/handoff lifecycle simulation

This test asks whether the fifth-launch stall from the integrated Linux request
workload is caused by detached-prefetch state accumulating across launches in
the core RTL. It repeats the physical probe's `prefetch.r; switch; load` shape
for six launches in one boot. Each launch first reads a separate 64 KiB
displacement region, reseeds resident context 1, and executes 256 requests in
each of contexts 0 and 1. Every return checks the preserved address register;
every launch checks both completion and context identity.

The exact trace-enabled command was:

```sh
BSG_TRACE_TIMEOUT_S=1200 VERILATOR_BUILD_JOBS=8 \
  make -C testing run-mt_prefetch_handoff_lifecycle_test \
  NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 TRACE=1
```

The minimal simulator uses the ten-entry detached side buffer and direct
prefetch AXI path. It does not include Linux, Sv39 translation, the full L2, or
physical DDR.

## Result

All six launches pass, including the fifth boundary where the physical Linux
workload stopped. The guest prints all six epoch markers and its exact PASS
marker; the core and host print `CORE PASS` and `BSG PASS`. The maintained
harness accepts the run after the known DPI-GPIO final-block assertion because
both guest and host completion precede it.

The waveform provides stronger lifecycle evidence than program completion:

| Epoch | Hints | Returned 8-byte beats | Side-buffer hits | UCE drops | Buffer/UCE valid at boundary |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 512 | 1,024 | 512 | 0 | 0 / 0 |
| 2 | 512 | 1,024 | 512 | 0 | 0 / 0 |
| 3 | 512 | 1,024 | 512 | 0 | 0 / 0 |
| 4 | 512 | 1,024 | 512 | 0 | 0 / 0 |
| 5 | 512 | 1,024 | 512 | 0 | 0 / 0 |
| 6 | 512 | 1,024 | 512 | 0 | 0 / 0 |

All 3,072 hints therefore produce a matching useful side-buffer hit, and all
6,144 response beats drain. There are no in-flight demand joins: every demand
arrives after its hint response has reached the side buffer. In epochs 2--6,
maximum occupancy is two side-buffer entries, one valid UCE entry, and one sent
UCE entry. Every observed structure returns to zero between launches, including
the first cold launch.

This rejects a simple persistent side-buffer or UCE-entry leak in the minimal
physical-address model. It does not explain away the physical stall. The next
reproducer must add the missing conditions independently: first U-mode Sv39
translation across repeated resident handoffs, then the full L2/DDR path if
translation still passes. The earlier demand-read preparation result can still
reflect translation, cache, or system-level launch state even though covering
additional pages was not required.

`extract.py` streams the FST through `fst2vcd`, retains 14 selected signals,
splits epochs at the five largest inter-hit gaps, and fails if any epoch lacks
512 requests, 1,024 beats, or 512 hits, or records a UCE drop. `analysis.json`
contains the checked result and `events.txt` contains the selected event stream.

The raw FST is 208 MiB and is retained locally as `lifecycle.fst`, rather than
committed. Its SHA-256 is
`b946f4aacd8f429f701b1e8c183ae248fa4699a2316da6553b116658542cea0e`.
The exact guest ELF SHA-256 is
`46243b85acb9d1fad96f0ea2168788f352cbb6111075f278c41f51c4b788d5ca`.
