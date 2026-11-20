This audit checks whether ordinary demand capture actually publishes and supplies unique instruction data in the recorded full-burst model. It also verifies the injected memory service timing at the real AXI interface. These are synthetic full-core controls with 2 physical slots and 4 logical contexts, not Linux application or 4-slot/4-context FPGA results.

The exact recorded BlackParrot revision is `ffc9bd7641bc1d9b3df6cf530f3a432db3ebae57`; the recording top revision is `9dbea5f7fc59c76fd18e0fc9502d3bb2abbd98a8`. Every mode uses ELF SHA256 `0bc79caf23b8f6f4f16525f2b4332752f91f6e10aeb6ed882e1d7467a27a93ca`; only the documented aligned NBF runtime-mode word changes. The session manifest retains exact compile/model flags, transport source hashes, closed FST hashes and native runtime acceptance. This audit does not relabel simulator process termination as a new runtime pass.

Sampling uses stable signal values immediately before actual BE rising edges. The exact ELF's retired global-cycle CSR reads at PCs `0x8000040c` and `0x80000414` delimit one complete recorded timed window. The windows reproduce the guest's values exactly. The boundary is architectural commit of those counter reads; in-flight refills begun before the first read can complete inside the window.

| Mode | Guest control | Timed cycles | Whole-run accepted misses / copied beats / complete epochs | Side-only consumed fetches, whole run |
| --- | --- | ---: | --- | ---: |
| 0 | Cold | 664 | 39 / 312 / 39 | 0 |
| 1 | Target warm | 197 | 39 / 312 / 39 | 0 |
| 2 | Source warm | 254 | 39 / 312 / 39 | 0 |
| 3 | Switch only | 111 | 32 / 256 / 32 | 0 |

All traces observe capture parameter 1 and eight response beats per 64-byte line. Captured beats match accepted cached-demand physical line addresses, all accepted beats reach the registered side-write path, and no provenance issues appear. At most 27 entries are complete simultaneously. There are zero side-only eligible cycles and zero side-only consumed responses across the entire traces, not just the timed prefix.

In modes 1 and 2, all seven prefix lines `0x80001000` through `0x80001180` in 64-byte steps are complete in the side store at timed begin. All 50 timed prefix fetch responses hit ordinary L1. Target-warm has 8 capture beats / 1 completion crossing into the timed window despite no new accepted miss there; source-warm has 16 capture beats / 2 completions and 1 new accepted miss. This is real refill overlap across a counter boundary, not capture suppression. As in the minimal path, the physical copy store does not provide guaranteed extra unique lines in this workload. It is not evidence of a prefetch speedup.

The cold mode's AXI trace proves the full-burst transport:

| Property | Observed |
| --- | --- |
| Core and AXI model clocks | Identical VCD handle; both source-wired to aclk |
| Configured first-response latency / queue depth | 40 ticks / 4 |
| Timed accepted read addresses | 8 |
| ARLEN / ARSIZE | All 7 / all 3: eight 64-bit beats, 64 bytes per transaction |
| AR acceptance to first R offer | 40 ticks for all 8 bursts |
| AR acceptance to final R acceptance | 47 ticks for all 8 bursts |
| Accepted within-burst beat spacing | 56 intervals, every interval 1 tick |
| Timed R backpressure | 0 cycles |
| Maximum outstanding reads, entire run | 1 |
| Pending reads at closed trace end / audit issues | 0 / 0 |

Raw AXI lines are `0x340` and `0x1000,0x1040,...,0x1180`, once each. The wrapper maps the core's physical DRAM address by XORing `0x80000000` and adding its configured DRAM base; raw AXI addresses are therefore deliberately reported separately from architectural physical addresses. One accepted AR services one 64-byte line here. The earlier minimal wrapper instead used 128 single-word ARs for the same cold 8-line path, so those earlier 40/200 results cannot be pooled as line-latency projections.

The source agrees with the trace. `cosim/black-parrot-example/v/top_zynq.sv` connects both `bp_axi_top` core/AXI clocks to aclk and forwards its ARLEN/ARSIZE onto HP0. `import/black-parrot-subsystems/blackparrot/v/bp_axi_top.sv` configures `bsg_cache_to_axi` with burst length `l2_block_width_p/axi_data_width_p`. The pipelined memory responder starts each accepted AR's absolute due time independently, preserves FIFO response order, and registers subsequent eligible beats every cycle when RREADY allows. Queue depth 4 is available but is not exercised beyond one outstanding read in this recorded experiment.

This validates a conditional 40-tick first-line-response setting plus one 64-bit beat per tick for this simulator path. It is not a calibrated DRAM latency or bandwidth estimate, does not establish memory-level parallelism benefits, and is not an FPGA measurement. The counter-bounded 664-cycle execution includes transport, refill, switch and instruction costs; the 8 burst timings must not be substituted for that complete endpoint. A matched capture-off model and changed-latency model remain the parent experiment's separate controls.

Reproduce without running a simulator:

```sh
fst2vcd MODE/dump.fst | python3 tools/analyze_icache_demand_capture_vcd.py --output MODE/capture-engagement.json
fst2vcd mode0/dump.fst | python3 tools/analyze_axi_burst_service_vcd.py --output mode0/axi-burst-service.json
python3 -B -m unittest -v test_analyze_axi_burst_service_vcd
```

The last command runs from `tools/`. Its three hand-constructed VCD tests check FIFO association for overlapping bursts, first-beat backpressure, complete-burst duration and one-tick beat pacing, visible RID mismatch, and rejection when BE/AXI clocks lack a proven shared handle. `capture-transport-audit-summary.json` binds every input FST/ELF/NBF/log, analysis script, source path and compact per-mode result by SHA256. No new simulator, FPGA or synthesis run was launched for this audit.
