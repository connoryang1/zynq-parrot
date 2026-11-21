This component gate verifies the opt-in large retained-store control CSR at 0x5c2 using the real banked CSR wrapper and instruction decoder. The cache-owned status is a stand-in, so these results do not establish full-processor trapping, cache policy behavior, FPGA correctness, timing, or application performance.

Both clean feature0 and feature1 builds pass with two physical CSR banks and four configured logical contexts. The exact CSR source hash is `2a13acd2135c43e6ea00b8c3f9cb55d6ee70456c3935b334b4927f9cd4456d8d`; root's explicit absent-feature read-data default is included. The source inspection that identified the missing default preceded these gates; no shared RTL was edited by this test owner. Neither build has LATCH/UNDRIVEN warnings or errors; unused component outputs are intentionally unconnected.

Coverage includes:

- Every four-bit control mask across all eight current/read/retirement-bank combinations, with nonzero upper payload bits to detect truncation or contamination.
- Full 64-bit externally supplied status observed identically through either read bank; bank context restoration does not overwrite that global stand-in state.
- All write/instret/context-switch gating combinations and neighboring/legacy CSR nonaliasing.
- Mixed U/S/M bank privileges: decoder privilege follows the currently decoded bank, while command permission and payload follow the retiring bank, even when those banks disagree.
- U-mode read/write decoder rejection and suppression of a synthetically supplied U-mode retirement command; S/M allowed.
- Feature0 reports illegal at the CSR read interface and emits no control command. Feature0 absence is checked separately from generic decoder privilege rejection; the decoder itself has no retained-feature parameter. No read request means no read-interface illegal pulse.

The tests are new `testing/rtl/large_retained_control_{tb.sv,driver.cpp}` and `run_large_retained_control.py`; existing 0x5c1 tests remain unchanged. Reproduce with fresh directories:

```sh
python3 testing/rtl/run_large_retained_control.py \
  --out /dev/shm/large-retained-control \
  --evidence research/large-retained-control-20261121/NEW_GATE
```

`gate01/feature{0,1}` retains the actual build commands/logs, closed FSTs, run logs, model hashes, dependency hashes and compressed exact source snapshots. The runner rejects source changes during either gate, enforces build/run time bounds and requires the matching feature-specific PASS marker. All retained source archives and available artifact hashes were independently rechecked after completion. Build objects existed only in private RAM; no target program, board, synthesis or shared SDK action was performed.
