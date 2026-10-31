This directory preserves two physical Linux runs of the completed instruction-plus-data cache-state oracle. The rotated-order run is the accepted measurement; the fixed-order predecessor is retained because it reproduces the local cache effect while demonstrating why scheduler-inclusive timing needs an ordering control. Neither run measures the current hardware preview mechanism or proves a whole-handoff speedup.

# Combined instruction and data oracle

## Exact platform

- Source base: top-level `c38a25c6e786d270d517db092fbb41df3ea62a54`, BlackParrot `be1967914a4e9659067e96d505d14ec38631b090`.
- PYNQ-Z2 package SHA-256: `1d6c4daecf5066d6b315ece0a5c0c04070d3fada3caa92ee6d0cefac0d194006`.
- Routed bitstream SHA-256: `ee8738cc79bdd894b9be3ddf04eb37ec6b4a66de8ec7a22839489fc12638c9bd`.
- Linux shell NBF SHA-256: `d4b97fc970eb1c54be5b9fef206f90fe8f3b4cbcaf4776d4e5a880f5ed3834f9`.
- Serialized runner SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.
- Accepted rotated-order ELF SHA-256: `458b168285be4608c86ff9aeb4b7bec589ab386eba9d93c42d43d3d9c285d199`.
- Fixed-order diagnostic ELF SHA-256: `3630986f8775fd770aaa52050c9941ecf5611876b28f56a2d3c8099d38132939`.

Both sessions began by atomically restaging the immutable package and NBF, explicitly reloading the overlay, and checking the FPGA manager. Guest ELFs were transferred as bounded gzip/base64 shell commands and hash-checked before execution. Both sessions ended through `poweroff -f` with guest parent/child PASS, `CORE PASS`, `BSG PASS`, and runner exit zero.

## Workload

The child is pinned to CPU 0, executes a 36 KiB straight-line instruction sweep that covers nine complete ways of the 64-set/eight-way I-cache, reads a 256 KiB data buffer, and then blocks. The parent executes either a 2 KiB straight-line target or equal-size decoy and reads either the exact 32-line dependent target chain or a matched decoy. Only after this preparation does it start the wakeup timer. Straight-line noncompressed instructions avoid branch-predictor training as a confound.

Modes are cold, instruction only, data only, and combined. The accepted executable rotates mode labels across balanced eight-trial blocks; every block still contains two observations of every mode. It records 256 measured rows, 64 per mode, after eight warmups. The analyzer rejects nonzero child faults, missing guest/board PASS markers, incorrect mode order, or inconsistent timestamps.

Reproduce the accepted analysis with:

```sh
xz -dc logs/combined-oracle-best-case-20261031/rotated-board-run.log.xz \
  > /tmp/rotated-board-run.log
python3 linux-tests/analyze_scheduler_combined_oracle_best_case.py \
  /tmp/rotated-board-run.log
```

The diagnostic uses `--schedule fixed` after decompression.

## Accepted local result

Rotated-order target-phase medians are 4,409 cold, 4,098 instruction only, 3,111 data only, and 2,839.5 combined cycles. Instruction warming saves a paired 599 code cycles with bootstrap 95% interval `[448.25,733]`. Data warming saves 1,302 data cycles with interval `[1,235.5,1,403]`. Combined warming is 1.55x locally with a paired median saving of 2,044 cycles.

The fixed-order diagnostic independently measures 488 instruction cycles, 1,206 data cycles, and 1,845 combined target cycles; its cold/combined medians are 4,444.5/2,725.5, or 1.63x. These consistent local results show that instruction and data state each help and are approximately additive.

The fixed-order wake-to-useful comparison appeared favorable, but mode identity occupied the same positions in every block. After rotating labels, the wake-to-useful paired interval is `[-5,638.25,15,388.5]` cycles and the round-trip interval is `[-19,186.25,28,416.5]`; neither establishes an end-to-end gain. The 1,845--2,044 local savings are equivalent to only 3.57%--4.00% of the runs' cold wake-to-useful medians.

Median preparation in the accepted run costs roughly 4.45--4.55 thousand cycles, more than the local demand saving. This upper bound is useful only if hardware overlaps warming before or during the switch. It warms shared file-backed user text, not the shared privileged kernel/OpenSBI prefix targeted by the separate instruction-replay work.

## Retained files

- `rotated-board-run.log.xz` and `rotated-summary.json`: accepted reordered run.
- `fixed-order-board-run.log.xz` and `fixed-order-summary.json`: ordering diagnostic.
- `scheduler_combined_oracle_best_case_dynamic`: accepted rotated-order executable.
- `SHA256SUMS`: hashes of all retained files.
