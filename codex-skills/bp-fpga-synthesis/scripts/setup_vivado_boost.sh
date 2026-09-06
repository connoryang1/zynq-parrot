#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
vivado_root=/tools/Xilinx/Vivado/2024.2
boost_root="$vivado_root/tps/boost_1_72_0"
vivado_lib="$vivado_root/lib/lnx64.o"

require_path() {
  if [[ ! -e "$1" ]]; then
    echo "Missing Vivado-provided Boost component: $1" >&2
    exit 1
  fi
}

require_path "$boost_root/boost/coroutine2/all.hpp"
for component in coroutine context system; do
  require_path "$vivado_lib/libboost_${component}.so.1.72.0"
done

mkdir -p "$repo_dir/install/include" "$repo_dir/install/lib"
ln -sfn "$boost_root/boost" "$repo_dir/install/include/boost"
for component in coroutine context system; do
  source_lib="$vivado_lib/libboost_${component}.so.1.72.0"
  ln -sfn "$source_lib" "$repo_dir/install/lib/libboost_${component}.so"
  ln -sfn "$source_lib" "$repo_dir/install/lib/libboost_${component}.so.1.72.0"
done

echo "Vivado-provided Boost 1.72 is available under install/."
