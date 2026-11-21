Prepared one offline **46 MiB-limited retention-kernel27 image**, preserving the exact accepted-rootfs `c7c1e214…3ff` kernel and rootfs. This is preparation for a future capability-present retention probe; no new kernel/rootfs build, target execution, runner change or performance acceptance occurred.

The image is `/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/retention-kernel46-20261120/linux-prefix32-retention27-accepted-rootfs-mem46-shell.nbf`, **70,906,578 bytes**, SHA-256 **`a1fbac904a8604939ee55b0c91ca2812cc9b9451220a7a53df97cfd88acf97d5`**. Only this new NBF and small metadata/DTB files were written externally; no full reverse NBF was stored.

The unchanged maintained FDT helper replaces existing padding in the 49-byte bootargs property, including its final NUL:

```text
old: "console=hvc0 loglevel=8 rdinit=/bin/sh          "
new: "console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M  "
```

The strict existing embedded46 parser identifies one valid loaded DTB at `0x80016000`, with bootargs at `0x800163a0`. The helper inserts six aligned writes immediately before the final unfreeze. Every original NBF record remains byte-identical; removing exactly that block in a streaming comparison reproduces the source SHA-256 `c7c1e214796644b1dbe728cc274ca3d776c1cd24d4eb7ff570e109f44b53e3ff`. The complete nominal-memory comparison finds exactly seven changed bytes, `0x800163c7..0x800163cd`; all other bytes and FDT properties remain unchanged.

The full 24,034,304-byte kernel payload remains SHA-256 `64f993713e1d7d5fcae57c26e42b32369d0bccfa0235635dd0b0010871f57435`. Its 3,303,052-byte rootfs blob remains `0fbebeabd9fb4e152c0f79efe19f7275d08fd5956c97f0f022f829221735b5cf`, corresponding to accepted CPIO `e2f7dbc4d02d0ae99bb66832fe94b4882e19d7c95acd2cc0521299ff6aa73f50`. Kernel instructions, retention ABI, prefix table, rootfs contents and addresses are preserved.

The existing width-aware load guard accepts all **1,916,383 DDR writes**, with 11 separate configuration/MMIO records and maximum written end `0x818eba68`, below owned end `0x82e00000`. Both the 1,209-byte initial DTB and its 1,216-byte rounded copy fit: source `[0x80016000,0x800164c0)`, runtime destination `[0x82200000,0x822004c0)`. The source c7 session12 boot binds OpenSBI Next Arg1 to `0x82200000`; the prior embedded46 source proof binds Linux enforcement and firmware copying. These are offline initial-copy bounds, not observations of the new image at runtime.

`prepare.py` reuses the maintained helper and reviewed parser/load guard without changing them; seven existing padding/tree/load-tail tests pass. `manifest.json` is retained locally and externally with exact input/helper hashes, records, source inventory, reverse proof, payload hashes and bounds. Reproduction refuses to overwrite existing evidence. The original c7 package and all older manifests remain unchanged.

A fresh complete probe boot must still establish the new image's `Memory limited to 46MB` notice, 47,104 KiB total, DMA32 last byte `0x82dfffff`, Next Arg1 `0x82200000`, actual 48,234,496-byte allocation, checked capability-present ABI, normal return and CORE/BSG PASS. The memory-node `reg` remains 64 MiB; Linux's `mem=46M` is the software cap, with no new hardware ownership guard. The uncapped c7 image's prior unsupported-hardware probe does not close this new runtime/capability gate, and no timing result is pooled across these baselines.
