# Shared Linux I-cache prefix control checkpoint

This checkpoint adds the control plane needed to turn RL-050's manual physical
line ingress into a Linux-usable shared-prefix replay. It is a functional
simulation result, not an end-to-end Linux speedup, FPGA timing, or physical
DDR result.

## Interface and mechanism

- Machine-custom CSR `0x7c1` writes one of 256 physical line addresses. Bits
  63:56 select the entry and the low physical-address bits carry the address.
- Machine-custom CSR `0x7c2` sets the valid entry count (bits 8:0); bit 63
  clears counters.
- Supervisor-custom CSR `0x5c0` contains no physical address. A write launches
  the immutable M-configured prefix; a read returns controller status.
- The controller uses a synchronous 256-entry physical-address table and
  streams it into the existing four-slot UCE replay lane. It holds entries
  across lane backpressure and gives the original M-mode direct ingress
  priority without consuming the held prefix entry.
- A trigger while busy or with no configured prefix is counted and discarded;
  it cannot restart a partial sequence.

Status layout is: lane-ready bit 0, busy bit 1, held-entry bit 2, table-read
pending bit 3, configured count bits 12:4, next index bits 21:13, admitted
prefix entries bits 37:22, accepted triggers bits 45:38, and dropped triggers
bits 53:46.

## Accepted evidence

The focused controller gate in `run.log` and `icache-replay-ctrl.fst` proves:

- ordered four-entry table replay;
- stable output across downstream backpressure;
- direct-ingress priority without losing the held prefix entry;
- rejection and accounting of a retrigger while busy; and
- counter clearing without changing the configured prefix length.

The updated full-core `mt_icache_replay_test` configures four physical function
lines in M mode, enters S mode, launches the prefix with one `0x5c0` write,
returns through an M-mode ECALL handler, checks the controller counters, and
executes all four functions. It then retains RL-050's direct-ingress duplicate
and `fence.i` cancellation checks. `full-core-supervisor-run.log` reaches the
exact guest marker, `CORE PASS`, and host `BSG PASS`; only the documented
post-pass DPI-GPIO finalization assertion follows. Its SHA-256 is
`a7b8698a06b53d4dde4851099b10e2a01654c4d49906a2e02079e03e8f1dfba7`.

The complete non-waveform two-thread/four-context model also builds. The
unchanged real-UCE I-cache replay gate, narrow D-cache replay gate, malformed
response assertion, and all 15 fail-closed harness tests pass after the
integration.

## Reproduction

```sh
python3 testing/rtl/run_icache_replay_ctrl.py \
  --out logs/linux-icache-prefix-ctrl-20261030

PATH=/home/coyang/zynq-parrot/install/bin:$PATH \
make -C testing build-sim NUM_THREADS=2 NUM_CONTEXTS=4 \
  VERILATOR_BUILD_JOBS=2 \
  CFLAGS='-I/tools/Xilinx/Vivado/2024.2/tps/boost_1_72_0' \
  LDFLAGS='-L/home/coyang/zynq-parrot/install/lib'

PATH=/home/coyang/zynq-parrot/install/bin:$PATH \
make -C testing run-mt_icache_replay_test NUM_THREADS=2 NUM_CONTEXTS=4 \
  VERILATOR_BUILD_JOBS=2 ZP_INSTALL_DIR=/home/coyang/zynq-parrot/install \
  LDFLAGS='-L/home/coyang/zynq-parrot/install/lib'
```

## Limits and next gate

The controller counts triggers and entries admitted to the UCE, not memory
issues, completed installations, later demand consumption, unused lines, or
demand delay. Firmware/Linux still must load the trained prefix and place the
single trigger at the selected early syscall/scheduler point. The decisive
next experiment is therefore instrumentation plus matched Linux runs with
replay enabled, replay disabled, and recorder-only. Synthesis, routed timing,
physical full-line latency, and FPGA execution remain unmeasured.
