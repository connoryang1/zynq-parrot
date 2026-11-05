This evidence extends the earlier five-headline-mode physical sweep with a complete run of all eleven Nano lookup schedules at N=8. It keeps the physical-DDR result separate from the synthetic 200-cycle simulator result and retains every accepted transcript. The routed overlay is a qualified ten-context ancestor of the newer Nano simulation RTL, so this is an FPGA platform comparison rather than an exact RTL-revision reproduction.

# Nano N=8 physical-FPGA matrix

## Result

Every mode passed four independent processor-reset invocations, its mode/query selector, result oracle, guest marker, `CORE PASS`, host `BSG PASS`, and native exit zero. Each data mode performs 88 useful node visits; switch-only has no data work and its normalization is diagnostic only.

| Mode | Schedule | Median cycles | Min--max | Median cycles/node |
| ---: | --- | ---: | ---: | ---: |
| 0 | Serial demand | 6,116.0 | 6,114--6,122 | 69.500 |
| 1 | Demand ring | 6,963.5 | 6,959--6,970 | 79.131 |
| 2 | Hardware worker prefetch | 7,030.5 | 7,027--7,035 | 79.892 |
| 3 | Historical runtime-count batch | 7,210.5 | 7,201--7,213 | 81.938 |
| 4 | Switch-only | 1,209.0 | 1,209--1,209 | 13.739 diagnostic |
| 5 | Serial prefetch | 3,995.0 | 3,661--4,270 | 45.398 |
| 6 | Checked C++20 coroutine | 11,618.0 | 11,617--11,619 | 132.023 |
| 7 | Fixed unrolled SoA batch | 6,369.5 | 6,364--6,384 | 72.381 |
| 8 | Fixed recompute batch | 6,380.0 | 6,371--6,383 | 72.500 |
| 9 | Lean-queue C++20 coroutine | 9,467.5 | 9,462--9,472 | 107.585 |
| 10 | Direct C++20 coroutine | 8,407.0 | 8,404--8,416 | 95.534 |

The best explicit software batch is 1.104x faster than hardware. Hardware is 1.196x faster than the best direct coroutine, but serial prefetch is 1.760x faster than hardware. Unlike the 200-cycle simulator, this FPGA therefore does not benefit from interleaving this fine-grained lookup: the measured first-touch DDR path is only about 41 core cycles on this low-frequency platform, so request scheduling and state-management work exceed the latency hidden. Serial prefetch is the only visibly variable row; its full accepted range is reported rather than selecting the 3,661-cycle sample.

The independent earlier three-sample N=2--10 physical sweep reports N=8 medians of 6,114 serial demand, 3,947 serial prefetch, 6,365 fixed batch, 7,025 hardware, and 8,405 direct coroutine cycles. This all-mode extension differs by only 0.033%/1.216%/0.071%/0.078%/0.024%, respectively; the larger serial-prefetch difference is consistent with this row's 3,661--4,270 accepted range. The two retained evidence sets therefore agree on the physical ordering and magnitude.

## Hardware and software identity

- Board: PYNQ-Z2, physical PS DDR, routed 18 MHz target.
- Overlay job: `20261004T200130Z-b7cf9953`.
- Overlay top/BlackParrot: `b7cf9953c6e5f2134536c3c0ecf0e8ee19bee573` / `c50b85719863443ba69de1bc2fd6575ca0b9e0a7`.
- Configuration: `e_bp_unicore_zynqparrot_prefetch10_cfg`, two resident banks, ten logical contexts, ten prefetch slots.
- Routed timing: WNS/TNS `+1.280/0 ns`; WHS/THS `+0.024/0 ns`.
- Utilization: 50,380 LUTs, 28,480 registers, 83.5 BRAM tiles, and 11 DSPs.
- Package SHA-256: `e9c4c01e639ae4558b84065a73043a9432a2fdc8edd657638144801d8a840e39`.
- Loaded bitstream SHA-256: `f234819855ee79028ccf6387a356fe297962b9e30e36420f4da224150384a7b8`.
- Benchmark source top/BlackParrot gitlink: `c55e3d861fc8e5e0926e2f7039dc253660ec3c70` / `6c79a42107a3857e63b6f47bc2468fe4599c5bff`.
- Board ELF SHA-256: `df4a18cb8b74193e063919aea3aee6ee903f11b3c4741c2f504e5b98567536e6`.
- Reviewed integer CRT SHA-256: `66453d7164c74d728e940f2d8b2fd7e8486422abd51570ecd492f49212e78ff1`.
- Candidate-exact NBF tool SHA-256: `41f7d6cde186bc210f82f643715f920a89050e9eb188b8dcb90b4e1811afe75f`.
- Board runner SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.

One O3 board ELF supplies all rows. Each NBF differs only in the aligned eight-byte selector at `0x80011f00`, encoding mode plus eight workers. The board was power-cycled after each interrupted bring-up attempt, gated on 90 seconds of PYNQ uptime, and explicitly loaded with the verified overlay. The maintained serialized runner reset the processor for every accepted sample; board execution was never concurrent.

## Evidence and limits

`board-all-samples.json` and `board-summary.json` are generated from the retained `mode*-board*.log` transcripts by `analyze_board_results.py`. `board-image-manifest.json` records source, ELF, CRT, NBF tool, and per-mode image hashes; `build_board_images.py` reproduces the images and rejects any 64-bit NBF write outside the board's 32-bit address window.

Two bring-up failures are excluded from performance results. An initially empty expected-runner argument exposed a maintained SSH wrapper bug before `control-program` launched. A first image build rebased only the initial Verilog address marker, producing later NBF writes above 4 GiB; the host loader exited before guest startup. The corrected builder rebases every marker, validates all write addresses, and all subsequent runs pass.

The overlay's BlackParrot revision is an ancestor of the Nano branch's `6c79a4210` switch-boundary interlock. Switch-only is nevertheless 1,209 FPGA cycles versus 1,211 in the exact Nano simulator, and every workload passes, but an exact `6c79a4210` route remains desirable before claiming revision-matched simulator/FPGA deltas. No board AXI waveform or outstanding-request counter was collected, so the physical mechanism is inferred from matched workload timing and prior board latency evidence rather than directly traced occupancy.
