The version-1 protected-RPC descriptor and call/return transport pass four
serialized, traced full-core regressions on the same clean Verilator model.

# Version-1 protected RPC

- `control`: stages all nine fields, rejects incomplete/equal-SATP/unsupported
  descriptors, atomically commits a valid descriptor, and checks token-aware
  query and revoke.
- `hardware`: uses distinct U-mode Sv39 address spaces and resident contexts,
  rejects an invalid token without starting the service, installs the fixed
  entry/SP/GP/TP/badge, transfers four request and reply words plus metadata,
  and consumes the protected return continuation. It measures 191/31 cycles
  for the matched local body and 186/56 cycles for protected RPC; the stable
  warm transition premium is 25 cycles.
- `library`: exercises the reusable client wrapper and separately linked
  service page through the same atomic descriptor, explicit outcome, and
  request/reply metadata contract. Bounds-checked shared offsets and distinct
  private pages are preserved.
- `smoke`: confirms ordinary context switching remains operational with the
  descriptor RTL present.

Each directory retains the exact ELF and NBF plus the complete transcript with
terminal-only trailing whitespace removed. The
closed FST files are hashed and retained under `/dev/shm/rpc-transport-evidence`
for the current run but are omitted from Git because they total about 67 MiB.
All transcripts contain the test-specific guest marker, `CORE PASS`, and host
`BSG PASS`. The later DPI GPIO finalizer assertion is the known simulator
teardown defect and occurs only after these markers; `testing/check_run.py`
classifies all four runs as valid.

The model SHA-256 is
`4b3a869506867eab37abc2204bce04163f7df6fb6b1d3f7c24be5751ae62d1e3`.
Every modified RTL input matched the isolated clean worktree before execution.
Closed waveform SHA-256 values are `6f67abbe…72fb` (control),
`19b17dee…1427` (hardware), `6a60ed04…dfae` (library), and
`70ed76e1…aaa7` (smoke).
These results establish the hardware mechanism, not yet the seL4 binding,
interrupt/fault policy, routed timing, or FPGA execution.
