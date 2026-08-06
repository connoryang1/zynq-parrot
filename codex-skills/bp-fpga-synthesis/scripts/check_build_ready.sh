#!/usr/bin/env bash
set -u

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null) || {
  echo "FAIL: skill is not inside a git checkout" >&2
  exit 1
}

fail=0
check_path() {
  if [[ -e "$1" ]]; then
    printf 'OK   %s\n' "$2"
  else
    printf 'MISS %s (%s)\n' "$2" "$1"
    fail=1
  fi
}

printf 'Top-level:   %s\n' "$(git -C "$repo_dir" rev-parse --short HEAD)"
printf 'Branch:      %s\n' "$(git -C "$repo_dir" branch --show-current)"
check_path /tools/Xilinx/Vivado/2024.2/settings64.sh "Vivado 2024.2"
if file /tools/Xilinx/Vivado/2024.2/lib/lnx64.o/libxv_bda.so 2>/dev/null | grep -q 'ELF 64-bit'; then
  echo "OK   Vivado core library"
elif file /tools/Xilinx/Vitis/2024.2/lib/lnx64.o/libxv_bda.so 2>/dev/null | grep -q 'ELF 64-bit'; then
  echo "OK   Vivado core library fallback from Vitis 2024.2"
else
  echo "MISS valid Vivado/Vitis 2024.2 libxv_bda.so"
  fail=1
fi
check_path "$repo_dir/import/black-parrot/.git" "BlackParrot submodule"
check_path "$repo_dir/import/basejump_stl/.git" "BaseJump submodule"
check_path "$repo_dir/install/bin" "prepared tool installation"
check_path "$repo_dir/install/include/boost/coroutine2/all.hpp" "Boost coroutine headers"
check_path "$repo_dir/install/lib/libboost_coroutine.so" "Boost coroutine library"
check_path "$repo_dir/install/lib/libboost_coroutine.so.1.72.0" "Boost coroutine runtime SONAME"
check_path "$repo_dir/install/lib/libboost_context.so" "Boost context library"
check_path "$repo_dir/install/lib/libboost_context.so.1.72.0" "Boost context runtime SONAME"
check_path "$repo_dir/install/lib/libboost_system.so" "Boost system library"
check_path "$repo_dir/install/lib/libboost_system.so.1.72.0" "Boost system runtime SONAME"
check_path "$repo_dir/riscv/bootrom/bootrom.none.riscv" "RISC-V boot ROM"

if [[ -e "$repo_dir/import/black-parrot/.git" ]]; then
  expected=$(git -C "$repo_dir" ls-tree HEAD import/black-parrot | awk '{print $3}')
  actual=$(git -C "$repo_dir/import/black-parrot" rev-parse HEAD 2>/dev/null || true)
  printf 'BP pinned:   %.12s\n' "$expected"
  printf 'BP checkout: %.12s\n' "$actual"
  if [[ "$expected" != "$actual" ]]; then
    echo "FAIL: BlackParrot checkout does not match the top-level gitlink"
    fail=1
  fi
fi

if [[ -n "$(git -C "$repo_dir" status --short --untracked-files=no)" ]]; then
  echo "WARN: tracked top-level files are modified; do not use this state for a baseline"
fi

if (( fail )); then
  echo "NOT READY"
  exit 1
fi
echo "BUILD READY"
