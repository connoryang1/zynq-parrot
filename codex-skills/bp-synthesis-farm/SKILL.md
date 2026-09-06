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
- Use the controller's measured Vivado thread default unless new tool evidence justifies an override.
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

`bp1` has 12 host cores. `bp2` and `bp3` have 64 host cores and enough memory
for one Vivado job apiece. Measured Vivado 2024.2 runs cap this design at seven
synthesis and eight implementation workers, so the controller defaults every
builder to eight Vivado threads; the faster 64-core hosts still reduce a route
from roughly 37 to 17.5 minutes through better host performance. Candidate-level
parallelism across VMs is the meaningful throughput gain. The controller uses
SSH host aliases internally and keeps credentials out of tracked files.

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

First admit the candidate. An admission is an immutable local record keyed to
the builder, label, and both pushed branches. Priority is numeric with `1` as
the highest priority; use a distinct label if the hypothesis changes:

```bash
BP_SYNTH_DECISION='Does the FE completion wait fix Linux handoff while retaining fit?' \
BP_SYNTH_CHEAPER_GATES='The local reproducer fails before and passes after, but cannot prove routed timing or board behavior.' \
BP_SYNTH_PASS_ACTION='Run the minimal Linux handoff probe, then reuse this image for the full Linux test and benchmark.' \
BP_SYNTH_FAIL_ACTION='Do not route variants; inspect the failed fit/timing report or return to the FE handshake trace.' \
  codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh admit \
    bp2 fe-completion-wait top-branch black-parrot-branch 1
```

Each field must be a non-empty single-line statement. The controller refuses
to replace or reuse an admission, so the resulting evidence cannot silently be
retargeted to another branch or candidate. It also prints the complete plan
before any remote work begins. Review it without contacting a builder with:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh plan \
  bp2 fe-completion-wait top-branch black-parrot-branch
```

After admission, launch with the same builder, label, and pushed branch names
so the remote can fetch and independently resolve both commits:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh launch \
  bp2 fe-completion-wait top-branch black-parrot-branch
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

If new evidence makes a running candidate irrelevant, cancel that exact job
and verify its Vivado processes are gone before reusing the builder:

```bash
codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh cancel \
  bp2 <job-id> <remote-log-root>
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

## Build Admission

Do not occupy a builder merely because it is idle. The required admission must
state the single decision the result will make, why neither an existing artifact
nor a cheaper local gate answers it, and the next action for both pass and fail.
Prefer the nearest untested boundary candidate. Admit at most one conditional
follow-up build in parallel, and only when it isolates a specific line-level
hypothesis and remains useful under either result of the boundary test. Archive
completed later checkpoints without spending board time on them until all
earlier changes are classified.
