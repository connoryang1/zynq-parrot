# Linux boot localization on the cache-miss recorder image

This directory records why the routed cache-miss recorder image initially did
not reach Linux and the packaging correction that produced a complete physical
boot.  The original failure was independent of the Linux userspace payload,
DRAM allocation size, and timer source: execution stopped in OpenSBI's early
machine-mode hart initialization because the NBF loader had entered debug mode.

## Exact deployed hardware

- top-level route: `e860ceea`
- BlackParrot RTL: `52c5dde701263b4a476fc87ae0c37afb9721cfcb`
- bitstream SHA-256:
  `f4a183d8f900170ce5a6eb59366d56609cbe0f492063ea5a41b791d807306c5a`
- 46 MiB `control-program` SHA-256:
  `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- OpenSBI-only prefix NBF SHA-256:
  `2ed63a1c8ad7df1198c3926dcaa43793b6913a3ef92534f4fd096ba20c4bcce6`

Every physical probe used a fresh explicit overlay reload and a bounded,
serialized board run.  `RUNNER_EXIT=124` means the target-runtime limit fired;
it is the expected failure result for a marker that was never reached.

## Payload and timer controls

| Image | Timer selector | Bound | Retired delta | MTIME delta | IPC | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| accepted shell image, 46 MiB DTB | 2 | 300 s | 250,005,324 | 1,499,995,857 | 0.020834 | no console |
| direct PID 1 image, 46 MiB DTB | 1 | 300 s | 250,006,186 | 234,374,771 | 0.133337 | no console |
| direct PID 1 image, 46 MiB DTB | 2 | 300 s | 250,004,034 | 1,499,996,173 | 0.020834 | no console |
| OpenSBI-only prefix | 2 | 120 s | 100,006,888 | 600,003,613 | 0.020835 | no console |

Selector 2 makes the shell and direct-PID-1 cases indistinguishable.  Removing
the entire Linux payload also preserves the stall.  This rules out BusyBox,
the shell, PID 1, Linux transfer, Linux memory footprint, and timer selection.

## Machine-mode reachability ladder

The one-shot NBF probes replace the instruction at a guarded physical PC with
a host marker and finish packet.  A PASS proves that PC was fetched and
executed; a timeout proves only that the PC was not reached within the bound.

| Probe | PC | Marker/result | Meaning |
| --- | ---: | --- | --- |
| before first boot AMO | `0x80000034` | `Ma`, PASS | reset entry executes |
| after boot branch | `0x8000003c` | `Mb`, PASS | first boot path selected |
| `sbi_init` entry | `0x800006cc` | `Md`, PASS | OpenSBI initialization entered |
| coldboot atomic return | `0x8000076e` | `Mf`, PASS | second AMO completed |
| coldboot atomic value | `0x8000076e` | `V0Mg`, PASS | AMO returned zero; cold path selected |
| secondary wait loop | `0x80000840` | timeout | core did not take secondary path |
| common hart hang | `0x8000ddc6` | timeout | no ordinary error return to hang |
| return from `sbi_hart_init` | `0x800007fa` | timeout | failure is inside hart initialization |
| before first `pmpcfg0` write | `0x8000bdc8` | `Mk`, PASS | setup and temporary `mtvec` sequence entered |
| after first `pmpcfg0` sequence | `0x8000bdd8` | timeout | exact first failing boundary |
| OpenSBI expected-trap entry | `0x8000ed60` | timeout | temporary handler was not reached |
| expected-trap `mret` | `0x8000ed82` | timeout | unreachable because handler was not entered |

The guarded sequence at the boundary is:

```text
0x8000bdcc  csrrw a2, mtvec, a2
0x8000bdd0  csrw  pmpcfg0, a1
0x8000bdd4  csrw  mtvec, a2
```

Replacing the PMP write with an ordinary illegal instruction or an M-mode
`ecall` still does not reach the temporary handler.  Inserting one or four NOPs
between the `mtvec` write and the forced exception does not change the result,
so this is not a one-cycle CSR dependency.  A separate board probe reads
`mtvec`, compares its low 32 bits with `0x8000ed60`, and reports `V0Mr`/PASS;
the temporary handler address is present in the active CSR bank.

## Root cause: the NBF requested debug entry

Both Linux packaging recipes invoked `nbf.py --debug`.  That option prepends a
debug-interrupt pulse while the core is frozen:

```text
02_0000000000200008_0000000000000001  # freeze = 1
02_000000000030c000_0000000000000001  # debug interrupt = 1
fe_0000000000000000_0000000000000000  # fence
02_000000000030c000_0000000000000000  # debug interrupt = 0
```

Clearing the interrupt does not leave architectural debug mode; software must
execute `dret`.  OpenSBI has no debug-resume startup stub.  Its synchronous PMP
probe therefore redirects to the debug exception PC at `0x80000008` instead of
the programmed `mtvec`.  That address is the third instruction of OpenSBI's
reset path, explaining both the failed temporary handler and continuing high
retirement count.

A standalone board test made the path visible with bytes `A/B` at reset,
`C` at main, `E` before ECALL, `H` at `mtvec`, and `R` after `mret`:

| NBF start and payload | Marker/result | Retired delta | MTIME delta |
| --- | --- | ---: | ---: |
| `--debug`, no `dret` | repeating `ABCE`, timeout | 117,684,716 | 7,813,048 |
| `--debug`, explicit `dret` | `ABCEHR`, PASS | 3,152 | 361 |
| no `--debug`, no `dret` | `ABCEHR`, PASS | 3,193 | 349 |

The unchanged OpenSBI-only prefix, with only the three debug-pulse commands
removed, prints the full OpenSBI v1.4 platform/HART report and reaches its
S-mode handoff.  Its SHA-256 changes from
`2ed63a1c8ad7df1198c3926dcaa43793b6913a3ef92534f4fd096ba20c4bcce6`
to `07d9675b53796f557d36dc71ed6a0d7a6226839d84bf93ff6d05e86690890dbd`.
The bounded prefix then runs into its intentionally absent payload.

The full direct-PID-1 image was transformed the same way, changing SHA-256
from `552d3cd768c4699f0e3991f26547cd98d6804d08216a8db489895a1261c3d053`
to `1a7a733546ea9f0de897cea0ed6267b2e746a9b5df925f8acc7c3db2121df82d`.
On the original recorder bitstream it booted Linux, ran `/ctxtsw_user_tiny`,
completed the hardware `0 -> 2 -> 0` user-mode handoff, printed PASS, and
powered down cleanly at Linux time 29.274616 s.  The host measured 304,368,284
retired instructions and 296,503,987 MTIME ticks for the target run.

The maintained `linux-tests/Makefile` now omits `--debug` for both Linux NBF
packaging paths and has a host regression preventing its reintroduction.

## Additional CSR compatibility route

Git history contained three earlier commits on a divergent branch that made
the exact OpenSBI probe classes legal hardwired-zero WARL state:

- PMP configuration/address probes
- absent machine HPM counters/events
- optional privileged-extension probes (`menvcfg`, `mstateen0`, `mcyclecfg`,
  `scountovf`, `mtopi`, and `stimecmp`)

Those commits were not ancestors of the recorder/ASID branch.  Their combined
behavior is restored in BlackParrot `6a8f319891141b45d5011681a47603f71b8aecd6`,
pinned by top-level `5c8475dfdf403cdbf3762fb187b8a48536561d62`.
This accurately advertises no PMP or optional capability directly.  The
physical no-debug run proves these RTL changes are not required to recover boot:
the older recorder image's architectural illegal-instruction handler also
completes OpenSBI discovery once it starts outside debug mode.

The clean Verilator model passes both:

- `mt_machine_trap_test`: after leaving the simulator CRT's reset/debug mode,
  a cold M-mode ECALL records cause 11 and the exact fault PC, redirects through
  `mtvec`, and returns through `mret`
- `mt_opensbi_csr_probe_test`: every recovered probe reads zero and completes
- `mt_umode_resident_sv39_data_handoff_test`: translated resident handoff,
  ECALL trap state, and return remain correct

An initial version of the cold-trap regression omitted the simulator-only
`dret` transition.  Its waveform correctly showed cause 11 redirecting to the
debug exception slot at `0x80000008`; that result exercised reset/debug state,
not OpenSBI's machine-mode trap path.  Repeating the test after the same debug
exit used by the maintained privilege tests passes, ruling out a general
M-mode exception defect in this RTL.

Routed job `20261006T212207Z-5c8475df` completed PASS as a direct-zero-WARL
compatibility candidate. It closed timing at +0.885 ns WNS and used 50,518
slice LUTs (94.96%), 21,581 registers (20.28%), 82 block-RAM tiles (58.57%),
and 11 DSPs (5.00%). Its bitstream SHA-256 is
`7c6becdda90ff2dd2c2ce48abeb8611eda603e105277af2ed6c0e4ee3c4c5ad9`.
The original recorder image has already passed OpenSBI, direct PID 1 Linux
boot, the hardware handoff, and sliced Linux cache-miss capture after the
packaging fix. The compatibility image still requires its own physical boot
gate before replacing the recorder image.
