#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)
compiler=${RISCV_LINUX_PROBE_CC:-"$repo_root/install/bin/riscv64-unknown-elf-gcc"}
readelf_bin=${RISCV_LINUX_PROBE_READELF:-"$repo_root/install/bin/riscv64-unknown-elf-readelf"}
output_dir=${RISCV_LINUX_PROBE_OUTPUT_DIR:-"$repo_root/riscv/linux"}
probe="$output_dir/bp_global_cycle_probe"
upload="$output_dir/bp_global_cycle_probe.upload.txt"

[[ -x "$compiler" ]] || {
  echo "FAIL: RISC-V compiler is not executable: $compiler" >&2
  exit 1
}
[[ -x "$readelf_bin" ]] || {
  echo "FAIL: RISC-V readelf is not executable: $readelf_bin" >&2
  exit 1
}

mkdir -p "$output_dir"

"$compiler" \
  -march=rv64ima_zicsr -mabi=lp64 \
  -O2 -ffreestanding -fno-builtin -fno-stack-protector \
  -fno-pic -fno-pie -no-pie \
  -nostdlib -nostartfiles -nodefaultlibs -static \
  -Wl,-e,_start -Wl,--build-id=none -Wl,-z,max-page-size=4096 \
  "$script_dir/bp_global_cycle_probe.c" -o "$probe"

elf_header=$($readelf_bin -h "$probe")
program_headers=$($readelf_bin -l "$probe")

grep -q 'Class:.*ELF64' <<<"$elf_header"
grep -q 'Machine:.*RISC-V' <<<"$elf_header"
grep -q 'Type:.*EXEC' <<<"$elf_header"
if grep -q 'INTERP' <<<"$program_headers"; then
  echo "FAIL: probe unexpectedly contains a dynamic interpreter" >&2
  exit 1
fi

{
  echo "base64 -d >/tmp/bp_global_cycle_probe <<'BP_GLOBAL_CYCLE_EOF'"
  base64 -w 76 "$probe"
  echo "BP_GLOBAL_CYCLE_EOF"
  echo "chmod 755 /tmp/bp_global_cycle_probe"
  echo "/tmp/bp_global_cycle_probe"
  echo "echo PROBE_EXIT=\$?"
} >"$upload"

echo "PROBE_ELF=$probe"
echo "PROBE_SHA256=$(sha256sum "$probe" | awk '{print $1}')"
echo "PROBE_SIZE_BYTES=$(stat -c %s "$probe")"
echo "UPLOAD_SNIPPET=$upload"
