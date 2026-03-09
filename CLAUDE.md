# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

ZynqParrot is a co-simulation and FPGA framework for developing accelerators (primarily the BlackParrot RISC-V processor) on Xilinx Zynq FPGAs. It provides a unified methodology to develop and test designs in Verilator/VCS/Xcelium simulation, then deploy the same RTL to FPGA hardware without code changes.

## Setup

```bash
make checkout      # initialize all submodules
make prep_lite     # build minimal toolchain (Verilator, basic SDK) — sufficient for simulation
make prep          # full build: RISC-V GNU toolchain, all compilers (1-2 hours)
```

## Key Directory Layout

```
cosim/                   # Co-simulation infrastructure and examples
  mk/                    # Shared Makefile fragments (Makefile.verilator, .vcs, .vivado, etc.)
  black-parrot-example/  # Primary BlackParrot co-sim design
    Makefile.design      # Design configuration (AXI port widths, bootrom, NBF generation)
    ps.cpp / ps.hpp      # ARM PS control program (same file runs in sim and on hardware)
    verilator/           # Verilator build directory — run sim here
    vivado/              # Vivado FPGA build
    zynq/                # On-board execution
  include/               # Simulator-specific C++ headers (verilator/, vcs/, zynq/, etc.)
  v/                     # Shared testbench Verilog (bsg_nonsynth_zynq_testbench.sv, etc.)
import/                  # Git submodules
  black-parrot/          # BlackParrot RISC-V RTL
  black-parrot-sdk/      # RISC-V toolchain, perch library, test programs
  black-parrot-tools/    # Development tools
  black-parrot-subsystems/ # L2, PLIC, DMA subsystems
  bsg_manycore/          # BSG Manycore accelerator RTL
testing/                 # Custom BlackParrot tests (multithreading, CSR isolation, etc.)
software/                # Petalinux / XSA build infrastructure
Makefile.common          # Exports all canonical path variables (BLACKPARROT_DIR, BP_SDK_DIR, etc.)
Makefile.config          # Board selection, tool paths
```

## Path Variables (from Makefile.common)

All design Makefiles `include $(TOP)/Makefile.common` to get:

| Variable | Path |
|---|---|
| `BLACKPARROT_DIR` | `import/black-parrot` |
| `BP_SDK_DIR` | `import/black-parrot-sdk` |
| `BP_SDK_INSTALL_DIR` | `import/black-parrot-sdk/install` |
| `BP_SDK_LIB_DIR` | `import/black-parrot-sdk/install/lib` |
| `BP_COMMON_DIR` | `import/black-parrot/bp_common` |
| `BASEJUMP_STL_DIR` | `import/black-parrot/external/basejump_stl` |
| `COSIM_DIR` | `cosim/` |

## RISC-V Toolchain

After `make prep_lite`, the toolchain is at `import/black-parrot-sdk/install/bin/` and on `PATH` when using Makefile.common. Key binaries:

- **Compiler**: `riscv64-unknown-elf-dramfs-gcc`
- **Objcopy**: `riscv64-unknown-elf-dramfs-objcopy`
- **Flags**: `-march=rv64gc -mabi=lp64d -mcmodel=medany -I$(BP_SDK_INSTALL_DIR)/include`
- **Link**: `-T$(BP_SDK_INSTALL_DIR)/linker/riscv.ld -L$(BP_SDK_LIB_DIR) -Wl,--whole-archive -lperchbm -Wl,--no-whole-archive`

Programs run on BlackParrot are distributed as `.nbf` (network boot file) format. Convert from ELF:
```bash
riscv64-unknown-elf-dramfs-objcopy -O verilog prog.riscv prog.mem
sed -i "s/@8/@0/g" prog.mem
python3 $(BP_COMMON_DIR)/software/py/nbf.py --debug --skip_zeros --config --mem prog.mem --ncpus 1 > prog.nbf
```

## Running Tests (testing/)

```bash
cd testing/
make sim                         # build Verilator simulator (one-time, ~10 min)
make run-multithreading_demo     # compile and run one test
make run-mt_benchmark
make all                         # run all tests
make clean                       # remove bin/ directory
```

Tests compile from `testing/*.c` → `testing/bin/*.riscv` → `testing/bin/*.nbf`, then run via `cosim/black-parrot-example/verilator/`.

## Running a Co-Sim Design (Verilator)

```bash
cd cosim/black-parrot-example/verilator/
make                                # build simulator
make run NBF_FILE=hello_world.nbf  # run a program
make clean
```

## FPGA Build and Deploy

```bash
# Build bitstream
cd cosim/black-parrot-example/vivado/
make clean fpga_build pack_bitstream BOARDNAME=pynqz2 VIVADO_VERSION=2022.1 VIVADO_MODE=batch

# Deploy to board (requires SSH access)
cd cosim/black-parrot-example/zynq/
make load_bitstream run BOARDNAME=pynqz2 NBF_FILE=hello_world.nbf
```

Supported boards: `pynqz2` (Artix-7), `ultra96v2` (UltraScale+), `vu47p` (UART bridge mode).

## Architecture: PS/PL Interface

The PS (ARM CPU running Linux) communicates with PL (accelerator) via:
- **GP0** (10-bit addr): Narrow control/CSR port — reset, bootrom load, performance counters
- **GP1/GP2** (30-bit addr): DRAM aperture and memory-mapped accelerator space
- **HP0/HP1** (32-bit addr): High-performance data ports to DRAM

The same `ps.cpp`/`ps.hpp` host program compiles for Verilator simulation, VCS, and actual Zynq hardware — the `cosim/include/` directory provides the simulator-specific shims.

## Adding a New Co-Sim Example

Each example in `cosim/` has:
1. `Makefile.design` — defines AXI port widths, builds bootrom and `bsg_blackparrot_pkg.sv`
2. `ps.cpp` / `ps.hpp` — control program (PS side)
3. `v/` — design-specific RTL
4. `verilator/Makefile`, `vcs/Makefile`, `vivado/Makefile`, `zynq/Makefile` — each includes `Makefile.design` then the appropriate `$(COSIM_MK_DIR)/Makefile.<backend>`
