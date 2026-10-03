This directory records the clean simulator qualification of the writeback-aware CSR800 target bypass. It retains the exact sustained regression, disassembly, waveform, identities, and assertion counts needed to distinguish the fix from the rejected fixed-age interlock.

# Context-target writeback bypass

BlackParrot `0d674c32f3a5673dd65a1bc1cc4923e3fc3e5885` keeps a register-form CSR800 instruction interlocked through integer pipeline stages zero through two. In stage three it releases only when the matching thread and destination register are present on integer writeback, and the scheduler forwards that packet's value directly into target classification. This removes dependence on same-cycle FPGA block-RAM read/write behavior without adding the unconditional fifth dependency age that stalled the routed sustained loaded-target ring.

The clean gate was:

```sh
make -C testing clean
make -C cosim/black-parrot-minimal-example/verilator clean
make -C testing run-mt_ctxtsw_target_bypass_stress_test \
  NUM_THREADS=2 NUM_CONTEXTS=4 TRACE=1 VERILATOR_BUILD_JOBS=12
```

The test runs 128 round trips in each direction, followed by two drain operations. Disassembly confirms the loaded loop contains adjacent `ld; csrw 0x800`, while the ready-bitmap loop contains adjacent `ld; ctz; csrw 0x800`.

| Target source | Resident context 1 | SRAM-backed context 2 |
| --- | ---: | ---: |
| Stable register | 2,000 cycles / 7.75 per operation | 3,177 / 12.31 |
| Adjacent load | 2,921 / 11.32 | 3,894 / 15.09 |
| Adjacent load and CTZ | 3,124 / 12.11 | 4,143 / 16.06 |

All six cases pass target identity, peer completion, guest `CORE PASS`, host `BSG PASS`, and the fail-closed harness. Across the exact clean waveform, CSR800 dispatch asserts 1,548 times; the register-source hazard and matching integer-writeback bypass each assert 1,028 times. Thus the new path is exercised repeatedly across loaded and computed targets rather than only during initialization.

The ELF SHA-256 is `1fa9e5445db0837de5457eaa7d82775b5c2c3a3d88a54d900483bcd8aaf99614`; the waveform SHA-256 is `52a08a1ecfde78d87bea757d0e01fe3e03c6da265bb7581ccb3b9aadfdf79fa3`. Routed timing and physical FPGA/Linux acceptance remain required because the original failure was FPGA-specific.

The first nested-repository push command was accidentally issued from the top repository and failed with an unknown refspec before changing either remote. The successful retry used `git -C import/black-parrot push`; future nested pushes must retain that explicit repository selection.
