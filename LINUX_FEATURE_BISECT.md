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
| Bad repaired endpoint | `1c42e9f2` | Feature tip plus the current compatibility stack; FPGA reaches the later unaligned-access boundary but not `/init`. |

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

## Current midpoint checkpoint (2026-09-03)

The first replay midpoint is BlackParrot `a9ee78ab1ea` (feature source
`7e886ad6e783`) plus the recorded narrow I-cache compatibility overlay. The
first routed attempt found a real combinational FE/UCE I-cache-refill loop
caused by the overlay's context-switch abort signal; it was deliberately
stopped and is not a valid FPGA candidate. The repaired overlay holds
`miss_abort` low, preserving redirect/context state while waiting for a refill
to finish. After restoring the midpoint's pinned nested BaseJump revision
(`4db526e68d`), its clean traced two-resident/four-context PYNQ-style model
passed the toolchain smoke and Linux-entry CSR/AMO/BSS gate.

Before the corrected FPGA route completed, an exact-NBF CSR preflight found
nine Linux instructions addressed to `0x081`--`0x083`, the midpoint's
context-switch CSR range. This makes the candidate inherently incompatible
with the archived Linux image, independently of the remaining frontend logic;
the route was cleanly stopped and no board result will be attributed to this
revision. The isolated migration overlay has since moved all 31 decode and
documentation references to the non-colliding `0x800`--`0x802` range: the
exact NBF preflight is collision-free and the static Linux-entry gate passes.
That early feature prefix still lacks its later frontend handoff and therefore
times out in the context-switch smoke; it is not a full feature acceptance or
a routed Linux classification. Future historical replay candidates must carry
both the acyclic refill behavior and the migrated CSR interface before a
routed Linux classification.

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
   **0/113 good**. If it fails cleanly, add or remove exactly one compatibility
   semantic that exists at this historical depth, prove its local gate, and
   repeat step 2. Do not reintroduce the full seven-fix stack merely to make a
   later local test pass.
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
