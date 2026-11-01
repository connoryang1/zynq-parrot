This directory preserves the accepted physical Linux upper-bound test for cross-process data warming. It compares a cold first-use footprint with perfect, fully completed target-line warming before the timed wakeup. The result proves local data headroom but is not a measurement of the current four-address hardware preview mechanism.

# Completed-data best-case oracle

## Exact configuration

- Source branch before this evidence commit: top-level `e6f106f8d055749a149e456906ea8f4e426f1366`, BlackParrot `be1967914a4e9659067e96d505d14ec38631b090`.
- PYNQ-Z2 package SHA-256: `1d6c4daecf5066d6b315ece0a5c0c04070d3fada3caa92ee6d0cefac0d194006`.
- Routed bitstream SHA-256: `ee8738cc79bdd894b9be3ddf04eb37ec6b4a66de8ec7a22839489fc12638c9bd`.
- Linux shell NBF SHA-256: `d4b97fc970eb1c54be5b9fef206f90fe8f3b4cbcaf4776d4e5a880f5ed3834f9`.
- Serialized runner SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`.
- Accepted benchmark ELF SHA-256: `96dc6532c815ed3cce418eda406633255a380c96223e0c156ccba421a4721e61`.
- Vivado 2024.2 route: configuration `e_bp_unicore_zynqparrot_prefetch5_cfg`, WNS/TNS `+0.029/0 ns`, WHS/THS `+0.032/0 ns`, 50,923/53,200 LUTs, and 85.5/140 BRAM tiles.

The package was verified, atomically staged, and loaded with the maintained FPGA scripts. The guest executable was transferred in bounded shell lines and its SHA-256 was checked before execution. The accepted run ended through `poweroff -f` with `CORE PASS`, `BSG PASS`, and runner exit zero.

## Benchmark and acceptance

The child and parent are separate Linux processes pinned to CPU 0. Before every trial, the child reads a 256 KiB eviction buffer and blocks. The parent then reads either an equal-sized decoy footprint or the exact MAP_SHARED target footprint; only after that read and a fence does it start the handoff timer and wake the child. Oracle preparation cost is reported separately and excluded from the timed interval, so the experiment assumes perfect address selection, completed warming, and complete overlap.

Four conditions cover 16 and 32 lines, with one line on each private page, using independent reads or a serialized dependent chain. Each condition has eight warmups and 128 measured trials in repeated `[cold,oracle,oracle,cold]` blocks. The analyzer requires ordered rows, balanced blocks, consistent timestamps, zero child minor faults, both guest PASS markers, and final board `CORE PASS`/`BSG PASS` markers.

Reproduce the analysis by decompressing the retained transcript first:

```sh
xz -dc logs/data-oracle-best-case-20261031/board-run.log.xz > /tmp/board-run.log
python3 linux-tests/analyze_scheduler_data_oracle_best_case.py /tmp/board-run.log
```

## Result and limit

All four target-load comparisons have paired bootstrap intervals excluding zero. The cold/oracle load medians are 1,287.5/776.5 cycles for 16 independent, 1,544/969 for 16 dependent, 2,477.5/1,356 for 32 independent, and 2,830.5/1,582.5 for 32 dependent.

The strongest 32-line dependent case is 1.79x locally. Its block-paired median saving is 1,265.25 cycles with a 20,000-resample 95% interval of `[1,245,1,294]`. That causal saving is only 2.66% of the 47,616.5-cycle cold wake-to-load median. Scheduler entry and round-trip intervals have much larger variance and are not attributed to warming, even where their unpaired medians appear favorable.

The median oracle preparation itself costs 2,940 cycles in the 32-dependent case, more than the 1,265-cycle demand saving. The design therefore needs to overlap warming before or during the switch; synchronously replaying ordinary loads inside the critical path would lose. This test also does not predict addresses, issue hardware hints, or establish that the current 2 KiB-reachable L2 can retain more than 32 lines.

## Rejected prefault diagnostic

`parent-prefault-rejected.log.xz` is an otherwise-passing predecessor that reports one or two child minor faults per condition. Parent-side population of the anonymous shared result array did not establish all child PTEs after `fork()`. Prefaulting that array from the child before warmup produced the accepted zero-fault run. Future fork-based timing tests must establish mappings in the measured process rather than infer them from parent touches.

## Retained files

- `board-run.log.xz`: accepted serialized board transcript.
- `summary.json`: accepted analyzer output.
- `scheduler_data_oracle_best_case_dynamic`: exact guest ELF.
- `parent-prefault-rejected.log.xz`: rejected diagnostic that motivated child-side prefaulting.
- `SHA256SUMS`: hashes of the retained files.
