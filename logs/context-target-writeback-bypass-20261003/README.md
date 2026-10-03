This directory records the simulator qualification and physical-board diagnosis of CSR800 target forwarding. It distinguishes the rejected same-cycle bypass from the follow-up registered-writeback design and retains the measurements needed to reproduce that decision.

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

The ELF SHA-256 is `1fa9e5445db0837de5457eaa7d82775b5c2c3a3d88a54d900483bcd8aaf99614`; the waveform SHA-256 is `52a08a1ecfde78d87bea757d0e01fe3e03c6da265bb7581ccb3b9aadfdf79fa3`.

## Physical rejection of the same-cycle bypass

The routed image at top `520e5dabfc3e9314b61a4690bafd0d11c4138ba0`, BlackParrot `0d674c32f3a5673dd65a1bc1cc4923e3fc3e5885`, and bitstream SHA-256 `ec89703717e89507c2b751835ba15a9bf5fc4d03f41700b10c464ad6b1f13dc4` met timing at WNS `+1.063 ns` and WHS `+0.035 ns`. Its exact Linux compact probe reproducibly completed register, loaded, and resident bitmap cases, then stalled on the nonresident `ld; ctz; csrw 0x800` case:

| Target source | Context 1 | Context 2 |
| --- | ---: | ---: |
| Stable register | 7.85 cycles/op | 12.29 |
| Adjacent load | 11.70 | 15.08 |
| Adjacent load and CTZ | 12.26 | stalled |

The following physical controls narrowed the failure:

- A sustained `amoswap; fence; ctz; csrw` sweep passed at every static spacing from eight NOPs through zero.
- Eight repeated context-2 bitmap rings passed; alternating live contexts 1 and 2 also passed.
- The exact six-case probe failed twice at the same final row.
- Replacing the preceding bitmap eviction with a constant-register eviction passed.
- Adding one NOP between CTZ and CSR800 to the otherwise exact six-case binary passed all rows; its context-2 bitmap result was 16.14 cycles/op.

These controls reject a general CTZ error, replacement-count limit, and random timing failure. They show that same-cycle forwarding can launch the switch one cycle before the fresh target is safe under the ordinary load/CTZ sequence. Detailed binaries, sources, runners, and transcripts are retained in the ignored working evidence directory `logs/linux-context-target-writeback-bypass-20261003/`.

## Registered-writeback candidate

The follow-up RTL holds a dependent CSR800 through the producer's live IWB cycle, registers that exact packet, and consumes it on the following cycle. This avoids both same-cycle block-RAM semantics and the rejected unconditional fifth-age tag. The sustained simulator gate passes all six cases:

| Target source | Resident context 1 | SRAM-backed context 2 |
| --- | ---: | ---: |
| Stable register | 2,001 cycles / 7.75 per operation | 3,178 / 12.31 |
| Adjacent load | 3,176 / 12.31 | 4,150 / 16.08 |
| Adjacent load and CTZ | 3,380 / 13.10 | 4,399 / 17.05 |

Relative to the same-cycle bypass simulation, dependent paths gain exactly one cycle per operation while stable-register switching is unchanged. `mt_ctxtsw_register_target_test`, `mt_ctxtsw_late_wb_hazard_test`, `mt_remote_seed_order_test`, and all 15 harness unit tests also pass. Routed timing and physical acceptance of this follow-up revision remain required.

The first nested-repository push command was accidentally issued from the top repository and failed with an unknown refspec before changing either remote. The successful retry used `git -C import/black-parrot push`; future nested pushes must retain that explicit repository selection.

The first evidence-staging command ran `git diff --cached --check` without `set -e`; serial-console carriage returns produced whitespace diagnostics but the following commit still ran. The transcripts were normalized to LF immediately afterward. Future evidence commits must use `set -e` or `&&` before the commit so a failed staged-diff check is terminal.
