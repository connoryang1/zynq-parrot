These tests validate simulation infrastructure in isolated build directories.
They do not boot BlackParrot or modify the full-system simulator's shared files.

# Pipelined AXI memory model

Run the model's protocol checks with the repository's Verilator and host C++14
compiler:

```sh
python3 -m unittest discover -s cosim/tests -p test_axi_mem_pipelined.py
```

Set `BP_AXI_MEM_TEST_OUT` to retain generated files and logs; otherwise the test
uses a temporary directory. `VERILATOR` may name another compatible executable.
The driver explicitly advances the clock and needs no C++ coroutine support.

The full-system testbench keeps its stock `bsg_nonsynth_axi_mem` by default.
To select `bp_nonsynth_axi_mem_pipelined`, add `BP_AXI_MEM_PIPELINED` to the
existing simulation `DEFINES` list. Preserve the other full-system definitions.
Optional definitions are `BP_AXI_MEM_READ_LATENCY=40` and
`BP_AXI_MEM_READ_QUEUE_DEPTH=4`, shown with their defaults. The latency and queue
size must each be at least two. These are presence-based RTL switches:
`BP_AXI_MEM_PIPELINED=0` also enables the model. The model configuration stamp
tracks enablement and effective latency/depth, so changes invalidate the
previous executable. Follow the repository's clean-build verification flow
before collecting full-system results.

Each accepted AR starts an independent service interval. With a ready response
channel and no older response occupying it, its first beat transfers exactly
`read_latency_p` cycles after AR acceptance. Older responses and R-channel
backpressure can delay delivery; they do not restart a queued request's latency.
All responses retain acceptance order, including requests with the same ID.
The bounded queue includes the currently returning burst. Queue-full AR
backpressure is independent of writes, and every stalled R or B payload remains
stable. RAM is sampled when a beat enters the R output register; same-edge writes
are visible to later samples, while an already-offered response retains its data.

The model supports aligned FIXED, INCR, and WRAP bursts, including narrow
transfers and byte write strobes. It rejects unsupported alignment, oversized
transfers, reserved burst types, invalid WRAP lengths, INCR bursts crossing
4 KiB, out-of-range accesses, invalid WSTRB lanes, and WLAST/AWLEN disagreement.
Reset abandons pending transactions and preserves RAM. Initial RAM contents use
the configured 32-bit pattern repeated across each data word, including in
Verilator's two-state simulation.

The positive protocol check proves four reads are outstanding before the first
response, the first request's latency is 40 cycles, the second response burst
starts one cycle after the first RLAST when its service is already complete,
and a later fifth request independently takes 40 cycles. It also checks queue
backpressure, repeated IDs, stalled responses during concurrent writes, byte
strobes, narrow and wrapping accesses, deterministic initialization, and reset.
Separate negative checks require malformed WLAST, alignment, and 4 KiB boundary
transactions to fail explicitly. Run `python3 -m unittest discover -s testing
-p test_check_run.py` for the simulator-stamp transition checks.

This is a deterministic model for measuring overlapping service intervals and
response bandwidth. It does not model DRAM bank conflicts, refresh, or an FPGA
memory controller, and its timing is not FPGA performance evidence.
