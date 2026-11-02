# Nano coroutine comparison on PYNQ-Z2

This run repeats the hot coroutine decomposition and the matched Nano lookup
comparison on the physical FPGA.  It uses three fresh processor-reset samples
for every `N=2..10` / mode point and five samples of the hot benchmark.  All 140
invocations pass the guest check, `CORE PASS`, native runner exit zero, and the
hash-pinned serialized board runner.

## Result

Cells below are median physical core cycles with the three-sample min--max in
parentheses.  Every Nano lookup performs exactly 11 dependent nodes per active
search.  Mode 7 is the fixed unrolled structure-of-arrays batch and mode 10 is
the direct symmetric-transfer C++20 coroutine ring.

| N | Serial demand | Serial prefetch | Fixed batch | Hardware contexts | Direct coroutine |
|---:|---:|---:|---:|---:|---:|
| 2 | 1,554 (1,553--1,554) | **1,224 (1,166--1,337)** | 1,359 (1,358--1,365) | 1,574 (1,564--1,575) | 2,136 (2,135--2,139) |
| 3 | 2,312 (2,310--2,312) | **1,559 (1,547--1,885)** | 2,353 (2,299--2,362) | 2,520 (2,520--2,521) | 3,186 (3,186--3,190) |
| 4 | 3,070 (3,069--3,073) | **2,129 (2,091--2,294)** | 3,150 (3,098--3,151) | 3,449 (3,438--3,450) | 4,210 (4,209--4,223) |
| 5 | 3,829 (3,822--3,829) | **2,667 (2,497--2,865)** | 3,920 (3,917--3,930) | 4,341 (4,339--4,349) | 5,280 (5,279--5,283) |
| 6 | 4,588 (4,586--4,595) | **3,037 (2,771--3,329)** | 4,735 (4,734--4,743) | 5,242 (5,224--5,242) | 6,300 (6,298--6,311) |
| 7 | 5,348 (5,341--5,351) | **3,597 (3,465--3,925)** | 5,533 (5,532--5,538) | 6,148 (6,147--6,149) | 7,338 (7,333--7,339) |
| 8 | 6,114 (6,113--6,122) | **3,947 (3,947--3,973)** | 6,365 (6,365--6,379) | 7,025 (7,024--7,030) | 8,405 (8,401--8,414) |
| 9 | 6,935 (6,933--6,942) | **4,314 (3,933--4,365)** | 7,198 (7,197--7,201) | 7,940 (7,939--7,951) | 9,417 (9,410--9,417) |
| 10 | 7,711 (7,705--7,712) | **5,156 (4,561--5,289)** | 8,069 (8,065--8,071) | 8,876 (8,867--8,876) | 10,487 (10,487--10,490) |

The corresponding median cycles per lookup node are:

| N | Serial demand | Serial prefetch | Fixed batch | Hardware contexts | Direct coroutine |
|---:|---:|---:|---:|---:|---:|
| 2 | 70.636 | **55.636** | 61.773 | 71.545 | 97.091 |
| 3 | 70.061 | **47.242** | 71.303 | 76.364 | 96.545 |
| 4 | 69.773 | **48.386** | 71.591 | 78.386 | 95.682 |
| 5 | 69.618 | **48.491** | 71.273 | 78.927 | 96.000 |
| 6 | 69.515 | **46.015** | 71.742 | 79.424 | 95.455 |
| 7 | 69.455 | **46.714** | 71.857 | 79.844 | 95.299 |
| 8 | 69.477 | **44.852** | 72.330 | 79.830 | 95.511 |
| 9 | 70.051 | **43.576** | 72.707 | 80.202 | 95.121 |
| 10 | 70.100 | **46.873** | 73.355 | 80.691 | 95.336 |

Ten shards are therefore not optimal for the hardware schedule on this board.
Its best measured cycles/node is N=2, where both contexts are resident.  The
hardware advantage over direct coroutines is also largest at N=2: 1.357x
throughput, falling to 1.182x at N=10.  Hardware never beats serial demand,
serial prefetch, or the fixed batch in this physical sweep.  N=3 is its closest
batch comparison (7.1% slower).  The N=9 serial-prefetch median is the lowest
cycles/node, but that mode has wider run-to-run variation; N=8 is almost as fast
and much tighter.

## Hot coroutine cost

Frames are constructed outside the timed interval.  Four of the five runs are
bit-identical; inline differs by one cycle in one run.

| Path | Median cycles | Cycles/operation | Increment over manual |
|---|---:|---:|---:|
| Inline payload | 24,611 | 3.004272 | -9.999023 |
| Manual noinline resume | 106,523 | 13.003296 | 0 |
| Single coroutine with outer driver | 204,863 | 25.007690 | +12.004395 |
| Eight-frame direct ring | 237,943 | 29.045776 | +16.042480 |

The direct-ring value differs from the accepted simulator result by only four
total cycles.  The board-linked single-coroutine path is about nine
cycles/operation faster than its simulator-linked counterpart; that is a
code-layout/link-image effect, not run noise, because all five physical samples
are identical.  The direct ring is the relevant mechanism for the Nano mode.

At N=8, direct coroutine minus batch is 23.181 cycles/node.  The separately
measured 16.042-cycle hot direct-ring premium describes 69.2% of that gap; the
remaining 7.139 cycles/node includes lookup-frame work, request spacing, and
memory-system interaction.  This is descriptive, not strict subtractive
accounting, because the hot counter and Nano lookup do not execute identical
state.  Direct coroutine is 15.681 cycles/node slower than hardware, while
hardware itself is 7.500 cycles/node slower than batch.

## Why FPGA and 200-cycle simulation differ

At N=8 the accepted synthetic 200-cycle model measured 2,810 hardware, 3,817
batch, 5,567 direct-coroutine, and 20,331 serial-prefetch cycles.  This FPGA
measures 7,025, 6,365, 8,405, and 3,947 respectively.  The ordering reverses
because the physical board's previously measured first-touch load interval is
about 41 cycles, not the simulator's fixed 200-cycle memory delay.  An immediate
serial hint can provide useful lead with almost no scheduler work, whereas
batch, hardware switching, and coroutine suspension execute extra instructions
that are not repaid by enough additional latency hiding.

This shape independently agrees with the earlier physical dependent-stream
experiment: its ten-stream hardware schedule was 11.2% slower than serial
demand and 19.9% slower than serial prefetch.  That experiment's waveform model
found victim collisions and busy hint drops in interleaved schedules while
serial prefetch admitted every hint.  The present FPGA has no bus waveform, so
the Nano totals reproduce the aggregate symptom but do not prove that exact
per-request mechanism.  All runs used the same physical CMA base (`0x16900000`),
so the serial-prefetch spread is not explained by different allocation bases.

## Identities and evidence

- Source and BlackParrot checkout: `c55e3d861fc8e5e0926e2f7039dc253660ec3c70`.
- Static FPGA configuration: two resident banks, ten logical contexts, ten
  prefetch slots.
- Qualified package SHA-256:
  `e9c4c01e639ae4558b84065a73043a9432a2fdc8edd657638144801d8a840e39`.
- Loaded bitstream SHA-256:
  `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`.
- Board runner SHA-256:
  `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.
- Both benchmarks use `-O3`, the board integer startup, and physical cycle CSR
  `0xcc0`.  Nano uses one ELF; only the aligned `benchmark_mode = mode | N<<8`
  word is patched before unfreeze.
- `samples.csv` retains every accepted result.  `raw-transcripts.tar.gz`
  retains all 135 Nano transcripts, five hot transcripts, staging and overlay
  logs, and NBF hashes.  Each local transcript contains the runner's live copy
  and retained replay; these are one invocation, not two samples.
