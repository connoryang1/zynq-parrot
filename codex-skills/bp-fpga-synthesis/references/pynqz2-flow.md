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
