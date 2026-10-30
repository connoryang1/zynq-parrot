# Physical I-cache replay RTL checkpoint

This directory records the first functional implementation checkpoint selected
by RL-049. It is an RTL/protocol result, not a Linux speedup, routed FPGA, or
physical-DDR timing result.

## Implemented mechanism

- Four independent 64-byte physical replay slots feed the I-cache UCE without
  consuming the architectural cache-request pipe.
- Replies are buffered per line and installed through the existing cache SRAM
  interface only when ordinary work is quiescent.
- Architectural demand has priority. A demand arriving during installation
  aborts the advisory install and proceeds through the ordinary UCE path.
- Accepted `e_cache_inval` (`fence.i`) immediately invalidates the replay epoch.
  Unissued or completed slots are discarded; an already-issued packet retains
  only enough identity to drain its response and cannot publish into L1.
- Machine CSR `0x7c0` is the initial physical-address test ingress. Its read
  value bit zero reports queue readiness. This is not the final Linux trigger
  or learned shared-prefix table.

## Accepted evidence

The isolated test in `run.log` and `uce-icache-replay.fst` checks the real UCE
and stream pumps. It observes:

- one complete reply causing exactly four 128-bit data writes followed by one
  tag publication;
- a partially returned replay canceled by invalidation draining its remaining
  beats with zero data writes and zero publication; and
- an architectural miss arriving in the fill state aborting replay and issuing
  its ordinary non-prefetch memory request.

The full-core program `mt_icache_replay_test` enqueues four distinct aligned
instruction lines, executes all four targets, cancels a fifth across `fence.i`,
and checks duplicate admission. `full-core-run.log` contains its exact guest
marker, `CORE PASS`, and host `BSG PASS`. The only later errors are the
repository's documented DPI-GPIO finalization exception, accepted by
`testing/check_run.py`. The ELF SHA-256 is
`f22fda2287f0c899813bbb61aac3240318ea068d1f3843b989ec751f6fb3bdb4`.

The restored narrow D-cache gate is independently retained in
`../uce-prefetch-regression-20261030/`; it passes ten-slot admission, duplicate
coverage, reordered 16-byte replies, demand routing, final-beat backpressure,
and malformed-response rejection.

## Reproduction

```sh
python3 testing/rtl/run_uce_icache_replay.py \
  --out logs/linux-icache-replay-unit-20261030

python3 testing/rtl/run_uce_prefetch.py \
  --out logs/uce-prefetch-regression-20261030 \
  --verilator /home/coyang/zynq-parrot/install/bin/verilator

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

`verification.json` hashes the unit executable, waveform, run transcript,
Verilator binary, and transitive RTL dependencies. `full-core-run.log` and
`full-core-build.log` have SHA-256 values
`ed28a9692247a6c77ade95de88b6b05fee2aaffec619fb4092117590003deee1` and
`5341f8c62921bf28dba39e3d684f727def489956d15afd76fdeb843ff9ef9f7e`.

## Workflow notes and limits

The experiment checkout has no local Verilator, Boost headers/libraries, or
RISC-V compiler. Builds therefore use the recorded canonical Verilator/compiler,
Vivado 2024.2 Boost 1.72 headers, and canonical Boost 1.72 libraries shown
above. A traced full-core build initially exhausted the nearly full filesystem;
the repository `rebuild-sim` target reclaimed only generated `obj_dir` data and
the successful functional rerun used the smaller non-waveform model.

The first CSR implementation incorrectly suppressed the normal CSR redirect by
classifying `0x7c0` as a context-switch CSR. The trace proved execution stopped
immediately after the first enqueue. Restoring ordinary CSR retirement semantics
fixed it. A cancellation signal derived from `cache_req_yumi_o` also initially
fed the main combinational UCE block; current RTL uses the invalidate request
for same-cycle suppression and the accepted handshake only for sequential epoch
retirement, removing that new feedback path.

Still missing are the M-configured shared-prefix table, a safe low-overhead
Linux/S-mode trigger, hardware counters for timeliness/usefulness, scheduler
coexistence measurements, synthesis/timing, physical full-line DDR latency, and
an end-to-end replay-enabled versus replay-disabled Linux comparison.
