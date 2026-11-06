This directory preserves the first clean simulator evidence for early hardware-sequenced instruction/data replay overlap. It records the exact joint stress, independent regressions, controller gate, and waveform observations used to decide whether the candidate is ready for FPGA implementation.

# Early instruction/data overlap evidence

## Candidate

- Top-level parent before the change: `1f4d6103bf3044472e63917a7e7fc7fff4df9112`
- BlackParrot parent before the change: `df64e5dd9f7bf56b222072bcf6867b14cdeb37a7`
- Top-level branch: `experiment/context-resume-overlap`
- BlackParrot branch: `feat/context-resume-overlap`
- Topology: `NUM_THREADS=2 NUM_CONTEXTS=4`
- Trace: enabled for every full-core run

The D-cache replay controller still emits the instruction-prefix trigger first. Instead of waiting for the I-UCE response state to drain, it observes the configured prefix controller active and releases tagged data on the following controller cycle. This preserves architectural launch order while allowing the independent I-cache and D-cache lanes to overlap.

## Joint stress

The joint test was strengthened from one command to 128 cold/replayed commands plus 32 resident-prefix commands. Each of the first 128 iterations executes `fence.i`, emits one bit-2 tagged command, waits for both controllers to become idle, checks the data target, and executes both instruction targets. The final 32 iterations omit `fence.i`, matching Linux's repeated scheduler-trigger shape and forcing the prefix controller through its resident-drop path. The complete test requires 160 tagged triggers with no drops, 256 accepted instruction entries, 64 resident instruction drops, 160 instruction triggers with no drops, and correct target contents.

Command:

```text
make -C testing clean
make -C testing -j12 run-mt_dcache_icache_follow_replay_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

The clean-build 128-command result reaches the dedicated guest marker, `CORE PASS`, host `BSG PASS`, and `VALID RUN` at 11,690 retired instructions. `joint-128.run.log`, `joint-128.prog.riscv`, `joint-128.prog.nbf`, and `joint-128.dump.fst` are immutable copies made before the shared simulator artifacts were reused. The subsequent software-only resident-prefix extension passes the same terminal gates at 13,736 retired instructions; its exact artifacts use the `resident-prefix` prefix.

## Waveform proof

The relevant signal identities are:

```text
D'   blackparrot.dcache_replay_follow_trigger_lo
A'   blackparrot.dcache_replay_v_lo
g&   blackparrot.icache_replay_lane_v_lo
uZ!  blackparrot.icache_uce.prefetch_valid_r[3:0]
aU!  blackparrot.dcache_replay_ctrl.follow_wait_r
bU!  blackparrot.dcache_replay_ctrl.follow_seen_r
tU!  blackparrot.dcache_replay_ctrl.follow_launched
```

For the first observed combined command, the instruction follow pulse occurs at trace time 337125000. Prefix activity is registered at 337225000; the first instruction replay is offered at 337325000. At 337375000 the first I-UCE slot becomes occupied and tagged data is offered in the same trace timestamp. The second instruction replay is offered at 337525000 while that slot remains occupied. A complete scan of the cold/replayed phase finds 128 tagged-data rising edges and all 128 occur with nonzero I-UCE prefix occupancy. In the extended trace, the additional 32 resident-prefix commands release data with zero I-UCE occupancy after the prefix controller identifies both lines as already resident; all complete and the architectural counters report exactly 64 resident drops. `waveform-summary.txt` retains both scan results.

## Independent regressions

The existing data-only regression passes its dedicated `tagged 32-line physical data replay` marker, `CORE PASS`, host `BSG PASS`, and `VALID RUN`:

```text
make -C testing -j12 run-mt_dcache_replay_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

The existing instruction-only regression passes its dedicated `shared-prefix and physical I-cache replay` marker, `CORE PASS`, host `BSG PASS`, and `VALID RUN`:

```text
make -C testing -j12 run-mt_icache_replay_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

Their exact logs, NBFs, ELFs, and FSTs are preserved with `data-only` and `instruction-only` prefixes. The simulator's known post-PASS GPIO final-block assertion is accepted only after the harness reports `VALID RUN`.

The standalone controller gate also passes command queuing, delay/gap/backpressure, accounting, instruction-first launch, early overlap, and empty-prefix release. Its build and run transcripts are under `controller-gate/`.

## Scope

This proves repeated command accounting, target correctness, architectural instruction-first ordering, and actual I/D overlap in simulation. It does not prove Linux correctness, eliminate the physical corruption seen with the fully drained predecessor, or establish a performance gain. Those require a routed image and recovered same-image instruction-only, data-only, and joint Linux runs.
