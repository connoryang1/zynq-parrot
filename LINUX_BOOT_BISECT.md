# Linux Boot RTL Bisect

This log tracks the hardware-history bisect for the regression where the archived BlackParrot
Linux image retires instructions but produces no OpenSBI or Linux console output. Results are only
classified after a fresh overlay load and an exact, hash-verified runner/NBF pair.

## Fixed Test Inputs

- PYNQ runner SHA-256: `76db506ed632b3e68eb3201fe010b2d06e5161a2cfbe1823b71a2fbb50513be8`
- Linux NBF SHA-256: `994bd900593ffb0eba6c6bdc0f413b321d755c538ecbe105f6b9f48c17d821d5`
- Vivado: 2024.2, PYNQ-Z2, `bp_unicore_zynqparrot_cfg_p`
- A fresh overlay load is required before every run.

See `codex-skills/bp-fpga-synthesis/references/pynqz2-flow.md` for the reset, timeout, staging, and
runner rules. In particular, do not classify a reused overlay and do not wrap unprivileged
`sudo ./control-program` with `timeout`, which can leave an orphaned root runner.

## Results

| Top revision | BP revision | Result | Evidence |
| --- | --- | --- | --- |
| `4015d0f` | `08edfb479c7` | GOOD | Archived control booted Linux 6.6 through `/init`, rootFS checks, poweroff, and `CORE[0] PASS`. |
| `69b939b` | `c39ee12b735` | GOOD | Initial multithreading/context-switch implementation booted the exact archived image through `/init`, rootFS checks, poweroff, and `CORE[0] PASS`. |
| `64e247a` | `7331fbd0958` | BAD | OpenSBI completed its banner and domain report, then stalled at the handoff to Linux S-mode before the kernel banner. |
| `079e4eb` | `b4143dcd9c0` | BAD | Isolated rollback of the global FE command-queue bypass still completed OpenSBI and stalled at the same Linux S-mode handoff. |
| `ef49245` | `c4b745f5930` | BAD | Isolated rollback of the FE PC-generator thread-selector update still completed OpenSBI and stalled at the same Linux S-mode handoff. |
| `e031866` | `3affb651cbb` | BAD | Fresh overlay and exact inputs remained silent through the healthy-boot window after the target started; clean traced CSR-isolation simulation still passed. |
| `212f9c3` | `518249289e6` | BAD | Fresh overlay and exact inputs retired instructions indefinitely with no OpenSBI/Linux console output. |
| `797d379` | `8708eff` | BAD | Current optimized context-switch design shows the same silent Linux failure. |

The `69b939b` result proves the initial multithreading/context-switch port itself can boot Linux.
The first bad revision is `7331fbd0`, the context-switch fast-path checkpoint. The following
`3affb651` commit introduces a second, earlier failure symptom:

1. `7331fbd0` — context-switch fast-path checkpoint
2. `3affb651` — allow context switch to escape I-cache miss state
3. `b5be57c4` — remove debug tracing (not expected to change function)
4. `4da00657` — fix context-switch translation/ASID restore wiring
5. `51824928` — remove dead scheduler scaffolding

- `c39ee12b735`: full Linux boot succeeds
- `7331fbd0958`: OpenSBI succeeds, Linux S-mode handoff stalls
- `b4143dcd9c0`: restoring the pre-fast-path FE command FIFO behavior does not change that stall
- `3affb651cbb`: no OpenSBI console output

## Verified `69b939b` FPGA Build

- Build job: `20260828T192850Z-d76f49b`
- Package SHA-256: `08844e4303dacefb277f140a71136a93817cc84c94b7b4d1fbf39b19b4a4fca0`
- Bitstream SHA-256: `15aba626c2fc4d344404500dfd0aa5e8e9f06a9721625414b434965beb8361ce`
- Routed timing: WNS `+4.712 ns`, TNS `0`, WHS `+0.025 ns`, THS `0`
- Utilization: 50,681 LUTs (95.27%), 20,015 registers (18.81%), 46 BRAM tiles
  (32.86%), 11 DSPs (5.00%)
- Linux run: 320,445,361 retired instructions, IPC `0.517400`, target wall time about 99.1 s
- Board log: `linux-bisect/69b939b/linux-run.log`

## Verified `e031866` FPGA Build

- Build job: `20260828T213836Z-e194c11`
- Package SHA-256: `4f5f53cd84aeef9dff59bb028060ae864543fa065d461656a68a640bf25f3f5d`
- Bitstream SHA-256: `b7e2818ea7e3c4e56fcea78943d0145dd1792124120287966c22bd281b76bfd2`
- Routed timing: WNS `+3.000 ns`, TNS `0`, WHS `+0.019 ns`, THS `0`
- Utilization: 50,756 LUTs (95.41%), 20,015 registers (18.81%), 46 BRAM tiles
  (32.86%), 11 DSPs (5.00%)
- Linux run: target reached `start()` but emitted no OpenSBI output through the full known-good
  boot window; the run was then stopped cleanly
- Board log: `linux-bisect/e031866/linux-run.log`

## Verified `64e247a` FPGA Build

- Build job: `20260828T230723Z-6940f4d`
- Package SHA-256: `ee41b89d69a0fd2177ed1f1505365ad26c0ec71ee899f1493dff4341c3c6c1cb`
- Bitstream SHA-256: `fa69746a7a543ac89c9792c9d44fc6da73c583bde2bcb901ff3ff035f115f26c`
- Routed timing: WNS `+0.862 ns`, TNS `0`, WHS `+0.031 ns`, THS `0`
- Utilization: 50,733 LUTs (95.36%), 20,015 registers (18.81%), 46 BRAM tiles
  (32.86%), 11 DSPs (5.00%)
- Linux run: OpenSBI v1.4 completed its platform/domain/HART report and selected Linux at
  `0x80200000` in S-mode, but no Linux kernel banner appeared through the full boot window
- Board log: `linux-bisect/64e247a/linux-run.log`

## Verified FE Queue Rollback Experiment

- Experiment top revision: `079e4eb4923`
- Experiment BP revision: `b4143dcd9c0`
- Change: restore the pre-`7331fbd0` queued FE command delivery while retaining every other
  fast-path change from `7331fbd0`
- Clean traced `mt_csr_isolation_test`: `CORE PASS`, 15,698 retired instructions
- Build job: `20260829T005406Z-079e4eb`
- Package SHA-256: `7588155f2643c08e23252039217de6f9d27a34f5fc235e7c5621cfdfe8e60a6a`
- Bitstream SHA-256: `7a90d3d26a1ec56239220f585c3093ed157ab1e4d324a029b9cde710d51b35d0`
- Routed timing: WNS `+1.588 ns`, TNS `0`, WHS `+0.008 ns`, THS `0`
- Utilization: 50,683 LUTs (95.27%), 20,015 registers (18.81%), 46 BRAM tiles
  (32.86%), 11 DSPs (5.00%)
- Linux result: OpenSBI completed its platform/domain/HART report and selected Linux at
  `0x80200000` in S-mode, but no Linux kernel banner appeared through the full observation window
- Board log: `linux-bisect/733-no-global-bypass/linux-run.log`

This rules out the global FE command-queue bypass as the sole cause of the first Linux regression.
The remaining functional changes in `7331fbd0` must be isolated independently, particularly the
context-switch-specific FE state-reset removal and PC-generator thread-ID update behavior.

## Verified FE PC-Generator Rollback Experiment

- Experiment top revision: `ef492456002`
- Experiment BP revision: `c4b745f5930`
- Change: restrict the FE predictor-bank thread selector to the pre-`7331fbd0` state-reset update
  condition while retaining every other fast-path change from `7331fbd0`
- Clean traced `mt_csr_isolation_test`: `CORE PASS`, 15,695 retired instructions
- Build job: `20260829T014613Z-ef49245`
- Package SHA-256: `89577c0005785de1037b2bbf80b72001deaa0781222f0101756a20c63568698d`
- Bitstream SHA-256: `7903b4c63718f1bfda08f47796d973b119200999797c773230b5be1129a0dec6`
- Routed timing: WNS `+2.380 ns`, TNS `0`, WHS `+0.013 ns`, THS `0`
- Utilization: 50,724 LUTs (95.35%), 20,015 registers (18.81%), 46 BRAM tiles
  (32.86%), 11 DSPs (5.00%)
- Linux result: OpenSBI completed its platform/domain/HART report and selected Linux at
  `0x80200000` in S-mode, but no Linux kernel banner appeared for more than 120 seconds after
  handoff
- Board log: `linux-bisect/733-pcgen-stable/linux-run.log`

This rules out the PC-generator selector update as the sole cause. Together with the FE queue
rollback result, the next high-confidence test is the combined rollback. It distinguishes an
interaction between the two FE fast paths from the remaining `7331fbd0` changes.

The four commits applied on disposable build worktrees are tool-compatibility changes only: remove
a stale source-list entry, use the stable AXI interconnect wrapper, exclude unused accelerators,
and add a missing historical BaseJump memory adapter source. Candidate CPU RTL remains at the BP
revision shown in the table.
