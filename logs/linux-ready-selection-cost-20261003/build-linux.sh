#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
out=logs/linux-ready-selection-cost-20261003/ready_selection_benchmark
/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-gcc \
  -Os -Wall -Wextra -Werror -static -nostdlib -nostartfiles -ffreestanding \
  -fno-stack-protector -ffixed-s11 -Wl,-e,_start -Wl,--build-id=none \
  -march=rv64imafdc_zicsr_zbb -mabi=lp64d -mcmodel=medany -mno-relax \
  -DBP_NUM_CONTEXTS=10 -DBP_NUM_THREADS=2 -Itesting \
  logs/linux-ready-selection-cost-20261003/ready_selection_benchmark.c -o "$out"
/home/jhumphri/black-parrot-sdk/install/bin/riscv64-unknown-linux-gnu-objdump \
  -d "$out" > logs/linux-ready-selection-cost-20261003/disassembly.txt
sha256sum "$out"
