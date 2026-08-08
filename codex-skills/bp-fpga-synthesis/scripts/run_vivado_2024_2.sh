#!/usr/bin/env bash
set -euo pipefail

vivado_root=/tools/Xilinx/Vivado/2024.2
vitis_lib=/tools/Xilinx/Vitis/2024.2/lib/lnx64.o
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)

source "$vivado_root/settings64.sh"

# This VM's Vivado copy contains a zero-filled libxv_bda.so. Vitis 2024.2 ships
# the matching valid library.  Present it through Vivado's supported patch-area
# mechanism so the loader selects it before the damaged baseline copy.  Using
# LD_PRELOAD here leaks a large Vivado library into shell helpers and IP child
# processes, which breaks SmartConnect XIT elaboration.
if ! file "$vivado_root/lib/lnx64.o/libxv_bda.so" | grep -q 'ELF 64-bit'; then
  if ! file "$vitis_lib/libxv_bda.so" | grep -q 'ELF 64-bit'; then
    echo "No valid 2024.2 libxv_bda.so is available." >&2
    exit 1
  fi
  patch_root="$repo_dir/install/vivado_patch"
  mkdir -p "$patch_root/lib/lnx64.o"
  ln -sfn "$vitis_lib/libxv_bda.so" "$patch_root/lib/lnx64.o/libxv_bda.so"
  export XILINX_PATH="$patch_root${XILINX_PATH:+:$XILINX_PATH}"
fi

exec vivado -mode batch "$@"
