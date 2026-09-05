# Linux Feature Compatibility Bisect

> Purpose: This document defines the reproducible search for the first
> SRAM-backed context-switch feature prefix that still prevents the archived
> Linux image from reaching `/init` after the known Linux-compatibility fixes
> are applied. It separates feature history from later repair history so every
> expensive FPGA result has a clear interpretation.

## Question

Which commit in the SRAM-backed context-switch feature sequence first remains
incompatible with Linux after the established frontend, I-cache, CSR, SATP,
and stale-fault repair semantics are present?

## Fixed endpoints

| Role | BlackParrot revision | Meaning |
| --- | --- | --- |
| Good feature baseline | `c39ee12b735` | Initial context-switch implementation; FPGA-verified Linux boot through `/init`. |
| Good compatibility seed | `ce328a77536` | `7331fbd0` plus the two independently required frontend safety restorations; FPGA-verified Linux boot through `/init`. |
| Feature tip | `8708eff7` | Last SRAM-backed context-switch feature commit before the compatibility repair series starts. |
| Bad repaired endpoint | `3df31a94e532` | Feature tip plus the compatibility stack and three OpenSBI CSR repairs; a fresh FPGA run prints the complete OpenSBI report but no Linux banner before its clean 180-second limit. |

The raw feature interval has 114 commits (`c39ee12b735..8708eff7`). The
practical replay starts at the good compatibility seed and replays the 113
post-`7331fbd0` feature commits through `8708eff7`; a binary search still
requires at most seven decisive hardware results after endpoint validation.

## Candidate construction

Create an isolated replay worktree from `ce328a77536`, which already contains
the two FPGA-proven safety constraints for the first fast-path regression.
Replay selected post-`7331fbd0` feature commits into that worktree, resolving
only where a later feature overwrites one of those constraints. Then apply a
small **compatibility overlay** for repair semantics that are meaningful at the
selected feature depth. The overlay must be resolved and recorded explicitly;
it is not a blind whole-stack cherry-pick because several later repairs target
RTL that does not exist in early feature prefixes.

The historical submodule URL resolves to a local BlackParrot checkout in this
workspace. Initialize only the required top-level dependencies with
`git -c protocol.file.allow=always submodule update --init import/HardFloat import/basejump_stl import/black-parrot import/black-parrot-subsystems`,
then initialize BlackParrot's pinned `external/basejump_stl` in the same way.
Do not use a recursive update: it needlessly fetches SDK submodules such as
WolfSSL. This keeps Git's global file-transport policy intact while recording
and reusing the exact submodule revisions.

Before interpreting any midpoint, prove both endpoints under the same overlay
semantics:

1. the compatibility seed must retain its known Linux boot through `/init`;
2. feature tip + overlay must exhibit the current known non-`/init` result;
3. only then classify a midpoint as **good** (`/init` and `CORE[0] PASS`) or
   **bad** (fails to reach `/init` with a fresh package and run).

## Efficient execution

Each candidate first receives a serialized local preflight: clean static
PYNQ-style build, a normal context-switch smoke gate, and the high-Sv39
Linux-shaped C.LD gate. A candidate that cannot build or fails a local gate is
recorded separately and is not a Linux classification.

A locally clean candidate then requires one routed PYNQ-Z2 implementation and
one fresh-overlay Linux boot. Routing is necessary for a conclusive answer;
it cannot be replaced by simulation. Existing exact-revision packages may be
reused, but no two Vivado jobs or board runs may overlap. A normal fresh
overlay load does not require a power cycle; power-cycle only after an
interrupted, timed-out, or SBI-reset terminal board run.

## Iteration loop and progress reporting

This is the authoritative loop for the replay.  It exists so that an
interrupted investigation can resume at the same checkpoint without treating
a local probe as a Linux result.

1. **Constructing candidate:** start from the last Linux-good feature prefix,
   apply only the selected feature commits plus the explicitly recorded
   compatibility semantics, and commit the isolated overlay.  Push the
   candidate branch before any long-running build so a disposable worktree is
   recoverable.
2. **Local verification:** record the top-level and BlackParrot commits, scan
   the exact archived Linux NBF for custom-CSR collisions, then perform a
   clean traced static-model build and the smallest relevant context and
   privilege/CSR gates.  A local failure is a repair or localization task, not
   a good/bad Linux classification.
3. **FPGA/Linux verification:** route exactly that clean committed candidate
   with static `e_bp_unicore_zynqparrot_cfg`, retain timing/utilization and
   artifact hashes, then use a fresh serialized board run of the archived
   Linux NBF.  Only `/init` plus `CORE[0] PASS` is **good**; a clean,
   reproducible non-`/init` run is **bad**.
4. **Repair or bisect:** if a candidate is not classifiable, make one isolated
   RTL or collateral repair, rerun the matching local gate, and repeat the
   FPGA stage.  If it is classifiable, update the binary-search boundary and
   choose the next midpoint; never stack speculative fixes across multiple
   unclassified feature commits.

If the zero-feature compatibility endpoint itself does not reach `/init`, stop
the replay immediately. Record the run as an endpoint-repair problem, keep the
count at **0/113**, and repair or remove only the compatibility overlay before
selecting any feature midpoint. A feature bisect cannot distinguish a feature
regression from a bad baseline.

`WORK_LOG.md` is the concise dashboard.  Add one row only when the phase,
checkpoint, feature count, compatibility-fix count, or Linux classification
changes.  Each row must name the current commit, show `verified/113` and
`remaining`, and say whether the work is **constructing**, **verifying**,
**repairing**, or **classified good/bad**.  Retain commands and routine
failures in `LINUX_BOOT_STATUS.md` instead.

## Current binary-search boundary (2026-09-04)

The 57/113 midpoint is historical top-level `f8a59c0d` paired with
BlackParrot `11bb7e7d`; the underlying feature source is `7e886ad6e783`.  Its
narrow compatibility overlay migrates the context CSRs to collision-free
`0x800`--`0x802` and restores acyclic I-cache refill semantics while preserving
the midpoint's original behavior.  The top-level checkpoint also carries the
already FPGA-proven AXI Interconnect substitution for this VM's damaged
SmartConnect XIT service and the routed-baseline source-list fix for its
instantiated masked-write memory adapter. It also explicitly restores the
validated static PYNQ dimensions (two resident threads, four logical contexts,
and a 1x1 L2); the preceding historical default used four resident threads and
a 2x2 L2 and failed placement at 63,298 LUTs. Both branches are pushed.

The clean trace-enabled static PYNQ model passed the current-toolchain smoke
and the complete Linux-entry CSR/AMO/BSS gate, including M-to-S entry,
interrupt-CSR clearing, high-DRAM atomics, and high-address code/stack access.
The exact Linux NBF collision scan also passes. Routed job
`20260904T230622Z-f8a59c0d` fit at 41,525 LUTs and 34 BRAM tiles with WNS
+2.684 ns and WHS +0.020 ns. Its package SHA-256 begins `bac66fe5` and its
bitstream SHA-256 begins `e48e2378`.

The fresh hash-verified Linux run printed the complete OpenSBI v1.4 report,
then reached the clean 180-second target limit without a Linux banner while
retiring 989,256 instructions at IPC 0.000879. The retained board transcript
is `/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260904T234431Z-472032.log`.
This classifies midpoint 57 as **bad**, eliminates feature commits 58--113,
and confines the first bad feature to commits 1--57. The next candidate is
midpoint 28/113, feature revision `ea83faa8b42a`.

Midpoint 28 is pushed as top-level `517a7521` with BlackParrot
`70018be9`; its underlying feature source is `ea83faa8b42a`. Because this
revision predates the separate `num_contexts` parameter, its static fit shape
uses two resident threads and a 1x1 L2 without injecting a nonexistent logical
context field. The compatibility overlay retains the two proven frontend
safety fixes, moves the context CSRs to `0x800`--`0x802`, and restores the
pre-feature rule that an I-cache refill completes before the miss state exits.
The clean traced Linux-entry CSR/AMO/high-address gate passes with `CORE PASS`.
The final BlackParrot revision also carries upstream's exact one-line CACC
packet-field correction (`offset` to `vaddr`), needed only because full Vivado
elaborates that disabled historical accelerator source.

Routed job `20260905T001700Z-517a7521` fit at 40,054 LUTs and 34 BRAM tiles,
with WNS +4.772 ns and WHS +0.018 ns. Its package SHA-256 is `49d22ce6…b3ae`
and bitstream SHA-256 is `36e1b254…a662`. The fresh hash-verified archived
Linux run reached `/init`, completed rootfs checks and clean poweroff, and
ended in `CORE[0] PASS`; the retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T005136Z-554143.log`.
Midpoint 28 is therefore **good**, so the first bad feature is in commits
29--57. The next candidate is midpoint 42/113, feature revision
`9883fc6fc970c63dfd78382e431c5950d57bb2b5`; 29 commits remain in the active
good/bad interval.

Midpoint 42 is pushed as top-level `3992f34d` with BlackParrot `cbc0a57e`;
its underlying feature source is `9883fc6fc970c63dfd78382e431c5950d57bb2b5`.
The clean traced Linux-entry privilege/CSR/AMO/high-address gate passed. Routed
job `20260905T010918Z-3992f34d` fit at 40,232 LUTs and 34 BRAM tiles, with WNS
+2.007 ns and WHS +0.009 ns. Its package SHA-256 is
`dce46d233141711f8fcf5e21848f20212e88f6f104f1c74c02c64793d7f4294b`
and bitstream SHA-256 is
`75ce3b8c560add5ae4e2e5a5585e7cec595c0b1c9f398a3b566b1849940674e2`.
The fresh hash-verified archived Linux run reached `/init`, completed rootfs
checks and clean poweroff, and ended in `CORE[0] PASS` after 323,562,456
retired instructions at IPC 0.514494. The retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T014738Z-628035.log`.
Midpoint 42 is therefore **good**, so the first bad feature is in commits
43--57. The next candidate is midpoint 49/113, feature revision
`b6e427fad5cd4877b6bb982221533cfa102b45ec`; 15 commits remain in the active
good/bad interval.

Midpoint 49 is pushed as top-level `5f2cc57b` with BlackParrot `ff6db40b`;
its underlying feature source is `b6e427fad5cd4877b6bb982221533cfa102b45ec`.
The clean traced Linux-entry privilege/CSR/AMO/high-address gate passed. Routed
job `20260905T015855Z-5f2cc57b` fit at 40,358 LUTs and 34 BRAM tiles, with WNS
+3.113 ns and WHS +0.014 ns. Its package SHA-256 is
`4fbf34bcac0c2f8424723d69b474f34ad2ec54e917a84e0465bddd81432a1f97`
and bitstream SHA-256 is
`99d6968872e1a3fd6e45c8b80149be4475e1a58d0cc945022b4efe6751d063c3`.
The fresh hash-verified archived Linux run reached `/init`, completed rootfs
checks and clean poweroff, and ended in `CORE[0] PASS` after 323,132,331
retired instructions at IPC 0.513599. The retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T023647Z-693175.log`.
Midpoint 49 is therefore **good**, so the first bad feature is in commits
50--57. The next candidate is midpoint 53/113; 8 commits remain in the active
good/bad interval.

Midpoint 53 is pushed as top-level `ab7eee9b` with BlackParrot `07a43589`;
its underlying feature source is `5090f64e78711233fa2f23bcb6f05125817e873f`.
The clean traced Linux-entry privilege/CSR/AMO/high-address gate passed. Routed
job `20260905T024758Z-ab7eee9b` fit at 41,495 LUTs and 34 BRAM tiles, with WNS
+3.130 ns and WHS +0.012 ns. Its package SHA-256 is
`6855284551817518724cfed6db7313c467c057446f5c883fdb27aea87685f97e`
and bitstream SHA-256 is
`9e988ab64690d82c1f8598eeb4ed3678cd9187b3a417aa37407b78ef844e1f36`.
The fresh hash-verified archived Linux run printed the complete OpenSBI report
but no Linux banner before the clean 180-second target limit, retiring 989,258
instructions at IPC 0.000879. The retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T032451Z-754414.log`.
Midpoint 53 is therefore **bad**, so the first bad feature is in commits
50--53. The next candidate is midpoint 51/113; 4 commits remain in the active
good/bad interval.

Midpoint 51 is pushed as top-level `11000f6c` with BlackParrot `3cd4ea75`;
its underlying feature source is `00910cd4a50c49f5cb9f1ecdcff2e027e4c2521e`.
Its exact Linux-NBF CSR collision scan, clean 12-worker traced static build,
and Linux-entry privilege/CSR/AMO/high-address gate all passed. Routed job
`20260905T033325Z-11000f6c` fit at 41,295 LUTs and 34 BRAM tiles, with WNS
+3.502 ns and WHS +0.023 ns. Its package SHA-256 is
`3011da16c78c62f6a158b3666bd44ed76158d1c102cbb264a9a4065300a0b8ba`
and bitstream SHA-256 is
`93c5e20997f8948bc347a68b03e6fdc286d085cc4a6108fa96da453d527c396a`.
The fresh hash-verified archived Linux run printed the complete OpenSBI report
but no Linux banner before the clean 180-second target limit, retiring 989,258
instructions at IPC 0.000879. The retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T041141Z-815814.log`.
Midpoint 51 is therefore **bad**, so the first bad feature is commit 50 or 51.
The next candidate is midpoint 50/113; 2 commits remain in the active good/bad
interval.

Midpoint 50 is pushed as top-level `5e55b377` with BlackParrot `f6863917`;
its underlying feature source is `acd832c19b4003c578420c032e4b694b486c433c`.
Its exact Linux-NBF CSR collision scan and clean traced Linux-entry gate passed
before hardware implementation. Routed job `20260905T042410Z-5e55b377` fit at
41,291 LUTs, 15,425 registers, 34 BRAM tiles, and 11 DSPs, with WNS +2.290 ns,
WHS +0.032 ns, and no timing failures. Its package SHA-256 is
`b08a5e36ae3c6f8c1435be5422e3adb5da80fa7f8164c17e8a42e91134754ae1`
and bitstream SHA-256 is
`ea0b8d6ea1d028116da6edd7ba2870fec92a1d6252a79b4570e5cf6ea8e29998`.
The fresh hash-verified archived Linux run reached `/init`, completed rootfs
checks and clean poweroff, and ended in `CORE[0] PASS` after 322,577,322
retired instructions at IPC 0.513384. The retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T050252Z-890139.log`.

Midpoint 50 is therefore **good**, and commit 51,
`00910cd4a50c49f5cb9f1ecdcff2e027e4c2521e` ("Clear FE queue on dcache replay
redirects"), is the exact first Linux regression. That change clears rather
than rolls the ordinary FE issue queue on D-cache miss/replay redirects; later
repair `78837f53e8733c55bc40efc301cb5e8630776542` explicitly removes those ten
lines to preserve DTLB-fill replay. It is independent of the SRAM context
storage mechanics. The next phase carries that narrow repair as a fixed
compatibility overlay while classifying feature commits 52--113.

The first repaired replay candidate, midpoint 81 (`0a77641a` / `a60851d7`),
passed the clean traced Linux-entry gate after carrying global commit 88's
sized physical-address cast. Its synthesis then used 87,933 LUTs because this
historical development point predates the intended banked-SRAM/BRAM-inference
transition. It is therefore not FPGA-classifiable and establishes no Linux
boundary.

Repaired commit 101 is top-level `b7133b51` with BlackParrot `c302d219`. It
omits bad commit 51, replays commits 52--101, and includes the narrow-address
and block-RAM compatibility changes. Its clean traced Linux-entry gate passes
(`CORE PASS`, 9,130 retired), and routed job
`20260905T061726Z-b7133b51` fits at 46,340 LUTs, 19,198 registers, 80 BRAM
tiles, and 11 DSPs with WNS +2.204 ns, TNS 0, and WHS +0.023 ns. The package
SHA-256 is `f695898c038d012b4bb86fc23337342effef36beee8fcc463a5a9e18965444ef`.

Its fresh hash-verified archived-Linux run printed OpenSBI and entered Linux,
then stopped after the two atomic-DMA-pool messages at kernel time 0.089464 s
before the 180-second target limit; it did not reach `/init`. The retained
transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T070054Z-979654.log`.
Repaired commit 101 is therefore **bad**, but its later boundary proves that
omitting commit 51 repairs the original pre-Linux failure and exposes another
regression within commits 52--101.

The next checkpoint is repaired commit 107: top-level `2e283a74` with
BlackParrot `89afc656`. It adds commits 102--107 while preserving the safe
frontend refill compatibility overlay and still omitting bad commit 51. Its
clean traced Linux-entry gate passes (`CORE PASS`, 9,130 retired), with
evidence under `logs/bisect/20260905-repaired-midpoint107/`. Source review
showed those added changes are context-switch-gated and cannot efficiently
classify the ordinary Linux-path regression exposed by commit 101, so routed
job `20260905T071112Z-2e283a74` was stopped cleanly before completion.

The active candidate is instead repaired commit 52: top-level `388de489` with
BlackParrot `9060cac5`. This is exactly proven-good commit 50 plus the
duplicate-I-cache-hit selection change, while still omitting bad commit 51.
Its clean 12-worker traced Linux-entry gate passes (`CORE PASS`, 9,137
retired), with evidence under `logs/bisect/20260905-repaired-commit52/`, and
routed job `20260905T072559Z-388de489` fit at 41,435 LUTs and 34 BRAM tiles
with WNS +0.063 ns, TNS 0, and WHS +0.023 ns. Its package SHA-256 is
`bbdff7edf257633ed68781b9d3bf269e1d62634a828fc872e4c61354b1d188ab`
and bitstream SHA-256 is
`8aae20ef225fa6ec61e42b9572cdbf03e5403c0c6a4acc986c41985b5a964c0a`.
The clean repeated archived-Linux run reached `/init`, completed rootfs
service and CPU/memory checks, powered off normally, and ended in
`CORE[0] PASS` after 321,457,141 retired instructions. Its retained transcript
is `/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T081126Z-1064208.log`.
Repaired commit 52 is therefore **good**.

Repaired commit 53 (`94353d42` / `8ee2dd28`) adds only the streamed-response
UCE credit-accounting change to the repaired good boundary. It routed at
41,483 LUTs and 34 BRAM tiles with WNS +2.343 ns, TNS 0, and WHS +0.023 ns.
Its package SHA-256 is
`25e30c3d0d75858ec68c066c38323a3993c3ab5ef083d69bdcb282e1143accbd`
and bitstream SHA-256 is
`21a92c2939cb9ff77a8dce98364ce453412240676e98127c504a6153d4d58fc5`.
The exact archived-Linux run reached `/init`, completed rootfs checks and
clean poweroff, and ended in `CORE[0] PASS` after 321,991,236 retired
instructions. Its retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T085503Z-1132981.log`.
Repaired commit 53 is therefore **good**; the speculative UCE full-credit
correction is not required and is excluded from the repair chain.

Repaired midpoint 77 (`17e4db38` / `eee61e7f`) passed the clean traced
Linux-entry gate, but exact synthesis required 89,437 of the PYNQ-Z2's 53,200
LUTs (168.11%). This is a historical pre-BRAM representation limit, not a
Linux classification; placement was stopped once the definitive utilization
report existed.

Repaired commit 61 (`98d46c71` / `3d6a10b0`), immediately before commit 62
introduces the large logical-context backing arrays, passed the pinned traced
Linux-entry gate and routed in the normal two-resident/four-logical
configuration. It used 42,116 LUTs and 34 BRAM tiles with WNS +2.293 ns, TNS
0, and WHS +0.031 ns. Package SHA-256 is
`7d53cb38cb007fa505366e40c3d8c8465e337574425b7f74241d31ef70e4c6d7`;
bitstream SHA-256 is
`da3ef196a9b2f73439b670b034f4b646b0a9f295f0643d3d40f8a5194644d7a9`.
The exact archived-Linux run entered Linux but stopped after the two atomic
DMA-pool messages until the clean 180-second target limit. Its transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T101219Z-1201541.log`.
Commit 61 is therefore **bad**, reducing the active bracket to good commit 53 /
bad commit 61 (eight commits 54--61); repaired midpoint 57 is next.

Repaired midpoint 57 (`04f6922c` / `5b3a2dab`) is pushed and passes the clean
12-worker trace-enabled Linux-entry gate with `CORE PASS` and 9,130 retired
instructions. Its exact local evidence is retained under
`logs/bisect/20260905-repaired-commit57/`. It routed at 41,485 LUTs and 34
BRAM tiles with WNS +0.707 ns, TNS 0, and WHS +0.003 ns; package SHA-256 is
`5f53884f34a6ec6d29268fd0cc8d11171573f0880f2cf8115f18f00bf8c9c88a`
and bitstream SHA-256 is
`acbb6d579dd2a00fbbe6c7c72634452ff28434b19e0bfa637134ab9519281477`.
The exact Linux run stopped after the two atomic DMA-pool messages until its
clean 180-second limit; transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T110147Z-1262643.log`.
Commit 57 is **bad**, reducing the bracket to good 53 / bad 57.

Repaired midpoint 55 (`2ff15d44` / `465d3af0`) is pushed and passes the same
clean traced Linux-entry gate (`CORE PASS`, 9,130 retired), with evidence under
`logs/bisect/20260905-repaired-commit55/`. Routed job
`20260905T110918Z-2ff15d44` fit at 41,501 LUTs and 34 BRAM tiles with WNS
+1.226 ns, TNS 0, and WHS +0.023 ns. Its package SHA-256 is
`3034b249fb3ec6b50a79bff588aef7a621ade64fef3b552f1b75b04b687dfd7a`
and bitstream SHA-256 is
`be6729c97edda26467e0897a4dec0340a21cb24092c17a510d8068ce6a252cd1`.
The exact Linux run stopped after the two atomic DMA-pool messages until its
clean 180-second limit; transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T114846Z-1325932.log`.
Commit 55 is **bad**, reducing the bracket to good 53 / bad 55.

Repaired commit 54 (`30a74bfe` / `b740b610`) is pushed and passes the clean
12-worker trace-enabled Linux-entry gate (`CORE PASS`, 9,137 retired), with
program, transcript, and waveform identities under
`logs/bisect/20260905-repaired-commit54/`. Routed job
`20260905T115448Z-30a74bfe` fit at 41,518 LUTs and 34 BRAM tiles with WNS
+1.144 ns, TNS 0, and WHS +0.018 ns. Its package SHA-256 is
`03d98107277c48a9982a05e593ed70f8f40ecd2d16fe55ab7c663a2d2cc7b2ca`
and bitstream SHA-256 is
`d03f203de0cf4526c5cfefbb9cbc622d68924de12fa88e0ebbbc4866d58c8c98`.
The exact archived-Linux run reached `/init`, completed rootfs checks and clean
poweroff, and ended in `CORE[0] PASS` after 323,303,531 retired instructions at
IPC 0.514104. Its transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T123545Z-1389380.log`.
Commit 54 is therefore **good**, and commit 55 (`465d3af0`, "Map resident
ctxtsw targets") is the exact first bad feature commit.

Commit 55 mixes its intended resident-target mapping with an ordinary-path
D-cache replay redirect in `bp_be_director.sv`; Linux can execute the latter
without issuing a context switch. The isolated repair at top-level `4674d583`
and BlackParrot `9a7e0425` retains the resident mapping but restores the
commit-54 director behavior. It passes the clean traced Linux-entry gate, and
routed job `20260905T123843Z-4674d583` fits at 41,523 LUTs and 34 BRAM tiles
with WNS +2.314 ns, WHS +0.023 ns, and no timing failures. Its package SHA-256
is `3dc4299d8babecd68958cdfe1cafa755228a1e0c1cb40744eecb99f0eb93ef36`
and bitstream SHA-256 is
`138b56077779528812a37bd072e64e08362bd2e2f5551eb6e5ccd354552cd578`.

The exact unchanged Linux image then reached `/init`, ran the rootfs checks,
powered off, and ended in `CORE[0] PASS` after 320,192,695 retired
instructions. This proves the ordinary D-cache replay redirect caused the
commit-55 boot stall and that resident target mapping itself can remain. The
retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T132251Z-1465010.log`.
BusyBox's `sysctl` process took one null page fault during that otherwise
terminally successful run, whereas the commit-54 control printed `sysctl: OK`;
a fresh repeat of the exact same hashes printed `sysctl: OK`, completed the
same `/init` and rootfs path, powered off, and ended in `CORE[0] PASS` after
320,437,746 retired instructions. Its retained transcript is
`/home/xilinx/bp-logs/linux-6.6-jhumphri-20250125-20260905T132933Z-1467088.log`.
Commit 55 is therefore repaired; the earlier isolated process fault did not
repeat and is retained as an anomaly rather than hidden.

The same director repair has been applied to the full 113-commit endpoint as
BlackParrot `0ecfeeea` and top-level `fa7c851c`. Its correctly redirected
trace-enabled static model passes the Linux-entry gate, repeated nonresident
integer and FP restore rings, and the nonresident benchmark at 5 warm and 13
cold cycles per switch. Routed job `20260905T132659Z-fa7c851c` definitively
failed detail placement: 62,948 LUTs required versus 53,200 available. The
excess is confined to the last three nonresident-FP preservation/copy commits;
it is the same area class already recorded for the rejected logic-shadow FP
experiments, not a Linux or integer-context failure.

The FPGA-fit endpoint is top-level `7fd64a63` and BlackParrot `b5fe1e93`. It
retains the full dedicated-SRAM GPR context path, physical cycle CSR, frontend
repairs, normal F/D execution, and the proven D-cache replay fix, while leaving
nonresident FP preservation unsupported. A fresh static traced model passes
the Linux-entry sequence and repeated nonresident GPR ring; its physical-cycle
benchmark reports 5.13 resident and 13.16 nonresident cycles/switch, and the
independent FP-execution smoke passes. Routed job
`20260905T141747Z-7fd64a63` is the active fit/Linux proof.

## Refreshed hardware bracket (2026-09-04)

The board and archived Linux payload have been revalidated independently of
the feature stack. The preserved pre-feature package (`c211216c…`, bitstream
`d45f7e3e…`) with its source-matched runner (`76db506e…`) booted through
`/init`, rootfs checks, poweroff, and `CORE[0] PASS`; the unchanged Linux NBF
hash is `994bd900…`.

The routed full feature/repair endpoint (`05b1e786` / BlackParrot
`3df31a94e532`, package `455f7768…`, bitstream `5713f7da…`) was then loaded
with the exact bounded runner (`be771785…`). It printed the complete OpenSBI
v1.4 capability report but no Linux banner before the clean 180-second target
limit, while retiring 1,884,254,103 instructions. This is the current bad
endpoint. The next decisive candidate is the already prepared replay midpoint
`f8a59c0d` / `11bb7e7de7fd` (feature source `7e886ad6e783`), representing
57 of the 113 post-`7331fbd0` feature commits.

## Active endpoint candidate (2026-09-04)

The zero-feature compatibility endpoint is top-level `c12d52f8` paired with
BlackParrot `faa584e9`, both pushed to their named replay branches. It holds
all seven recorded compatibility semantics and migrates the two local
context-smoke guests to the non-colliding `0x800`--`0x802` CSR range.

Progress is **0/113 verified, 113 remaining, compatibility endpoint repair**.
The first fresh serialized archived-Linux run used the package and bitstream
hashes below and reached its clean 180-second target limit with 150,007,078
retired instructions at IPC 0.133339, but no OpenSBI/Linux console or `/init`.
It is an endpoint result, not a feature classification: the overlay itself
must be repaired or reduced before a midpoint can be chosen. The exact Linux
NBF collision scan and clean traced static model build pass; the
CSR isolation and six-switch microbenchmark guests reach `CORE PASS` (12-cycle
warm minimum). The static PYNQ-Z2 implementation also routes cleanly as job
`20260904T152933Z-c12d52f8`: WNS +6.506 ns, TNS 0, WHS +0.013 ns, 50,428 LUTs
(94.79%), and 46 BRAM tiles (32.86%). Its package SHA-256 is
`ea8b3feafc76d35474ac3ed3fcc1dde83ac438c9e8caa017d2c670f73ac8b09` and its
bitstream SHA-256 is `9f8c0c5f8f7a8d0ff61229deff843cf5f17e57cc68e5802679111fa319a2bd91`.
The next proof is one isolated endpoint repair with a matching local gate and
a new fresh-board `/init` result; only then can it set the first binary-search
boundary.

## Current endpoint-repair loop (2026-09-04)

The all-seven-fix overlay is not a valid replay baseline because its zero-feature
endpoint timed out before emitting an OpenSBI or Linux console. The active
repair candidate is therefore top-level `380377a3` on branch
`ce-minimal-overlay-linux-verify`, paired only with BlackParrot `7f41bca9`.
That one commit migrates the context-switch CSRs from Linux-colliding
`0x081`--`0x083` to reserved custom-user `0x800`--`0x802`; it deliberately
does not carry the six later speculative compatibility changes.

This minimal candidate has now been classified **bad** on a fresh board. Its
static PYNQ-Z2 route `20260904T163508Z-380377a3` passed timing and fit (WNS
`+4.580 ns`, WHS `+0.022 ns`, 50,324 LUTs, and 46 BRAM tiles); the verified
package/bitstream hashes are `7463ea1a…473997` and `4d756d07…3afbf`.
The unchanged Linux NBF (`994bd900…821d5`) loaded successfully but reached
its controlled 180-second limit at 150,006,825 retired instructions and IPC
0.133339 without OpenSBI/Linux console output or `/init`. Therefore the
custom-CSR migration is necessary but not sufficient in the CE code shape;
the next iteration must localize its changed decode/commit path rather than
reintroducing any of the six removed overlays or advancing the 113-commit
feature replay.

Use the following loop until the zero-feature endpoint is classifiable:

1. **Verify the minimal candidate locally.** Run a clean static traced model
   build, scan the archived Linux NBF for the retired CSR range, and run the
   migrated CSR-isolation guest. Run the context-switch microbenchmark only
   once the replayed prefix contains its required frontend handoff: the
   zero-feature historical seed is allowed to be nonterminal after proving the
   migration because that benchmark depends on later feature mechanics. Stop
   for a local failure only when it contradicts a gate supported by the
   candidate's historical feature depth; repair only the corresponding change.
2. **Classify it on hardware.** If local gates pass, route the exact committed
   pair with `e_bp_unicore_zynqparrot_cfg`, archive utilization/timing and
   package hashes, then load it after the board-readiness gate and run one
   fresh serialized archived-Linux boot. A board timeout or interrupted run
   requires a power cycle, readiness wait, and overlay reload before any retry.
3. **Choose the smallest next overlay.** If the minimal candidate reaches
   `/init`, it becomes the replay baseline and the feature search begins at
   **0/113 good**. If it fails cleanly, first capture whether the actual
   firmware executes a migrated CSR access or a changed CSR/commit side path;
   then add or remove exactly one CE-shaped compatibility semantic, prove its
   local gate, and repeat step 2. Do not reintroduce the full seven-fix stack
   merely to make a later local test pass.
4. **Resume the feature replay only after classification.** Once a zero-feature
   candidate reaches `/init`, push and retain that exact pair, update the
   scoreboard to `0/113 good`, and test feature midpoints with the same local
   preflight then one route/boot decision. The count changes only for a
   classified feature prefix, never for an overlay repair.

This loop favors a small, attributable RTL delta over optimistic replay speed.
It also keeps slow synthesis and board work off the critical path until a
candidate has passed the inexpensive local checks; all test runs remain
serialized because they share program, trace, and simulator artifacts.

## Result record

For every hardware decision retain: feature revision, overlay patch hash and
manual resolutions, top-level revision, package/bit/NBF hashes, Vivado
utilization and timing, local preflight log, and board transcript. Add only
the resulting good/bad boundary changes to `LINUX_BOOT_BISECT.md` and the
concise `WORK_LOG.md`.
