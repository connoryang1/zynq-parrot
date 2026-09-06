#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
toolchain_dir="$repo_dir/import/black-parrot-sdk/riscv-gnu-toolchain"

if [[ ! -e "$toolchain_dir/.git" ]]; then
  echo "Missing initialized SDK GNU toolchain: $toolchain_dir" >&2
  exit 1
fi

set_mirror() {
  local name=$1
  local url=$2
  local module_git
  git -C "$toolchain_dir" config "submodule.$name.url" "$url"
  module_git=$(git -C "$toolchain_dir" rev-parse --git-path "modules/$name")
  if [[ -d "$module_git" ]]; then
    git --git-dir="$module_git" config remote.origin.url "$url"
  fi
}

set_mirror binutils https://github.com/riscvarchive/riscv-binutils-gdb.git
set_mirror gdb https://gnu.googlesource.com/binutils-gdb
set_mirror glibc https://github.com/bminor/glibc.git
set_mirror gcc https://github.com/gcc-mirror/gcc.git
set_mirror newlib https://github.com/RTEMS/sourceware-mirror-newlib-cygwin.git

git -C "$toolchain_dir" submodule update --init --depth 1 binutils gcc gdb glibc newlib

failed=0
for name in binutils gcc gdb glibc newlib; do
  expected=$(git -C "$toolchain_dir" ls-tree HEAD "$name" | awk '{print $3}')
  actual=$(git -C "$toolchain_dir/$name" rev-parse HEAD)
  printf '%-8s expected=%s actual=%s\n' "$name" "$expected" "$actual"
  if [[ "$expected" != "$actual" ]]; then
    failed=1
  fi
done

if (( failed )); then
  echo "Mirror checkout did not preserve every pinned revision." >&2
  exit 1
fi
echo "Pinned GNU dependency mirrors are ready."
