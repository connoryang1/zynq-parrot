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

Keep deployment separate from build validation. With authorization, copy the packed bitstream to
the board, unpack it from `cosim/black-parrot-example/zynq`, and run:

```bash
make unpack_bitstream load_bitstream run \
  BOARDNAME=pynqz2 \
  VIVADO_VERSION=2024.2 \
  VIVADO_MODE=batch \
  NBF_FILE=hello_world.nbf
```

Confirm the board address, user, destination checkout, and NBF before copying or programming.

## Application image

Build the RISC-V application through the pinned SDK. Copy the resulting `.riscv` into the
BlackParrot Verilator directory and run `make prog PROG=<name>` to create the NBF. Preserve the
exact SDK revision and compiler flags with performance-sensitive programs.
