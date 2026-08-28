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
| `e031866` | `3affb651cbb` | BAD | Fresh overlay and exact inputs remained silent through the healthy-boot window after the target started; clean traced CSR-isolation simulation still passed. |
| `212f9c3` | `518249289e6` | BAD | Fresh overlay and exact inputs retired instructions indefinitely with no OpenSBI/Linux console output. |
| `797d379` | `8708eff` | BAD | Current optimized context-switch design shows the same silent Linux failure. |

The `69b939b` result proves the initial multithreading/context-switch port itself can boot Linux.
The bad `e031866` midpoint narrows the regression to the first two later BP commits:

1. `7331fbd0` — context-switch fast-path checkpoint
2. `3affb651` — allow context switch to escape I-cache miss state
3. `b5be57c4` — remove debug tracing (not expected to change function)
4. `4da00657` — fix context-switch translation/ASID restore wiring
5. `51824928` — remove dead scheduler scaffolding

The next hardware candidate is top `64e247a` / BP `7331fbd0`. If it boots, the regression is
`3affb651`; if it fails, the regression is `7331fbd0`.

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

The four commits applied on disposable build worktrees are tool-compatibility changes only: remove
a stale source-list entry, use the stable AXI interconnect wrapper, exclude unused accelerators,
and add a missing historical BaseJump memory adapter source. Candidate CPU RTL remains at the BP
revision shown in the table.
