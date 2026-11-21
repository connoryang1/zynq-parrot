This diagnosis localizes the failed native mode0 run to an image-packaging regression before any natural request. It uses only the recoverable prefix of the unfinalized, capped FST, exact ELF/NBF bytes and source/disassembly. It does not accept complete trace coverage, capacity effects or performance results, and does not establish an e109 ordinary-refill defect.

The preparer omitted the established `--keep_mem_zeros` option. The archived F35 runner uses `--skip_zeros --keep_mem_zeros`; the new preparer initially used only `--skip_zeros`. The initial nine old/new configuration records are byte-identical, so debug/config differences do not explain the regression. Old F35 explicitly writes zero to its allocator header at0x80006a80/6a88. The new image omits the corresponding required zero words at0x80006ee8/6ef0. Debug mode explains the exception redirect/restart, not the bad allocator input.

The available prefix shows39 entries into WHOLE/control setup and zero request/warm/ring/check markers. There are39 actual control commands and clear pulses;38 observed idle polls return raw status0x8308050005000000. Thus polling completes. The program then repeatedly raises a load-misaligned exception in `_malloc_r` at0x80001232 and redirects to the debug exception vector0x80000008, reentering CRT/main. The raw process eventually hits the200MiB FST cap; increasing only that cap would continue this invalid execution.

At the first exception, cycle117466, architectural a3 was written as3 at117465. The preceding instruction at0x80001228 is `ld a3,24(t1)`: memory-pipe operands show t1=0x800076e8, offset24 and EA0x80007700. A normal demand for that exact physical address is accepted at117438. The accepted first refill word at117460 has data3, fill mask1 and critical1, and the ordinary tag write is index28/way3/tag0x80007. Both ELF and NBF explicitly contain3 at this address (`__sglue+8`). The load therefore returns the requested value correctly. The next load uses rs1=3, offset8 and EA0xb; its load-misaligned exception is directly observed. This is not evidence of selecting a neighboring refill word.

The allocator reached that non-pointer field after consuming uninitialized bitmap/sentinel words:

| Physical address | File-backed ELF value | Failed NBF record | Observed accepted normal refill data |
|---|---|---|---|
|0x80006ee8|0|absent|0xc4156d89443a4ac3|
|0x80006ef0|0|absent|0x589a4e6fb6b3b5a0|
|0x800076f0|0x800076d8|present, exact|0x800076d8|
|0x800076f8|0|absent|0xf559028eb8884666|
|0x80007700|3|present, exact|3|
|0x80007710|0|absent|0xdcc33e632ea0fecf|

The nonzero ELF/NBF words agree with the selected address/data/masks/tags. Missing file-backed zero words do not have defined zero contents in this native model. No hardware change is justified by this failure. The targeted diagnostic files preserve selection, code, reader/source/input hashes, recovered events, first-fault operands, register writebacks, requests, data beats and tag packets. All remain explicitly prefix-only.

`prepare_image_v2.py` is a packaging-only correction, separately approved by the parent. It reuses the exact8c83 ELF and original `.mem`, without recompilation or a C/RTL/model/layout/corpus change, and adds `--keep_mem_zeros`. `image-v2-01/manifest.json` exhaustively verifies all30,912 file-backed PT_LOAD bytes including4,490 zero bytes. The failed image omitted952 bytes (119 all-zero64-bit words); the corrected image materializes all of them with no mismatched bytes. All14 nonmemory/config records and all previously materialized bytes remain identical. Each mode0/15 image fully matches the ELF with only its initialized8B mode-word override; the arms differ in one NBF record/one low byte. Six focused host checks cover omitted zeros, wrong values, duplicate writes, BSS distinction and mode override.

A fresh resource admission may now be reviewed using the corrected image. The old cohort stays failed with zero workload requests and supplies no arm contrast or effect. No corrected-image target execution is implied by the packaging preflight.
