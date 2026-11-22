#!/usr/bin/env bash
set -u

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=${ZP_REPO_DIR:-$(git -C "$script_dir" rev-parse --show-toplevel 2>/dev/null)}
[[ -n "$repo_dir" ]] && repo_dir=$(cd "$repo_dir" && pwd) || {
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
check_path "$repo_dir/import/black-parrot/external/basejump_stl/.git" "BlackParrot nested BaseJump submodule"
check_path "$repo_dir/import/black-parrot/external/HardFloat/.git" "BlackParrot nested HardFloat submodule"
check_path "$repo_dir/import/black-parrot/external/bedrock/.git" "BlackParrot nested BedRock submodule"
check_path "$repo_dir/install/bin" "prepared tool installation"
check_path "$repo_dir/install/include/boost/coroutine2/all.hpp" "Boost coroutine headers"
check_path "$repo_dir/install/lib/libboost_coroutine.so" "Boost coroutine library"
check_path "$repo_dir/install/lib/libboost_coroutine.so.1.72.0" "Boost coroutine runtime SONAME"
check_path "$repo_dir/install/lib/libboost_context.so" "Boost context library"
check_path "$repo_dir/install/lib/libboost_context.so.1.72.0" "Boost context runtime SONAME"
check_path "$repo_dir/install/lib/libboost_system.so" "Boost system library"
check_path "$repo_dir/install/lib/libboost_system.so.1.72.0" "Boost system runtime SONAME"
check_path "$repo_dir/riscv/bootrom/bootrom.none.riscv" "RISC-V boot ROM"
check_path "$repo_dir/install/gen/v/rv_plic/rtl/rv_plic_reg_pkg.sv" "generated OpenTitan PLIC RTL"

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

if [[ -e "$repo_dir/import/black-parrot/.git" ]]; then
  for nested in external/basejump_stl external/HardFloat external/bedrock; do
    if [[ -e "$repo_dir/import/black-parrot/$nested/.git" ]]; then
      expected=$(git -C "$repo_dir/import/black-parrot" ls-tree HEAD "$nested" | awk '{print $3}')
      actual=$(git -C "$repo_dir/import/black-parrot/$nested" rev-parse HEAD 2>/dev/null || true)
      printf 'BP %-20s pinned: %.12s checkout: %.12s\n' "$nested" "$expected" "$actual"
      if [[ -z "$expected" || "$expected" != "$actual" ]]; then
        echo "FAIL: BlackParrot nested $nested checkout does not match its gitlink"
        fail=1
      fi
    fi
  done
fi

if [[ -e "$repo_dir/import/basejump_stl/.git" ]]; then
  expected=$(git -C "$repo_dir" ls-tree HEAD import/basejump_stl | awk '{print $3}')
  actual=$(git -C "$repo_dir/import/basejump_stl" rev-parse HEAD 2>/dev/null || true)
  printf 'BSG pinned:  %.12s\n' "$expected"
  printf 'BSG checkout:%.12s\n' "$actual"
  if [[ "$expected" != "$actual" ]]; then
    echo "FAIL: BaseJump checkout does not match the top-level gitlink"
    fail=1
  fi
fi

# The PYNQ Vivado source list resolves the top-level BaseJump memory wrapper.
# Historical BlackParrot revisions can request ram_style_p while an older
# top-level BaseJump gitlink silently supplies a wrapper without that parameter;
# Verilator may resolve the nested copy instead, so catch the mismatch here.
context_mem="$repo_dir/import/black-parrot/bp_be/src/v/bp_be_context_mem.sv"
top_bsg_mem="$repo_dir/import/basejump_stl/bsg_mem/bsg_mem_1r1w_sync.sv"
if [[ -f "$context_mem" ]] && grep -Eq '\.ram_style_p[[:space:]]*\(' "$context_mem"; then
  if [[ -f "$top_bsg_mem" ]] && grep -Eq 'parameter[[:space:]]+ram_style_p' "$top_bsg_mem"; then
    echo "OK   BaseJump context-SRAM ram_style parameter"
  else
    echo "FAIL: BlackParrot context SRAM requests ram_style_p but the top-level BaseJump wrapper does not declare it"
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
