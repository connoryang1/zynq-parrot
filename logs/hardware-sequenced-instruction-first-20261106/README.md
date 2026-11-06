This directory preserves the first clean full-core evidence for hardware-sequenced instruction-first replay. It records correctness and ordering only; it does not establish FPGA timing fit or a Linux performance gain.

# Instruction-first full-core evidence

The trace came from a clean two-thread/four-context run:

```text
make -C testing clean
make -C testing run-mt_dcache_icache_follow_replay_test \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

The guest printed `[BSG-PASS] hardware-sequenced instruction then data replay`, followed by `CORE[0] PASS` and the host `BSG PASS`. The known GPIO DPI teardown assertion happened only after those terminal markers, and the maintained wrapper classified the run as valid.

## Waveform result

`full-core-ordering-transitions.txt` is a compact extraction from `full-core-ordering.fst`. Its identifiers map to these signals:

- `D'`: instruction-prefix trigger
- `g&`: prefix replay valid
- `JU!`: prefix-controller busy
- `E'`: I-UCE outstanding count
- `F'`: I-UCE completed-response count
- `A'`: data replay valid
- `bU!` through `fU!`: instruction-follow controller state
- `xU!`: fully drained decision

The command asserts exactly one instruction trigger at time `237925000`. Two instruction entries replay at `238125000` and `238325000`; I-UCE occupancy reaches two, the prefix controller becomes idle, and occupancy finally reaches zero at `242875000`. The first data replay does not assert until `243025000`, 150000 trace units (three core edges) later. No data replay occurs before or during the instruction replay, and no second instruction trigger appears.

The standalone controller gate also passes configured-prefix backpressure, active-prefix wait, delayed I-UCE allocation, outstanding and completed response drain, queued-command order, and the zero-configured-prefix release case. Independent full-core regressions preserve `[BSG-PASS] tagged 32-line physical data replay` and `[BSG-PASS] shared-prefix and physical I-cache replay`, each followed by guest, core, and host PASS.

The first data-only regression trace was accidentally overwritten by the following instruction-only run. No conclusion depends on that lost trace: the data regression was immediately rerun with the same command and its replacement trace is retained here. Future trace sequences must copy and hash each closed FST before launching the next run, even when the preceding terminal markers already passed.

A later board-collateral preflight first invoked two unittest files by path from the repository root; their sibling imports were consequently absent from Python's module path and both failed before test execution. The corrected discovery command, `python3 -m unittest discover -s linux-tests -p 'test_*scheduler_tagged_replay*.py'`, runs all 41 matching tests successfully. Use discovery with `-s linux-tests` for this suite rather than treating the hyphenated directory as an importable package.

## Artifact hashes

```text
d9555b198163fa65689db714a5d6a331549478fc1821a589cf199a5a43c5bed8  full-core-ordering.fst
7b8e40eb6f12abf6500893e049eeb4d8f2b657c715e19901bbec36aed3090dd5  full-core-ordering.log
4e2afe5aef52badf0b4166352db1d636f239fda01850a5ef55c8a2995877a403  full-core-ordering.nbf
a4b877058f6cc43ec1c75875f8561a39da676c0547e65e346db6e1bb39a20e38  full-core-ordering.riscv
eabb476bdabaf5fe1814f1f30f8715508eff739de5d9b42aff3bc5fa6cb5216c  full-core-ordering-transitions.txt
db964a3af2c31f6d0c053d810e05c68ac5ac06abb963d54d864cc140ff3331a2  dcache-regression.fst
5f86e801d0e7061052a62b7f0be9ff9278cfc54cccb6e9fc57d4a8928c6572dd  dcache-regression.log
acdedcac23fd45f1f6a36a775f8060e1304d4b027334084ee5d0d59b7211598f  dcache-regression.nbf
c29e5e55a9ba9247920ece55da0fdfba7c8fc712ce874e930773511cdfb3ad5d  dcache-regression.riscv
4c753ce974c84caf3a26b103fc3f64fd0dc2e72e9eb92e35d88b1c69ad112c8d  icache-regression.fst
6fec7cdbd6782044770c25b27f744bdc77163dc0a16c5f9f489ac514a6d9c8ad  icache-regression.log
a0447eddc56da627e569a646cf4a1774aed67d78a4c535878175bff1c3a2d945  icache-regression.nbf
ee966c4380a6be4a80e1df93bab38cbe32e11b63ff973e9ae3a44c1d5114b08e  icache-regression.riscv
```
