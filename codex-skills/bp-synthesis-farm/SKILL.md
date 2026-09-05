---
name: bp-synthesis-farm
description: Coordinate isolated BlackParrot PYNQ-Z2 Vivado builds across the configured build VMs, including probing capacity, launching immutable revision pairs, monitoring jobs, and collecting verified artifacts without touching the FPGA board.
---

This skill defines the reusable multi-VM synthesis workflow for this BlackParrot checkout. It exists to shorten Linux/RTL bisects while keeping every routed result tied to exact source revisions and leaving live-board tests serialized.

# BlackParrot Synthesis Farm

Use the build farm for independent PYNQ-Z2 implementation candidates. Use
`bp-fpga-synthesis` for the acceptance criteria and deployment steps, and use
`bp-parallel-safe-runs` to confirm that candidates have disjoint remote source,
build, and log directories.

## Invariants

- Each builder may run at most one Vivado implementation at a time.
- Separate builders may synthesize different immutable candidates concurrently.
- Always use `CFG=e_bp_unicore_zynqparrot_cfg` for the context-cache PYNQ image.
- Identify a candidate by both its exact top-level and BlackParrot commits.
- Use a clean detached remote worktree; never build the builder's dirty coordination checkout.
- Use the current coordination checkout's maintained synthesis scripts while
  `ZP_REPO_DIR` points at the immutable historical source worktree.
- Use the builder's advertised worker count unless memory or tool evidence requires a lower cap.
- Never load an overlay or run `control-program` from a synthesis worker. FPGA
  deployment and Linux execution remain serialized on the single board.
- A yielded SSH or build command is still active: retain its session identifier
  and poll it to a real exit code before consuming its output or scheduling a
  dependent operation.

## Builders

The controller knows `bp1`, `bp2`, and `bp3`. Probe them before scheduling:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh probe all
```

`bp1` has 12 workers. `bp2` and `bp3` have 64 workers and enough memory for one
Vivado job apiece. The controller uses SSH host aliases internally and keeps
credentials out of tracked files.

## Launch And Monitor

When preparing a top-level candidate, stage its BlackParrot gitlink directly
from the source worktree instead of copying an object ID by hand:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh link \
  /path/to/top-worktree /path/to/black-parrot-worktree
```

The command refuses to overwrite an already modified gitlink and verifies the
exact indexed object. Review and commit the staged gitlink from the top-level
worktree before launching the build.

Launch with pushed branch names so the remote can fetch and independently
resolve both commits:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh launch \
  bp2 candidate-name top-branch black-parrot-branch
```

The controller verifies that the BlackParrot gitlink in the top revision equals
the fetched BlackParrot revision, materializes all pinned nested submodules,
links only the ignored dependency prefixes, runs build readiness, and starts the
existing background synthesis launcher. It records a local manifest under
`logs/fpga-farm/`.

Use `list`, `status`, and `collect` for subsequent operations:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh list all
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh status bp2 <job-id> <remote-log-root>
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh collect bp2 <job-id> <remote-log-root>
```

Only collect a `PASS` job. Re-run the package verifier locally before staging an
artifact to the board.

## Scheduling A Bisect

Use different builders for independent ordered candidates, but interpret them
in feature order. A later candidate passing does not make an earlier failure
irrelevant, and a later failure does not localize the first bad change until the
nearest earlier candidate is classified. Keep the board queue ordered around
the current good/bad boundary and record only meaningful classifications in
`WORK_LOG.md`.
