# Physical accepted-miss recorder validation

This directory preserves the first FPGA/real-DDR validation of the ordered
I/D accepted-demand-miss recorder. The routed image is top revision
`e860ceea`, BlackParrot revision `52c5dde70`, with bitstream SHA-256
`f4a183d8f900170ce5a6eb59366d56609cbe0f492063ea5a41b791d807306c5a`.
The exact directed NBF has SHA-256
`e30d602e3b857ec99f6248f16390e53ae4ce5cc4ac5c27b7f17249dbe2bb8353`.

All nine accepted physical samples report exactly two I-cache misses and one
D-cache miss, find the intended physical instruction and data lines, retain
the guest and core pass markers, and exit zero. In every sample the recorded
data request is accepted exactly 47 core cycles after the intended cold
instruction request. The range and median are therefore both 47 cycles. The
same directed program records 63 cycles in the maintained simulator, so the
physical interval is 16 cycles shorter.

The 47-cycle value is an interval between two **accepted requests**. It
includes the cold function's instruction-miss service, instruction execution,
and generation of its dependent load. It is not a standalone DDR response
latency because this recorder does not yet timestamp refill completion. Its
main result is stronger and more basic: the synthesized recorder captures the
right physical demand-request identities, preserves their order and cycle
timestamps, and does so deterministically on the actual HP0/PS-DDR path.

The board's standard runner initially requested 64 MiB and failed before NBF
loading because CMA could not supply 16,384 contiguous pages, even though
`CmaFree` reported 118,492 KiB. That rejected preflight is retained and is not
counted as a target sample. The directed NBF writes only through offset
`0x9e67`, so a temporary runner was rebuilt with a 16 MiB allocation. Every
successful run used only the first 8 MiB usage bucket and freed the buffer.
The FPGA bitstream and RISC-V NBF were unchanged. After measurement, the
original runner was restored byte for byte at SHA-256
`912362b0639b2fafdce3b6ba256cf004c2702a50f1db72207146ece7cd06386d`;
the board was left idle with the FPGA manager `operating`.

Run `./analyze.py` to regenerate `results.json` from the retained raw logs and
to require uniform counts, pass markers, zero runner status, bounded memory
usage, and a deterministic interval. `board-evidence.tar.gz` is the exact
archive transferred from the board, with original member hashes recorded in
`results.json`; the readable files under `raw/` have terminal CRLF converted
to LF. The next experiment should use these CSRs
around a Linux scheduler handoff and merge the independent I/D histories by
timestamp; this bare-metal test validates the instrumentation needed for that
measurement but does not itself contain a Linux context switch.
