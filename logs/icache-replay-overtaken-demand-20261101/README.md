This directory preserves the directed and full-core simulation evidence for dropping a detached I-cache replay that arrives after an identical architectural demand is already resident in the UCE. The change avoids issuing an advisory request that cannot satisfy that resident demand and would otherwise cause a redundant ordinary refill; it is not yet FPGA evidence or a Linux performance result.

# Overtaken same-line replay suppression

The simulation-accepted BlackParrot revision is
`158adde752c4a03c0d9136acc04235f850bc8f2d`.

## Mechanism

`bp_uce.sv` now compares each incoming detached replay with the resident
`cache_req_r`. If their cache-line addresses match, the UCE acknowledges the
advisory replay without allocating a replay slot. The resident architectural
demand then issues directly. Replays that arrived before the demand retain the
existing merge/withdraw behavior, and unrelated replays retain the existing
capacity and duplicate checks.

## Verification

- Side-buffer directed test:
  `python3 testing/rtl/run_uce_icache_replay.py --side-buffer --out /dev/shm/zp-joint-bestcase-uce-physical --verilator /home/coyang/zynq-parrot/install/bin/verilator`
  reports `PASS: detached retirement and overtaken same-line replay drop`.
- Legacy-installer directed test, using output directory
  `/tmp/zp-uce-overtaken-legacy`, reports the same overtaken-replay drop along
  with the existing installer, invalidation, and demand-priority checks.
- Four-slot/80-cycle burst control, using output directory
  `/tmp/zp-uce-overtaken-burst4-l80`, completes 16 requests in 393 cycles with
  maximum occupancy four.
- The clean nonresident full-core gate was built and run with
  `make -C testing run-mt_icache_replay_test NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12`.
  It reaches `[BSG-PASS] shared-prefix and physical I-cache replay`, `CORE PASS`,
  and `BSG PASS`. The retained log then contains the known shutdown-only DPI
  finalizer assertion after both guest and host pass; the maintained wrapper
  classified the result as `VALID RUN`.

The focused waveforms and verifier manifests are retained as
`uce-{side-buffer,legacy,burst}.*`. The clean full-core waveform is
`full-core-dump.fst`; `full-core-build.log` proves that the model was freshly
rebuilt rather than reused.

## SHA-256

```text
4275db34faed370389463283d246bb9a40d3e413768350abfc3aa685b4647e58  full-core-build.log
2f9771e9f68c523b29aca60fe63eb6654abf8081367319214072f35cf52b34f9  full-core-dump.fst
d27ebefc01e70b0de7eb3ca607139be02ba72a0529c4857835b33b4eb606d8d8  full-core-run.log
74a7bb1487f10e55aee08fafc3ffad0b889acebcfc85f10b77780abf61fc0ce6  uce-burst-run.log
b887e08e873bc77c6c38cce63cf15478a816c26170b0c1c9c5f2e63d2a4739ad  uce-burst-verification.json
074ac088bd5e00d540a2b26fe7af6808fb065ec0a6c4e66c47c26c8ac2dd2a15  uce-burst.fst
a890f4fa45d886c0e881aa1e213ccbfea6fbab67a9e117a26e06a4283230663b  uce-legacy-run.log
7dd6ddf02e18671c72c87bdd2dcbbb0956063d70868478bf84ea994af71a8c0c  uce-legacy-verification.json
e6ec9c84d85ecc7a00f1123d640bee04a0f7f3db93a97e938583254eae832d4f  uce-legacy.fst
6c9f1046cacfb2d441a9800b1da1077c97e5842203fb9251c2c4c1d491ee7c2f  uce-side-buffer-run.log
62cbcfa52a6ab5e4c3ab938c6dd217060b02489c08f7b36b0ef924a87d76b91a  uce-side-buffer-verification.json
32d10b87b8eabfee34b3ba7fb449c6925fcf1e500d48b2aba8dc6ef2a72e05a2  uce-side-buffer.fst
```
