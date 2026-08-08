#!/usr/bin/env bash
set -euo pipefail

vivado_root=/tools/Xilinx/Vivado/2024.2
vitis_lib=/tools/Xilinx/Vitis/2024.2/lib/lnx64.o
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
guard="$repo_dir/install/lib/vivado_preload_guard.so"

source "$vivado_root/settings64.sh"

# This VM's Vivado copy contains a zero-filled libxv_bda.so. Vitis 2024.2 ships
# the matching valid library, so put that same-release directory first.
if ! file "$vivado_root/lib/lnx64.o/libxv_bda.so" | grep -q 'ELF 64-bit'; then
  if ! file "$vitis_lib/libxv_bda.so" | grep -q 'ELF 64-bit'; then
    echo "No valid 2024.2 libxv_bda.so is available." >&2
    exit 1
  fi
  if [[ ! -f "$guard" || "$script_dir/vivado_preload_guard.c" -nt "$guard" ]]; then
    mkdir -p "$(dirname "$guard")"
    gcc -shared -fPIC -O2 -o "$guard" "$script_dir/vivado_preload_guard.c"
  fi
  export LD_LIBRARY_PATH="$vitis_lib:${LD_LIBRARY_PATH:-}"
  export LD_PRELOAD="$vitis_lib/libxv_bda.so:$guard"
fi

exec vivado -mode batch "$@"
