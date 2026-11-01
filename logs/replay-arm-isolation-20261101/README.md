This directory documents a cross-trial contamination found in the interleaved instruction-replay benchmark and the software-only correction prepared for the next FPGA run. The historical measurements remain valid timing records, but nonempty-table matrices did not compare a clean replay-disabled arm against replay because detached lines persist across trials.

# Replay-arm isolation audit

## Confirmed benchmark mismatch

The physical benchmark uses repeated `[off,on,on,off]` blocks and previously executed no `fence.i` between trials. The detached I-cache buffer independently retains a completed line until replacement, reset, or accepted `fence.i`; its hit lookup has no per-task preview-mode gate. The shared-prefix table contains 16 lines and the advisory buffer contains 16 entries, so an enabled warmup can make those lines visible to later disabled trials.

This is not speculation about cache timing. It follows directly from these maintained sources:

- `linux-tests/scheduler_physical_preview_benchmark.c` alternated arms without an instruction invalidation.
- `bp_fe_icache.sv` retains `replay_buffer_alloc_r` and complete beat masks, clears them on `replay_buffer_inval`, and performs advisory lookup without consulting the Linux mode.
- `mt_icache_replay_test.c` explicitly verifies that a repeated trigger sees all four completed lines resident and that `fence.i` invalidates them.

The one-shot RL-081 demand traces remain useful: the enabled trace followed 16 disabled warmups, so it demonstrated that the first early trigger removed 13 of 16 selected demand misses. The 512-trial performance matrix has different state after its alternating warmups and therefore cannot assign its paired 325.25-cycle difference to the full replay feature versus an unexposed buffer.

## Chronology evidence

`mode6-wakeup-prefix16-chronology.json` reanalyzes the exact retained eight-group FPGA matrix with position-specific contrasts. Its primary 20,000-sample aggregate result is unchanged elsewhere; this diagnostic uses 2,000 stratified bootstrap samples.

For wake-to-load:

| Window | Paired saved cycles | 95% interval | First off minus first on | Trailing off minus second on |
| --- | ---: | ---: | ---: | ---: |
| Quarter 1 | 571.25 | [325, 764.5] | 126.5 | 198.5 |
| Quarter 2 | 277.25 | [42.5, 521] | 60 | 158 |
| Quarter 3 | 133.25 | [-178.75, 406.5] | -27 | 225 |
| Quarter 4 | 299.75 | [-73.5, 614.5] | 49 | -7 |
| First half | 419 | [235, 577.5] | 100.5 | 186.5 |
| Second half | 203.75 | [17, 402] | 30 | 147.5 |
| Complete | 325.25 | [176.5, 443.5] | 52 | 172.5 |

The point effect falls from 419 cycles in the first half to 203.75 in the second. Across the complete matrix, the first off-versus-on contrast is unresolved around 52 cycles, while the on-followed trailing contrast is 172.5 cycles and the trailing disabled position is 888 cycles faster in median than the leading disabled position. This ordering is consistent with cross-trial cache/state carryover but does not identify replay-buffer persistence as the only cause; scheduler phase and ordinary cache warmth remain alternatives. The source-level persistence proof is why the old matrix is rejected as a clean A/B, not the exploratory chronology interval alone.

## Corrected experiment

The benchmark now accepts a fifth `persistent|isolated` argument. `isolated` executes `fence.i` symmetrically after cache-pressure preparation and before enabling either arm, outside the timestamped handoff. The guest program retains persistent behavior as its direct-command default for reproduction, while the serialized runner defaults to `--replay-state isolated` and records the choice in its status JSON.

The exact clean build uses Buildroot GCC 13.2.0 and the maintained `rv64imafdc_zicsr_zifencei` flags:

```text
benchmark ELF SHA-256: e4dd1fccae686b3f0982bdcf5cc6092d08686d229bcfb29aeaa74da72de3a4e8
transfer SHA-256:      b2a8aa36f35815731ed84f620c9b92b9a350dbd20a2751d5f38741c828fc0566
```

Disassembly confirms the conditional `fence.i` at `0x11274`, after `fence rw,rw` and the isolation-mode branch and before the preview-enable `prctl` setup. Thirty-eight focused runner/analyzer tests pass.

The first test invocation from repository root failed only because the test modules use sibling imports. The accepted invocation is from `linux-tests/`:

```text
python3 -m unittest test_run_scheduler_physical_preview_sweep.py \
  test_scheduler_physical_preview_sweep.py
Ran 38 tests ... OK
```

## FPGA feasibility

After an externally completed power cycle, the board passed the PYNQ readiness gate at 5,429 seconds uptime, loaded exact bitstream `e97e0517...2381`, and reported the FPGA operating. Exact mode-6 NBF `5e42c2f6...5d2bd`, control program `2dd9c411...7c30`, benchmark ELF `e4dd1fcc...a4e8`, and transfer `b2a8aa36...0566` all matched before launch. No board lock or competing control process was present.

One predeclared group-7 `wake-trigger target fifo isolated` cell completed 512 accepted trials with zero retries, runner exit zero, and final parent/child/CORE/BSG PASS. Its paired results are:

- wake-to-entry: `1897.75 [-1614.25,6734.5]` cycles saved;
- four dependent loads: `-1.25 [-4,0]` cycles saved;
- wake-to-load: `2424.25 [-1032.5,6734]` cycles saved;
- roundtrip: `-1427.25 [-7767.75,5356]` cycles saved.

The isolated wake-to-load point estimate is about 7.8 times the contaminated persistent-matrix point estimate, but every whole-handoff interval crosses zero in this one noisy cache-set group. It is feasibility and evidence of upside, not a speedup claim.

The isolation-specific position check is more decisive. Leading-versus-trailing disabled wake-to-load differs by only `39 [-81,107.5]` cycles, compared with the historical persistent matrix's `-888`-cycle pooled median. The sign counts are also balanced at 67 positive, 60 negative, and one zero block. This verifies that symmetric `fence.i` removed the systematic disabled-position carryover in the feasibility cell.

Exact compressed raw/status, 20,000-sample partial-cell analysis, and 5,000-sample position analysis are retained under `physical-sweep/` with SHA-256 values `93f52385...6417`, `4eba9ac0...872e`, `b82bbef9...87f2f`, and `3146b082...5198`. The decompressed raw transcript hashes to `a1df868a...f5b1`.

## Acceptance plan and limits

The complete eight-group isolated mode-6 matrix, isolated mode-5 selection-time control, and independent isolated mode-6 replication remain pending. A valid result must retain exact ELF/NBF/bitstream hashes, final runner/CORE/BSG PASS, and show that the full chronology analyzer remains free of a systematic arm-position effect. The feasibility run ended through guest shutdown, so the board must be physically power-cycled and the overlay reloaded before another launch; the current shell still lacks the private power-controller URL.

`fence.i` deliberately creates a cold-instruction best case and clears the ordinary local I-cache as well as the advisory buffer. It is a mechanism ceiling, not a claim about the natural temperature of general Linux context switches. A later representative workload must use a production clear/generation policy rather than issuing `fence.i` on every handoff.
