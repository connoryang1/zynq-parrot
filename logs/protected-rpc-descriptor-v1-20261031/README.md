The version-1 protected-RPC descriptor and call/return transport pass four
serialized, traced full-core regressions on the same clean Verilator model.

# Version-1 protected RPC

- `control`: stages all nine fields, rejects incomplete/equal-SATP/unsupported
  descriptors and commit before preparation, requires two GPR-line scrubs plus
  CSR-bank construction, proves that restaging invalidates preparation, then
  atomically commits and checks token-aware query and revoke.
- `hardware`: uses distinct U-mode Sv39 address spaces and resident contexts,
  rejects an invalid token without starting the service, installs the fixed
  entry/SP/GP/TP/badge, transfers four request and reply words plus metadata,
  and consumes the protected return continuation. Before preparation, M mode
  deliberately dirties one register in each server GPR line; the service
  observes both as zero. It measures 250/31 cycles for the matched local body
  and 396/58 cycles for protected RPC; the stable warm transition premium is
  27 cycles.
- `library`: exercises the reusable client wrapper and separately linked
  service page through the same atomic descriptor, explicit outcome, and
  request/reply metadata contract. The privileged controller constructs the
  clean server context directly, without running untrusted bootstrap code.
  Bounds-checked shared offsets and distinct private pages are preserved.
- `smoke`: confirms ordinary context switching remains operational with the
  descriptor RTL present.

Each directory retains the exact ELF and NBF plus the complete transcript with
terminal-only trailing whitespace removed. The
All transcripts contain the test-specific guest marker, `CORE PASS`, and host
`BSG PASS`. The later DPI GPIO finalizer assertion is the known simulator
teardown defect and occurs only after these markers; `testing/check_run.py`
classifies all four runs as valid.

The model SHA-256 is
`5925788e632135b9cc1b705d1c8e5fb3d07be2b77a15c7176bcd5ebecb3456bc`.
The matching OpenSBI installer stages, prepares, and commits in that order; a
fresh pinned OpenSBI plus seL4 package build succeeded with NBF SHA-256
`cbc2b526ae59141168b3df45c0b069e4b08a007248d85bb3f6bd7e679b672f79`.
These results establish the hardware mechanism, not yet the seL4 binding,
interrupt/fault policy, routed timing, or FPGA execution.
