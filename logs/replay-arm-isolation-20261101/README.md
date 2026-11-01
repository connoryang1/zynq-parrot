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

## Complete isolated mode-6 matrix

After recovery through the documented private outlet fallback, the board passed readiness at 94 seconds, reloaded exact bitstream `e97e0517...2381`, and reported FPGA state `operating`. The exact NBF, corrected ELF, and transfer hashes matched. All eight `wake-trigger target fifo isolated` groups then completed 512 accepted trials apiece, with 13 asynchronous attempts filtered and repeated, eight zero cell exits, runner RC zero, and final child/parent/CORE/BSG PASS.

The first attempt to inspect the fallback script with URL redaction had a shell-quoting syntax error and executed no controller request. A corrected redaction-only inspection confirmed its two PUT operations without exposing the endpoint; the maintained power helper then performed the accepted cycle. Keep endpoint parsing and use inside one shell process so the credential never enters command output or tracked evidence.

Across 4,096 accepted trials, the stratified paired result does not show a cold first-resume gain. Wake-to-entry is `-1058.75 [-1886.75,580.25]` saved cycles, the four local data loads are `0 [-0.5,0]`, and wake-to-load is `-993.25 [-1834.75,822.5]`; negative values mean replay is slower. The complete roundtrip regresses by 7,838.5 cycles, with saved-cycle interval `[-9071.5,-5199.5]`. Five of eight individual groups have roundtrip intervals wholly below zero.

The chronology check continues to validate isolation: trailing-disabled minus leading-disabled wake-to-load is `-16 [-80,37.5]`, unlike the historical persistent matrix's −888-cycle position shift. The first half is neutral at −59.5 paired wake-to-load cycles, while the second half is −1294.75; quarter signs vary. Thus the unresolved first-resume result is not promoted to a slowdown claim, but the full-return regression is stable enough to reject per-switch clear-and-refill mode 6 as a performance policy for this benchmark.

The next discriminator is the same isolated eight-group matrix with selection-time mode 5. If it also regresses on roundtrip, the cold replay burst or its cache/transport effects dominate; if it does not, the early successful-wakeup launch creates the harmful tail. The fresh-boot persistent-pair A/B remains separately necessary because production retained lines avoid per-switch refill.

Evidence hashes are:

```text
compressed raw: 93597e25b29c73a6f4a3d8465bb1a1c297fbd1e80c3ec5599ddea12621df3f91
raw content:    2b721c1cd3247e878f061769a3944e3cd01a02c1841115aafdfcb389c698d2eb
runner status:  bb3d9acde5fcf1275596272c593a9e15e887114c4cc57f1b7df7bf6ed6114324
primary result: bfb253a24128b6ae4bbeaa3c30ac5fb450ba66e4ba1aabdf8abe135eceedb920
chronology:     d9803d617f775cee6b928c788a642c8b9de1f35e51e8dab4cdaa448d5e9f5680
```

## Isolated mode-5 timing control

After a second valid recovery and exact overlay reload, the same eight groups ran with selection-time mode 5 and no other benchmark or image change. All 4,096 trials were accepted after 14 filtered attempts; all cells exited zero and the run ended with terminal PASS.

Mode 5 reproduces mode 6: wake-to-load is `-942.5 [-1746.75,913]` saved cycles, local loads are exactly `0 [0,0]`, and roundtrip is `-7514.5 [-9101.5,-4552.5]`. A direct 20,000-sample mode-6-minus-mode-5 comparison is unresolved for every endpoint: `-50.75 [-2080.25,1953]` wake-to-load and `-324 [-3549.5,2623]` roundtrip. The earlier wake trigger therefore neither fixes nor uniquely causes the regression; the forced cold replay/refill epoch is the common mechanism.

The mode-5 chronology has a small resolved disabled-position drift of `65.5 [4.5,118]` cycles at wake-to-load, far below the historical −888 cycles and opposite in sign. Its paired first-resume interval remains broad, while the roundtrip regression is resolved in both halves. Treat this as a minor scheduler-phase residual rather than replay-buffer leakage; the fresh-boot persistent protocol avoids interleaved arms entirely.

Mode-5 evidence hashes are:

```text
compressed raw: 74051576d12ebd1819bf44e5cc15d7d82f6980d9957a6b10a9009aac3e9f31f3
raw content:    91b01ca3c7407c3c83c7750d590fc481401b87e49eaf257d620b5814aa9d6928
runner status:  cb30ecd366ba223fcfc44c790aba05d32d182bcd5af7917e41b1ea03aac7a328
primary result: 32dffa6cb2ddfade6cd9952b064868a27944c17029479144fec6498b558d22fa
chronology:     012b16d0e4912649153f77a026c0be4d1d3dccc4be9f64ff4cd5365839788851
mode6-mode5:    7ce6131238a146b4d66ee8c70574cfa8ceda97612a6fed31e4fa80450d7d86c7
```

## Acceptance plan and limits

The complete isolated mode-6 matrix and mode-5 timing control are now accepted. The fresh-boot persistent-pair A/B remains pending and answers the production-retention question that per-trial invalidation intentionally cannot. Every run ends through guest shutdown, so the board must be physically power-cycled, pass readiness, and reload the exact overlay before another launch; use the documented local outlet fallback without exposing its endpoint.

`fence.i` deliberately creates a cold-instruction best case and clears the ordinary local I-cache as well as the advisory buffer. It is a mechanism ceiling, not a claim about the natural temperature of general Linux context switches. A later representative workload must use a production clear/generation policy rather than issuing `fence.i` on every handoff.
