# FPGA miss-trace recorder sizing

The remaining replay uncertainty is the ordered sequence of instruction and data lines demanded between a pre-yield marker and first user dispatch. BlackParrot's existing I-cache/D-cache tracers and core profiler are simulation-only, and `mhpmcounter`/`mhpmevent` are not implemented. CSR `0x803/0x804` provides an active D-cache service path rather than a miss recorder.

A small synthesizable diagnostic can capture accepted ordinary read misses without modifying either cache pipeline. The clean observation points already exist in `bp_unicore_lite.sv`:

- I-cache: `mem_fwd_v_o[0] && mem_fwd_ready_and_i[0]`
- D-cache: `mem_fwd_v_o[1] && mem_fwd_ready_and_i[1]`
- Filter: BedRock memory reads with `payload.prefetch == 0`

Both streams are visible in the positive-edge clock domain after the D-cache edge FIFO. Use two independent memories so simultaneous I and D requests never contend for one write port. Global timestamps merge the streams offline.

The current endpoint has a 34-bit physical address and 64-byte lines, leaving a 28-bit physical line address. One 64-bit record can contain a 32-bit global-cycle timestamp, the 28-bit line address, and four metadata bits. The timestamp wraps after 238.6 seconds at 18 MHz, far longer than the measured interval.

Two **256 x 64-bit** simple dual-port buffers require 16,384 bits each, so each should map to one RAMB18. Together they add one BRAM tile. The accepted routed endpoint currently uses 82 RAMB36 plus three RAMB18, or 83.5 of 140 tiles. The recorder projects to **84.5/140 tiles (60.36%)**. It has 3,184 LUTs of arithmetic headroom and +4.827 ns routed WNS, although placement still requires synthesis because the design is slice-dense.

Depth 256 leaves 81 entries above the conservative 175 instruction refill-equivalents and 112 above the 144 data equivalents. Since those are timing equivalents rather than literal requests, each buffer needs a sticky overflow bit. This depth targets the kernel interval through first user dispatch; a separate post-dispatch application capture would need a larger D buffer or a second run.

The diagnostic interface can use three unused user-custom CSRs: control/status, read index/source, and 64-bit data. A source-thread write arms and clears the recorder immediately before `sched_yield`; the receiver's first aligned operation disarms it. Reading the buffers happens afterward while disarmed and is outside the measured interval.

This recorder provides the exact evidence RL-023 cannot infer: unique lines, recurrence, I/D ordering, first-demand cycle, and how many of the 204–214 late-trigger-capacity lines would actually arrive before use. It is measurement instrumentation, not the proposed replay implementation.

Reproduce the sizing with:

```sh
python3 logs/cache-resume-miss-tracer-design-20261006/size.py
```
