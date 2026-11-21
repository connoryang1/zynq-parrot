This repair limits Linux ordinary RAM to the immutable runner's 46 MiB allocation. It changes only existing FDT bootargs padding in the verified embedded image pair, and a complete physical known-flow gate confirms the actual bounds. It does not establish the cause of earlier SIG11 failures or a performance improvement.

The new files are under `/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/embedded46-workloads/`:

| Image | SHA-256 |
| --- | --- |
| `linux-prefix32-embedded46-baseline-shell.nbf` | `2e5ccc94a801fe724fd5b8787f5086fb6e939795c4ec98e49ef7a702ad9c024a` |
| `linux-prefix32-embedded46-control-shell.nbf` | `32db338b492964d3e1aecdc35fbb9dc77a7b1959740f9717a71f689a144d0efa` |

The source images remain the verified embedded baseline `e9ae...` and control `edd3...`. Their kernel/rootfs bytes, ELF provenance and prefix table are untouched. The source rootfs remains CPIO `2c294725...e9d7`, shared by both capped arms. No fresh rootfs, kernel ELF, kernel build or host-runner binary was created.

Ordered reconstruction at each actual NBF memory width finds exactly one valid loaded DTB: physical `0x80016000`, firmware offset `0x16000`, total size 1,209 bytes. The parser verifies header ranges, reserve map, structure tokens, strings, node/property uniqueness and lengths. Its `/chosen/bootargs` property starts at physical `0x800163a0` and remains 49 bytes including the final NUL:

```text
old: "console=hvc0 loglevel=8 rdinit=/bin/sh          "
new: "console=hvc0 loglevel=8 rdinit=/bin/sh mem=46M  "
```

The existing maintained `make_linux_shell_nbf.py` helper inserts six aligned writes at `0x800163a0..0x800163d0` immediately before the final unfreeze. All original NBF records remain byte-identical. Final nominal memory differs at exactly seven bytes, `0x800163c7..0x800163cd`; those are the nonspace bytes of `mem=46M`. Property length, FDT total size, reserve map, all other properties and the 64 MiB memory-node `reg` remain unchanged. Removing the exact inserted block restores each source NBF byte for byte; restoring the old property bytes restores the complete source nominal memory.

The firmware source DTB and Linux's runtime DTB argument are distinct addresses. A complete accepted `ef50...` boot records OpenSBI Next Arg1 `0x82200000`; retained OpenSBI source selects the embedded firmware FDT, supplies that next argument, and copies the FDT there. The entire initial 1,209-byte tree and its 1,216-byte rounded machine-word copy fit within the owned allocation at both source and destination: the runtime copy ends at `0x822004c0`, below `0x82e00000`. This is an offline initial-copy bound; new runtime boot evidence is still required.

The independent load guard checks every write overlapping advertised DDR `[0x80000000,0x84000000)`, including its final byte and actual width. Each capped arm contains 1,887,663 DDR writes plus 11 separate configuration/MMIO records. The maximum loaded end is `0x818eba68`, offset `0x18eba67` for the last byte, below 48,234,496 owned bytes. The guard rejects tail crossings, high unowned DDR writes and values that would require width truncation. No record is silently clipped or discarded. The complete kernel payloads remain baseline SHA-256 `6116cd8d1316a59a74549c5dfd91245acd9288daf920a91b0b862a7d94dd230a` and control `c9945c141f545624046e7f3a86dcd71425bc75e6cfc8f370cae5f6c0b8ba8c5a`.

Primary Linux 6.6 source snapshots bind the intended enforcement: `early_param("mem", early_mem)` parses and page-aligns the size, `setup_arch` parses early arguments before `paging_init`, and `setup_bootmem` invokes `memblock_enforce_memory_limit`. That function truncates both memory and reservation maps at the computed end; final ordinary linear mapping is also bounded by `memory_limit`. For the existing single bank beginning at `0x80000000`, 46 MiB means exclusive RAM end `0x82e00000`, expected DMA32 last byte `0x82dfffff`, total 47,104 KiB and maximum normal RAM offset `0x2dfffff`, strictly below the owned allocation size. Source intent does not substitute for observing those values on the new boot.

The capped pair still differs only at the reviewed mode-14 instruction byte. Its only differing NBF record remains line 1,075,385, changing `0x471d` to `0x4721` at physical `0x80a13fe8`. The prior all-256-mode semantics proof remains bound to the unchanged kernel payloads. `manifest.json` hashes to `099370428f6e568c474e119b5dca601604a71333ce8377aa05ca76e139a3ff32`; independent `verification.json` hashes to `0d2a9793007c507ae7d112e1acdd1eb273d8be4ee692835c60519bc503158ad4`. Both are retained locally and externally with source snapshots, DTBs, helper logs and exact reverses.

The dedicated comparator adds only the fixed `--image-pair embedded46` selector. Original and uncapped embedded selectors keep their existing pins and defaults. Embedded46 additionally requires the immutable `2dd9c411...7c30` runner and actual complete-boot evidence for the `Memory limited to 46MB` notice, 47,104 KiB total, DMA32 end `0x82dfffff`, Next Arg1 `0x82200000`, `mem=46M` command line and both announced/actual 48,234,496-byte allocation messages. WHOLE/resource rows, all terminal/drain gates, exact identities/configuration and at least two independent boots per image remain mandatory. The capped and uncapped image families cannot be pooled.

`host-tests.log` exercises FDT padding, malformed trees, duplicate properties, inventory and DDR byte/word tail limits. `comparator-tests.log` retains the fixed-family regression gates and rejects absent, inconsistent or oversized runtime bounds.

`physical-bounds-gate.json` binds complete session15: copied exact `e943...` scan workload, checked results, normal shell return, CORE/BSG PASS and runner zero exit. Actual Linux reports 46 MB/47,104 KiB and DMA32 end `0x82dfffff`, firmware passes the DTB at `0x82200000`, and both host allocation messages report 48,234,496 bytes. This closes the memory-bounds and known-flow gate only. Session16 failed during upload with ENOSPC before execution and recovered; narrowly scoped task-owned staging maintenance enabled complete session17 scan/parse boots. Session17's older resource ELF has the policy-scope defect documented in `../complete-policy-scope-20261120/`, so its WHOLE rows remain diagnostic and cannot support a causal policy comparison. The original preregistered plan is retained; the new scoped-ELF plan is recorded separately rather than silently replacing its identities.
