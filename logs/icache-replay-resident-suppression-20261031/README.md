This directory preserves the simulation, route, and physical FPGA evidence for completed-line residency suppression in the detached instruction replay path. It distinguishes accepted exact-image results from stale-program and harness failures, and it keeps the fresh Linux performance comparison separate from the physical-correctness claim.

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

## Routed FPGA result

Farm job `bp2/20261031T113038Z-a556049e` implemented exact top-level commit
`a556049ece76113307a559cc2fe2b67cb695798c` and BlackParrot commit
`5201034466864b01c6a512acf67f03df3e702489` for
`e_bp_unicore_zynqparrot_prefetch_cfg`. Signoff passes at `+0.841 ns` setup WNS
and `+0.030 ns` hold WHS with zero TNS/THS. It uses 50,084/53,200 LUTs
(94.14%), 24,782 registers, 94 BRAM tiles, and 11 DSPs. The verified package
and bitstream SHA-256 values are respectively
`622f45589fd2fd6410f5b2e96494ca40679e727011d4f89a6f7817bb5979a688` and
`508a192ba7287cc372e456336d50b310b9ecb0e73af3a51c56efaa0a1605163d`.
The retained farm summary and revision manifest are under
`../fpga-farm/bp2/20261031T113038Z-a556049e/`.

Relative to the preceding accepted route, the feature costs 204 LUTs and 15
registers, leaves BRAM/DSP counts unchanged, and improves setup WNS by 0.723
ns. This comparison is an implementation observation, not an expected
frequency gain from the feature.

## Physical correctness gates

The exact repeated-trigger discriminator uses source/ELF/NBF SHA-256 values
`4f33fd29dfcfb043e71039b21dea9b182b6d22e6ec87d1843fa868e3db25339f`,
`5a50721bc641859ec44feafe1d24d85712d6f1f43154ce01ae4528dfa85db2f7`,
and `b083917d2e78a63e2f9eb40c4bb431d8702d83352921ac8f32ed1da98b8279ce`.
After a recovery-qualified power cycle and exact overlay reload, it reached
`[BSG-PASS]`, `CORE PASS`, runner RC 0, and `BSG PASS`
(`fpga-foreground/mt_icache_replay_test.log`). This physically exercises the
repeated-trigger, resident-drop, invalidation, and readmission assertions in
the guest rather than inferring them from Linux survival.

The replay-enabled exact kernel-#8 image then booted to a shell and completed
two competing 1,000-iteration workers and two 5,000-iteration workers. It shut
down through `CORE PASS`, runner RC 0, and `BSG PASS` after 719,905,147 retired
instructions (`fpga/linux-prefix16-sustained.log`, SHA-256
`0bf76f06a18aa189733014bda7142823ae01bb3184079236063271afc47b079f`).
The first stress command is rejected because the guest lacked `/dev/null`;
the accepted repetitions ran only after creating that device.

## Fresh physical Linux A/B

Both arms use the same routed hardware and benchmark ELF SHA-256
`332d4e9c54660586234fd6eef2b464973e4aa7f76d5c13c4f49fc8c648eeb6a7`.
Each arm starts from a fresh overlay load, performs one unrecorded warmup, and
collects 50 numbered `to-peer` samples before a clean poweroff. The enabled
old-16-line NBF SHA-256 is
`d7a2964c018f260cba7695607e0f7d86eced474e65dd57bb4ec967af16fae235`;
the disabled NBF SHA-256 is
`eee6fa9ff26307f7b8f0edf3cf3e2718f2a6ad2a073a11fa87aa6c27235fe716`.

The enabled median is 16,485 cycles and the disabled median is 17,569.5
cycles, a favorable point difference of 1,084.5 cycles or 6.17%. The
deterministic 100,000-resample independent-sample bootstrap gives a 95%
enabled-minus-disabled median-difference interval of `[-17,403, +16,595]`
cycles and favors enabled in 65.489% of resamples. The interval crosses zero,
so this batch does **not** establish a Linux speedup. It is a promising but
noisy best-case point estimate after the physical correctness gates, not a
performance acceptance result. Exact samples, terminal-marker validation,
hashes, and analysis are in `fpga-ab-results.json` and
`analyze_fpga_ab.py`.

## Harness failures excluded from RTL evidence

Three setup attempts preceded the accepted physical discriminator. One ran
validation from a directory where the serial wrapper could not hash its
basename-only argument; another exposed that SSH drops an empty final runner
hash argument; and a detached wrapper disappeared before producing a target
transcript. None reached an accepted target result. The last event required a
PYNQ power cycle, readiness wait, and overlay reload before the foreground
PASS. These are harness outcomes, not RTL failures; the runner fixes are kept
separate from the feature checkpoint.

## Remaining boundary

The mechanism now passes focused simulation, clean full-core simulation,
routed timing/fit, a physical repeated-trigger discriminator, and sustained
replay-enabled Linux. The fresh performance point favors replay but is not
statistically closed. A stronger next performance experiment should reduce
scheduler-mode mixture or collect enough independently booted batches to
narrow the interval; prefix-size tuning should not be inferred from this one
noisy 50-sample pair.
