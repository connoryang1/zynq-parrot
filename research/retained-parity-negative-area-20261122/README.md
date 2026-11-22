This preserves the measured negative area result of parity-banked full-line storage and reviews existing evidence at the next capacity boundary. It supports source/capacity decisions without claiming a routed limit, application speedup or unmeasured intermediate mapping.

| Matched1792 lines/side | LUT | FF | BRAM36 tiles | DSP |
|---|---:|---:|---:|---:|
| Canonical8df |1142|2211|56|0|
| Parityb295 |1591|2221|56|0|

Both acquisitions completed0 under the same production wrapper/50ns opposite clocks/Vivado2024.2 AreaOptimized_high/global-retiming settings, with actual ownership RELEASED and no owned group remaining. Every source and mapped artifact hash was independently rechecked; report totals were recomputed. Parity therefore adds449LUT/10FF and saves no RAM at this capacity; it is not selected for the next1792 whole-device attempt. Its twelve geometry/clock component runs passed, but that functional result does not convert negative area into an optimization.

Each parity lane has14RAMB36 in each even/odd bank (12at9bits,2at18bits), no RAMB18 tail. Even banks report physical B width0; odd banks report physical A/B9or18 despite one logical source RW port. The logical organization and actual primitive pins must be distinguished. No claim that all physical B ports are unused is made.

Existing canonical RAM-only measurements show1792=56tiles,1856=60,1920=60. The exact parameter and RAM/access fragments match current8df byte-for-byte. The old probe excluded FSM/epochs/RR/512-bit buffers/CPU/UCE, used Default synthesis and created clocks after synthesis; its results are not whole-device production-fit projections. Current production1792 reproduces the56tile footprint, but untested depths must still be mapped in their actual context.

The measured1792→1856 difference is entirely payload. PERlane,1792 has21RAMB36at9bits +4RAMB36at18bits +oneRAMB18at2bits +oneRAMB18at4bits;1856 retains all of these and adds2RAMB36at36bits. Tags stay2RAMB36at18bits. The payload word depth is14336 versus14848. There is no address-width cliff: for1792/1793/1800/1824/1856, local tag/payload address widths stay11/14, global widths12/15, tag29/epoch8/RR3 stay fixed. Ways change7→8, with a partial final way for in-between capacities. Ordinary caches are unchanged.

1793,1800 and1824 are UNMEASURED in these artifacts. The tail pattern suggests an allocation discontinuity, but it does not locate it; existing1856=60 must not be assigned to every intervening depth. Nor do unused bit capacity or primitive ceilings prove that any candidate uses≤58tiles. Traceoff changes the prospective whole-device budget/context, not evidence for unmeasured store layouts. A later explicitly authorized small source-bound mapping of these capacities is the cheapest direct answer; no new arm or vendor run was performed here. Full-device fit and functional gates would still follow any favorable footprint.

`review.py` reads the closed packets only, verifies acquisition/source/artifact hashes and recomputes exact resources/port groups/source geometry. `review.json` binds raw DCP/netlists externally, including old RAM reports; compact lossless snapshots retain exact sources/reports/primitive/protocol evidence. `verify.py` checks local curation bytes without vendor/model/reader execution. All previous b12/static/parity and operational-failure evidence remains unchanged.
