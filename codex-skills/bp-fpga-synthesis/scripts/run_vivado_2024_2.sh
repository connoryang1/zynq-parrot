#!/usr/bin/env bash
set -euo pipefail

vivado_root=/tools/Xilinx/Vivado/2024.2
vitis_lib=/tools/Xilinx/Vitis/2024.2/lib/lnx64.o

source "$vivado_root/settings64.sh"

# This VM's Vivado copy contains a zero-filled libxv_bda.so. Vitis 2024.2 ships
# the matching valid library, so put that same-release directory first.
if ! file "$vivado_root/lib/lnx64.o/libxv_bda.so" | grep -q 'ELF 64-bit'; then
  if ! file "$vitis_lib/libxv_bda.so" | grep -q 'ELF 64-bit'; then
    echo "No valid 2024.2 libxv_bda.so is available." >&2
    exit 1
  fi
  export LD_LIBRARY_PATH="$vitis_lib:${LD_LIBRARY_PATH:-}"
fi

exec vivado -mode batch "$@"
