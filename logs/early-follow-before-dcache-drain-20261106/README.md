This directory preserves the simulator evidence for launching a followed instruction prefix without waiting for unrelated D-UCE traffic. It binds the controller invariant, clean full-core regressions, and contention waveform to the candidate that moves the D-UCE drain gate from instruction launch to data release.

# Early follow before D-UCE drain

## Motivation

Two independent FPGA boots of the accepted early-overlap route resolve a `4219.25`-cycle instruction-only wake-to-first-use gain, while two joint 32-line boots retain only the local data benefit and leave wake-to-first-use unresolved. A four-line joint control also fails to recover the instruction effect, excluding replay volume as the primary cause. RTL inspection found that `follow_ready` still waited for D-UCE outstanding and completed-response state inherited from the older data-first sequencer, so ordinary kernel data traffic could postpone the independent instruction trigger.

## Candidate invariant

The instruction trigger now depends only on the followed command being armed and the instruction-prefix controller being ready. Followed data still waits for the prefix-active observation and for older D-UCE state to drain, preserving command order without charging instruction replay for D-cache traffic.

The directed controller command is:

```text
python3 testing/rtl/run_dcache_replay_ctrl.py --out <isolated-output>
```

It passes with two modeled outstanding D-UCE slots and a completed response present at the instruction-trigger boundary, then requires data to remain hidden until those inputs clear. An initial invocation without the mandatory `--out` argument printed usage and performed no build; future runs must always supply an isolated output directory.

The first host-test invocation from the repository root omitted `linux-tests` from Python's module search path and therefore ran zero tests. The corrected command uses `PYTHONPATH=linux-tests`; all 42 selected analyzer/runner tests pass. The synthesis-farm `link` helper also refused the already-advanced nested submodule, as designed for separate BP worktrees, so the exact committed gitlink was staged manually and verified against `git -C import/black-parrot rev-parse HEAD`.

## Full-core gates

After separate testing and simulator cleans, the clean trace-enabled joint gate passes its dedicated marker, CORE/host PASS, and maintained `VALID RUN` verdict at 13,736 retired instructions. The independent data-only and instruction-only regressions pass at 8,767 and 20,608 retired instructions. An extended joint program then adds a real-controller contention phase and passes at 14,454 retired instructions with 162 data commands, 161 instruction follows, no trigger drops, 258 accepted cold instruction entries, and 64 resident suppressions.

The known DPI-GPIO final-block assertion occurs only after guest, CORE, and host PASS; the maintained validator accepts the same teardown behavior on the baseline.

## Contention waveform

The first contention command produces this ordered sequence in `raw/joint-contention-dump.fst`:

```text
time=337850000 downstream_outstanding=001
time=337925000 instruction_follow=1 downstream_outstanding=001
time=338125000 instruction_replay=1
time=338325000 instruction_replay=1
time=338500000 downstream_outstanding=000 data_release=1
time=338625000 followed_data_replay=1
```

Thus the real I-UCE receives both prefix entries while an older D-UCE request remains outstanding, and followed data waits until that older state drains. `waveform-summary.txt` records the signal identifiers, exact transition scan, and artifact hashes.

## Scope

This is simulator correctness and mechanism evidence, not a Linux speedup. A routed image and recovered-board joint replication are required to determine whether removing the stale launch gate restores the physical instruction benefit without regressing the resolved data benefit.
