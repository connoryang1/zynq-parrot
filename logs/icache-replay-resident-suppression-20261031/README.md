This directory preserves the simulation evidence for completed-line residency suppression in the detached instruction replay path. It distinguishes the accepted exact-ELF run from an initially misleading stale-program run and records the remaining physical-validation boundary.

# Instruction replay resident suppression

## Implemented contract

Each configured prefix entry now spends one cycle querying the frontend's
16-entry advisory replay buffer before UCE admission. A matching entry counts
as resident only when all four 128-bit beats are valid; complete matches are
dropped without a memory request, while partial, absent, or invalidated entries
continue to the detached UCE lane. CSR status bits 63:55 count resident drops,
and bit 54 reports a pending residency query.

The lookup covers the completed advisory buffer, not ordinary L1-I tags. Its
purpose is to prevent the repeated context-switch trigger from withdrawing and
refetching a line that the detached mechanism itself already retains.

## Accepted gates

- The controller gate queries four ordered entries, suppresses two modeled
  residents, admits the other two under backpressure/direct-request priority,
  and checks resident-drop counter saturation/clear behavior
  (`controller-run.log`).
- The buffer gate rejects a three-beat partial entry, reports a four-beat entry
  resident, executes all eight words, and reports it absent after `fence.i`
  (`buffer-run.log`).
- A clean `NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1` full-system rebuild executes
  three prefix epochs: four initial admissions, four resident drops with no
  additional admissions, then four new admissions after `fence.i`. It also
  executes all replay targets, a 32 KiB ordinary demand stream, direct replay,
  duplicate admission, and cancellation before reaching guest, core, and host
  PASS (`full-core-final.log`). The known DPI finalization assertion occurs
  only after those PASS markers and is accepted by `testing/check_run.py`.
- The exact rebuilt ELF and simulator copy both have SHA-256
  `ee966c4380a6be4a80e1df93bab38cbe32e11b63ff973e9ae3a44c1d5114b08e`.
  The accepted NBF has 7,567 records and retires 20,608 instructions. The FST
  SHA-256 is `bcfe85d3141d46988d86d467d8e7b54f20c3a1aa4f72aa23b20ab0272fbf45d4`
  and remains at `/dev/shm/zp-resident-suppression-fullcore/final-dump.fst`.

An independent context-switch smoke test also reached its guest marker,
`CORE PASS`, host `BSG PASS`, and `VALID RUN` after the shared collateral fix.

## Rejected stale-program run and guardrail

The first apparent repeated-trigger pass actually ran an older same-named ELF.
The collateral rule recursively searched `riscv/`, where both
`riscv/bp-tests/mt_icache_replay_test.riscv` and a stale nested
`riscv/riscv/bp-tests/mt_icache_replay_test.riscv` existed; `find -exec cp`
copied both and the stale file won. Its simulator copy had SHA-256
`4e2ba85069c467a1a9bb6f29c17dfbb44d62659cc9448a53fc8b9a599b205af8`,
only 3,432 NBF records, and 4,081 retired instructions
(`rejected-stale-elf-run.log`). It is not acceptance evidence.

Testing now passes the exact prerequisite ELF as `PROG_RISCV`, and the lower
collateral rule verifies that path before copying. The normal testing flow then
reproduced the accepted 7,567-record/20,608-instruction result, closing the
stale-name ambiguity without deleting the historical nested tree.

## Remaining boundary

This proves the intended timing and invalidation mechanism in focused and full
system simulation. It does not prove FPGA timing/fit, sustained Linux safety,
or a Linux speedup. The next gate is a routed candidate followed by the same
physical replay discriminator and sustained Linux correctness; only then
should the matched disabled/old-16-line performance comparison be repeated.
