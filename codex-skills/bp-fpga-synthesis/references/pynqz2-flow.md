# PYNQ-Z2 Build And Deployment Reference

## Current build

From `cosim/black-parrot-example/vivado`:

```bash
make fpga_build pack_bitstream \
  BOARDNAME=pynqz2 \
  VIVADO_VERSION=2024.2 \
  VIVADO_MODE=batch \
  CFG=e_bp_unicore_zynqparrot_cfg
```

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

The historical `bp_unicore_zynqparrot_cfg_p` argument is not the current enum used by this
repository. Prefer `e_bp_unicore_zynqparrot_cfg` unless the active branch explicitly adds a new
configuration.

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

### Recovering an unreachable board

If the board refuses SSH and the controlled outlet is available, export its state endpoint only
for the current shell and run:

```bash
PYNQ_POWER_STATE_URL='<private-state-endpoint>' \
  codex-skills/bp-fpga-synthesis/scripts/power_cycle_pynq.sh \
  xilinx@192.168.4.35
```

The helper powers the outlet off, waits briefly, powers it on, and polls SSH with bounded timeouts.
Do not commit or print the endpoint because it contains a controller credential. Treat a successful
SSH reconnect only as evidence that the board OS rebooted. Power cycling removes the loaded
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

The Jan. 24 historical bitstream must use its historical threaded FIFO decoder. The newer
`bsg_host` polling runner can stall this image at about 0.133 IPC with no console output, while the
compatible runner boots near 0.5 IPC. Preserve the threaded decoder and apply only the owned-CMA
fix: never reuse a DRAM pointer from a previous `control-program` process. The historical monitor
thread is not joined and can segfault after a clean target poweroff; treat that as a host teardown
bug only when `CORE[0] PASS` and the target poweroff are already present.

Before an application run, inspect the Makefile or compile command for `DRAM_TEST`. It must be
absent. That mode performs a destructive 64 MiB connectivity diagnostic and is not evidence that
an NBF loaded or executed. Program the freshly extracted overlay in an interactive board shell:

```bash
make load_bitstream \
  BOARDNAME=pynqz2 \
  VIVADO_VERSION=2024.2 \
  VIVADO_MODE=batch

sudo ./control-program <program>.nbf
```

Record the board-side bitstream and NBF SHA immediately before the run. A successful staged
context-cache probe prints `ABRrNP` and `CORE[0] PASS`. Do not put host MMIO followed by a fence
inside the measured switch region; that tests the I/O drain path rather than a pure handoff.

## Application image

For the maintained FPGA regression images, use:

```bash
make -C testing fpga-tests NUM_THREADS=2 NUM_CONTEXTS=4
```

This rebuilds the integer-only DRAMFS startup and emits NBFs with the required `--config --debug`
preamble. Preserve the exact SDK revision and compiler flags with performance-sensitive programs.

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
4. Build the focused diagnostic and verify it in a clean traced simulator before the board:

   ```bash
   make -C testing clean run-mt_amo_swap_return_test \
     TRACE=1 NUM_THREADS=2 NUM_CONTEXTS=4
   make -C testing \
     "$PWD/riscv/bp-tests/mt_amo_swap_return_test_fpga.nbf" \
     NUM_THREADS=2 NUM_CONTEXTS=4
   ```

The diagnostic intentionally uses `a6` as both the nonzero address input and AMO destination,
uses OpenSBI's plain `amoswap.w` without `.aq`, `.rl`, or `.aqrl`, and places the conditional
branch immediately after the AMO. Do not change the ordering bits or simplify it to a separate
destination register: either change can exercise a different pipeline path or miss the speculative
memory-result catchup case. Record all four
architectural values (two returned old values and two memory values), both immediate branch
decisions, the NBF SHA, and the waveform around the AMO/branch window.

Board automation calls `sudo -n` so it cannot pause invisibly at a password prompt. Before a
remote run, execute `sudo -v` and confirm `sudo -n true` in the same board terminal that will
launch the command. Older images commonly keep sudo timestamps per TTY, so a separate SSH session
will still require a password. In that case, run the exact validation command manually in the
authorized terminal; do not create an unvalidated sudoers fragment merely to bridge sessions.
