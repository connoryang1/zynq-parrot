This file explains maintained FPGA build, deployment, and Linux debugging procedures. Historical commands are recoverable at named Git checkpoints; use the canonical checkout guide for accepted source and artifact identities.
It distinguishes the baseline configuration from the prefetch candidate and the validation each image requires.

# PYNQ-Z2 Build And Deployment Reference

The canonical branch and accepted identities are documented in
[CURRENT_CHECKOUT.md](../../../CURRENT_CHECKOUT.md). Current Linux application
packaging is in [linux-tests/README.md](../../../linux-tests/README.md).
Historical Jan. 24 runner recipes and removed AMO/S-mode test commands are
preserved in local tag `archive/pynq-recipes-before-cleanup-20260908`; their old
harness is at `e4242c1c`. Recover those on an isolated diagnostic branch only
when needed, rather than running leftover binaries in the active checkout.

## Current build

The baseline command, from `cosim/black-parrot-example/vivado`, is:

```bash
make fpga_build pack_bitstream \
  BOARDNAME=pynqz2 \
  VIVADO_VERSION=2024.2 \
  VIVADO_MODE=batch \
  CFG=e_bp_unicore_zynqparrot_cfg
```

For the nonblocking-prefetch candidate, use the maintained launcher's
`FPGA_CFG=e_bp_unicore_zynqparrot_prefetch_cfg` override with a clean immutable
source snapshot, pinned dependencies, and separate persistent logs as shown in
[the synthesis skill](../SKILL.md#iteration-modes). The baseline remains the
launcher default. The prefetch candidate requires FPGA fit and board
acceptance; consult [CURRENT_CHECKOUT.md](../../../CURRENT_CHECKOUT.md) for status.

A clean milestone build may prefix `make clean`, but a fresh isolated worktree does not need it.
The expected packed artifact is:

```text
cosim/black-parrot-example/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64
```

Vivado's routed timing report normally resides below:

```text
black_parrot_bd_proj.runs/impl_1/
```

## Prerequisites

- `/tools/Xilinx/Vivado/2024.2/settings64.sh`
- initialized pinned submodules, including nested BlackParrot and BaseJump dependencies
- populated repository `install/` and `riscv/` trees from `make prep_lite`
- a configuration enum that exists in the pinned BlackParrot RTL

### Sourceware rate-limit fallback

The SDK's RISC-V GNU toolchain may receive HTTP 429 from Sourceware. Preserve the gitlinks and
change only the fetch transport:

- binutils: `https://github.com/riscvarchive/riscv-binutils-gdb.git`
- GDB: `https://gnu.googlesource.com/binutils-gdb`
- glibc: `https://github.com/bminor/glibc.git`
- GCC: retain `https://github.com/gcc-mirror/gcc.git`
- newlib: `https://github.com/RTEMS/sourceware-mirror-newlib-cygwin.git`

Run `../scripts/setup_sourceware_mirrors.sh` from this skill instead of editing the SDK's tracked
`.gitmodules`. The helper uses shallow checkouts and verifies the final commits against gitlinks.

`bp_unicore_zynqparrot_cfg_p` is the base definition behind the top-level
`e_bp_unicore_zynqparrot_cfg` Make enum. This baseline has two resident slots
and four architectural contexts. The separate static
`e_bp_unicore_zynqparrot_prefetch_cfg` retains those context counts and selects
two L2 banks, 16 sets per bank, and 50-bit branch metadata. Use these named FPGA
configurations rather than `e_bp_custom_cfg`: the dynamic FPGA macro path can
silently fall back to an incompatible four-resident-thread design.

## Board deployment

Keep deployment separate from build validation. First verify the package locally:

```bash
codex-skills/bp-fpga-synthesis/scripts/verify_pynq_package.sh \
  cosim/black-parrot-example/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64
```

Record the package SHA, bitstream SHA, and reported artifact stem. With authorization, copy the
exact package and NBF to the board. Do not trust already unpacked collateral. Explicitly extract
the selected package and verify the resulting `.bit`:

```bash
base64 -d ../black_parrot_bd_1.zynq.pynqz2.tar.xz.b64 | tar xvJ
sha256sum black_parrot_bd_1.bit
```

The board checkout and package should come from the same top-level revision. Older checkouts may
use `blackparrot_bd_1.*` while current packages contain `black_parrot_bd_1.*`. Update the board
checkout or copy the verified `.bit`, `.hwh`, and `.map` to the expected stem together; never mix
members from different packages.

Prefer the guarded staging helper for this sequence:

```bash
codex-skills/bp-fpga-synthesis/scripts/stage_pynq_artifacts.sh \
  <package.tar.xz.b64> xilinx@192.168.4.35 <program.nbf> [...]
```

It detects the board Makefile's load stem and prevents a new NBF from being run against an old
same-directory bitstream under the historical `blackparrot_bd_1` name.

### Unattended overlay reload

Install the root-owned fixed-path loader once on the board. Copy the installer from this skill to
the board, inspect it, and run:

```bash
sudo ./install_pynq_overlay_loader.sh
```

The installer validates its sudoers fragment before activation and installs:

- `/usr/local/sbin/load-blackparrot-overlay`, owned by root and mode `0755`
- `/etc/sudoers.d/blackparrot-overlay`, owned by root and mode `0440`

The sudo rule permits only that helper. The helper accepts no arguments and loads only
`/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/blackparrot_bd_1.bit` with its matching
HWH. It does not grant passwordless Python, shell, `make`, or arbitrary-path execution. Because
the `xilinx` user can replace the fixed-path bitstream, this deliberately grants unattended FPGA
programming capability; do not use the rule on a shared or untrusted board account.

After staging a verified package, load it from the VM with:

```bash
codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh xilinx@192.168.4.35
```

Require `LOADING_BIT_SHA256` to match the staged `BOARD_BIT_SHA256` and require both
`OVERLAY_LOAD_OK=1` and `REMOTE_OVERLAY_LOAD_OK=1` before launching a target image.

### Retained board-run transcripts

`control-program` configures terminal state and must be given a pseudo-terminal. A plain detached
SSH command can lose all target output (or leave an uninspectable root child), so launch retained
board tests through `script` and poll the board-side transcript. **There must be exactly one
control-program run on the board at a time.** Use the serial helper; it atomically acquires a
board-side lock, rejects a legacy/manual runner, retains the transcript under `~/bp-logs`, and
waits for the exact launched PID to write its exit status before it returns:

```bash
codex-skills/bp-fpga-synthesis/scripts/run_pynq_serial.sh \
  xilinx@<board> <program>.nbf
```

Do not schedule a delayed remote launch behind a local timeout: the local caller can disappear
while its remote command later starts, causing two runners to compete for PL DRAM and GP ports.
If the helper reports `ACTIVE_RUNNER`, do not retry; inspect the retained transcript or power-cycle,
reload the overlay, and then start a fresh run. It reclaims only a lock whose recorded wrapper PID
is dead and only after confirming no direct `control-program` or `script` runner remains.

For manual inspection only, the underlying retained-run form is:

```bash
ssh xilinx@<board> '\
  cd ~/zynq-parrot/cosim/black-parrot-example/zynq || exit 1; \
  mkdir -p ~/bp-logs; \
  log=~/bp-logs/<run>.log; rm -f "$log"; \
  nohup /usr/bin/script -qef -c "sudo -n ./control-program <program>.nbf" \
    "$log" </dev/null >/dev/null 2>&1 & \
  runner_pid=$!; echo "$runner_pid" > ~/bp-logs/<run>.pid; echo "RUNNER_STARTED_PID=$runner_pid LOG=$log"'
ssh xilinx@<board> 'tail -n 120 ~/bp-logs/<run>.log'
```

Require the transcript to contain the target marker (`CORE[0] PASS` or `CORE PASS`) and record its
bitstream and NBF hashes. Store Linux-run transcripts under `~/bp-logs`, not `/tmp`: a board
power-cycle removes `/tmp` evidence, while user-home storage survives the recovery. Treat an
SSH-stream cutoff as inconclusive until the retained log is read. If the root runner cannot be
stopped through its parent `script` process, power-cycle the board, reload the overlay, and start a
fresh run; do not reuse a possibly contaminated fabric.

### Recovering an unreachable board

If the board refuses SSH and the controlled outlet is available, export its state endpoint only
for the current shell and run:

```bash
PYNQ_POWER_STATE_URL='<private-state-endpoint>' \
  codex-skills/bp-fpga-synthesis/scripts/power_cycle_pynq.sh \
  xilinx@192.168.4.35
```

The helper powers the outlet off, waits briefly, powers it on, and waits for both SSH and the
`start_pl_server.py` PYNQ PL manager with bounded timeouts. Do not reload an overlay merely
because SSH returned: on this image it can precede PL-manager readiness and leave the board
unreachable. Do not commit or print the endpoint because it contains a controller credential.
Power cycling removes the loaded
BlackParrot overlay and invalidates prior CMA/DRAM allocation state, so reload the intended overlay
and recheck the bitstream and NBF hashes before running a test.

### Interactive Linux image

The dated Jan. 25 Linux regression image runs `/init`, executes its test scripts, and powers off;
it is not Jack's missing interactive `linux.nbf`. Create a shell derivative without rebuilding
the kernel or initramfs:

```bash
codex-skills/bp-fpga-synthesis/scripts/make_linux_shell_nbf.py \
  riscv/linux/linux-6.6-jhumphri-20250125.nbf /tmp/linux-shell.nbf
```

This replaces `root=/dev/ram0` with the equal-length `rdinit=/bin/sh`. The NBF loader's byte and
halfword read-modify-write expressions are unsafe, so the helper preserves surrounding bytes and
uses aligned 8-byte commands only. Validate success with `Run /bin/sh as init process`, a shell
marker, `uname -a`, `poweroff -f`, and `CORE[0] PASS`. A direct `rdinit` shell does not run the
normal init scripts; mount `/proc` manually before reading `/proc/cpuinfo`.

Use the maintained serialized interactive runner described above. After a
native runtime limit, interruption, or SBI-reset terminal probe, power-cycle the
board, wait for PYNQ readiness, and reload the verified overlay before another
run. Before launching, verify that the runner was built without `DRAM_TEST` and
record exact runner, bitstream, and NBF hashes. Keep host MMIO and fences outside
measured switch regions.

## Application image

The maintained harness has no `fpga-tests` target. For the Linux application
proof, follow the clean `tiny-init-linux-image` flow in
[the Linux guide](../../../linux-tests/README.md). For bare-metal acceptance,
retain the source, integer-only board CRT, compiler flags, ELF, and NBF identities
with the run; the accepted recipes and artifacts are recorded in
[the checkout guide](../../../CURRENT_CHECKOUT.md#fpga-acceptance-identities).
A simulator ELF is not automatically an FPGA image: the board startup and NBF
`--config --debug` preamble must match the selected hardware.

## Required run-state checks

Before interpreting a failure, distinguish these stages in order:

1. package extracted and board-side bitstream SHA matches
2. overlay explicitly reloaded after extraction
3. host runner built without `DRAM_TEST`
4. NBF SHA matches and loader reports its finish command
5. integer startup markers execute
6. resident round trip completes
7. nonresident SRAM-backed round trip completes

Do not change RTL until the failing stage is localized. A host allocation error, diagnostic-only
runner exit, startup/FPU mismatch, MMIO fence stall, and context-switch failure can otherwise all
look like “no output.”

### Silent pre-console Linux triage

When the loader finishes and the core continues retiring instructions but neither OpenSBI nor
Linux prints anything, reduce the image before changing the kernel or host runner:

1. Preserve every NBF configuration record, but keep only firmware memory writes below the Linux
   payload boundary (normally `0x80200000`). Run this OpenSBI-only prefix with the same bitstream
   and runner.
2. If the reduced image has the same IPC/instruction-retirement signature, treat the failure as
   machine-mode firmware startup rather than Linux.
3. Disassemble the exact firmware image. OpenSBI's single-hart election normally loads the
   `_boot_status` address into `a6`, executes `amoswap.w a6,a7,(a6)`, and immediately branches on
   the returned old value. A wrong or stale nonzero value sends the only hart into the deliberate
   secondary-hart wait loop before console initialization.
4. Construct a focused local AMO/branch reproduction using the captured
   architectural inputs. The old `mt_amo_swap_return_test` source/build rule is
   recoverable from `e4242c1c` on an isolated branch; it is not an active harness
   target. Require a clean traced pass before packaging that reproduction for
   the board, and retain source/CRT/ELF/NBF hashes.

The diagnostic intentionally uses `a6` as both the nonzero address input and AMO destination,
uses OpenSBI's plain `amoswap.w` without `.aq`, `.rl`, or `.aqrl`, and places the conditional
branch immediately after the AMO. Do not change the ordering bits or simplify it to a separate
destination register: either change can exercise a different pipeline path or miss the speculative
memory-result catchup case. Record all four
architectural values (two returned old values and two memory values), both immediate branch
decisions, the NBF SHA, and the waveform around the AMO/branch window.

When patching firmware instructions for a board probe, emit aligned 8-byte NBF writes that preserve
the surrounding instruction bytes. Do not emit command `00` or `01` byte/halfword writes. The
current host loader's read-modify-write path uses an incorrect subword shift and ambiguous operator
precedence, so an offline reconstruction of the intended NBF can disassemble correctly even though
the board received different bytes. Confirm the final NBF contains a command `03` at an 8-byte
aligned address for every code patch. Use the repository helper rather than editing NBF lines by
hand; it reconstructs each touched 8-byte block from the source NBF before overlaying the patch:

```bash
codex-skills/bp-fpga-synthesis/scripts/patch_nbf_bytes.py \
  input.nbf output.nbf --patch 0x80000000:probe.bin
```

### Linux PC milestone probes

For a post-OpenSBI silent Linux image, prefer a disposable stop-at-PC probe before adding RTL
instrumentation. `tools/make_linux_milestone_nbf.py` replaces a small physical instruction
window with two long-standing host put-character writes and a normal finish packet:

```bash
python3 tools/make_linux_milestone_nbf.py \
  riscv/linux/linux-6.6-jhumphri-20250125.nbf /tmp/linux-m1.nbf \
  --pc 0x802010d0 --marker 1 --expect-first-word 0x10401073
```

The runner prints `M1` immediately before `CORE PASS` only if execution reached
that exact PC. Run separate probes at increasingly later known physical PCs to bracket a stall.
The optional expected-word guard rejects stale addresses or a mismatched image. These probes are
diagnostic only: host MMIO changes timing and the probe intentionally terminates, so never use them
to measure performance or certify an uninstrumented Linux boot. They are reliable before virtual
memory is enabled. A source-NBF patch after the first main-kernel `satp` write is conclusive only
when the translated physical address of that PC is known: the pre-translation physical address need
not contain the next fetched instruction. `--disable-satp` is safe only after that mapping has been
established, because it clears translation and exits immediately; it is not a continuing Linux
instrumentation mechanism.

For the archived `linux-6.6-jhumphri-20250125.nbf`, begin with this ordered map (each value is
the guard word at that physical PC):

| Marker | PC | Guard word | Meaning |
| --- | --- | --- | --- |
| 1 | `0x802010d0` | `0x10401073` | Linux S-mode entry |
| 2 | `0x80201102` | `0x016eb697` | boot-hart AMO path completed |
| 3 | `0x80201120` | `0x016eb617` | BSS clear completed |
| 4 | `0x8020113c` | `0x4097852e` | stack initialized, first kernel call pending |
| 5 | `0x80c05544` | `0xe8a2711d` | early main-kernel target reached |
| 6 | `0x80c06430` | `0x18079073` | immediately before first main-kernel `satp` write |
| 7 | `0x80201146` | `0x00004517` | early main-kernel routine returned to its S-mode caller |
| 8 | `0x80201000` | `0x01299597` | caller's relocation / `stvec` / `satp` transition helper entered |
| 9 | `0x80201044` | `0x18051073` | immediately before the helper's first `satp` write |

Start at 1 and 6. If one fails, use the intervening entries; add a narrower address range only
after those coarse boundaries identify it. Derive virtual-to-physical translation before attempting
a post-`satp` probe.

### Silent-Linux diagnostic bundle

Before changing RTL or spending another routed build, retain exact source,
runner, package, bitstream, and NBF identities; the closed board transcript;
and the first failed milestone. Select a local reproduction matching the live
architectural inputs. The maintained translated U-mode tests do not by
themselves reproduce an arbitrary S-mode Linux fault.

Use the [test guide](../../../testing/README.md) for clean, bounded `TRACE=1`
runs and retain the closed FST. `tools/satp_fst_tail.awk` can extract SATP writes
and retired-PC tails from streamed VCD; do not resurrect the removed
`run-mt_smode_sv39_entry_test` target from a leftover ELF. The old trace-window
command-line options are not implemented by the current tracer.

The accepted route uses 81 of 140 BRAM tiles; older claims that the image fills
all BRAM are obsolete. Decide whether instrumentation fits using the exact
candidate's routed reports, and first try bounded software probes or local
waveforms when they can answer the question without changing hardware.

Board automation uses the fixed-path overlay helper and serialized runner from
the skill. Keep permission scope tied to those reviewed executables; archived
runner commands are recovery material, not current deployment instructions.
