#!/bin/sh
# Package a built seL4 elfloader behind pinned BlackParrot OpenSBI as an NBF.

set -eu

if [ "$#" -ne 4 ]; then
    echo "usage: $0 /path/to/sel4-build /path/to/opensbi-repo /path/to/work-dir output.nbf" >&2
    exit 2
fi

sel4_build=$(realpath "$1")
opensbi_repo=$(realpath "$2")
work_dir=$3
output=$4
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
opensbi_revision=7830e987856eb1319c82664702892b6d50a93e7a
sel4_cross_prefix=${SEL4_CROSS_PREFIX:-$project_root/install/bin/riscv64-unknown-elf-}
opensbi_cross_prefix=${OPENSBI_CROSS_PREFIX:-riscv64-unknown-linux-gnu-}
nbf_tool=${NBF_TOOL:-$project_root/import/black-parrot/bp_common/software/py/nbf.py}
overlay="$project_root/linux-tests/opensbi-platform/blackparrot"
elfloader="$sel4_build/elfloader/elfloader"
dtb="$sel4_build/kernel/kernel.dtb"

test -x "${sel4_cross_prefix}objcopy" || { echo "missing ${sel4_cross_prefix}objcopy" >&2; exit 1; }
test -x "${opensbi_cross_prefix}gcc" || { echo "missing ${opensbi_cross_prefix}gcc" >&2; exit 1; }
test -f "$nbf_tool" || { echo "missing NBF tool: $nbf_tool" >&2; exit 1; }
test -f "$elfloader" || { echo "missing seL4 elfloader: $elfloader" >&2; exit 1; }
test -f "$dtb" || { echo "missing seL4 DTB: $dtb" >&2; exit 1; }
test "$(git -C "$opensbi_repo" rev-parse "$opensbi_revision^{commit}")" = "$opensbi_revision"

mkdir -p "$work_dir"
work_dir=$(realpath "$work_dir")
opensbi_source="$work_dir/opensbi-src"
opensbi_build="$work_dir/opensbi-build"
payload="$work_dir/elfloader.bin"
mem="$work_dir/sel4-rpc.mem"
raw_nbf="$work_dir/sel4-rpc.raw.nbf"

if [ ! -d "$opensbi_source/.git" ] && [ ! -f "$opensbi_source/.git" ]; then
    git -C "$opensbi_repo" worktree add --detach "$opensbi_source" "$opensbi_revision"
fi
if [ "$(git -C "$opensbi_source" rev-parse HEAD)" != "$opensbi_revision" ]; then
    echo "unexpected OpenSBI worktree revision" >&2
    exit 1
fi

install -D -m 0644 "$overlay/Kconfig" "$opensbi_source/platform/generic/blackparrot/Kconfig"
install -D -m 0644 "$overlay/objects.mk" "$opensbi_source/platform/generic/blackparrot/objects.mk"
install -D -m 0644 "$overlay/platform.c" "$opensbi_source/platform/generic/blackparrot/platform.c"
install -D -m 0644 "$overlay/icache_prefix.h" "$opensbi_source/platform/generic/blackparrot/icache_prefix.h"
install -D -m 0644 "$overlay/configs/defconfig" \
    "$opensbi_source/platform/generic/blackparrot/configs/defconfig"

"${sel4_cross_prefix}objcopy" -O binary "$elfloader" "$payload"
make -C "$opensbi_source" -j4 \
    O="$opensbi_build" \
    PLATFORM=generic/blackparrot \
    CROSS_COMPILE="$opensbi_cross_prefix" \
    "CC=${opensbi_cross_prefix}gcc -std=gnu17" \
    PLATFORM_RISCV_XLEN=64 \
    PLATFORM_RISCV_ISA=rv64imafdc_zicsr_zifencei \
    PLATFORM_RISCV_ABI=lp64d \
    PLATFORM_FDT_PATH="$dtb" \
    PAYLOAD_PATH="$payload" \
    PLATFORM_ADDITIONAL_CFLAGS=-DPLATFORM_HART_COUNT=1 \
    BP_ICACHE_PREFIX_ENABLE=0 \
    FW_PAYLOAD=y

firmware="$opensbi_build/platform/generic/blackparrot/firmware/fw_payload.elf"
"${sel4_cross_prefix}objcopy" -O verilog "$firmware" "$mem"
sed -i 's/@8/@0/g' "$mem"
python3 "$nbf_tool" --skip_zeros --config --mem "$mem" --ncpus 1 > "$raw_nbf"

selector='02_0000000000308000_0000000000000001'
if [ "$(grep -Fxc "$selector" "$raw_nbf")" -ne 1 ]; then
    echo "NBF does not contain exactly one default mtime selector" >&2
    exit 1
fi
sed -i "s/^$selector$/02_0000000000308000_0000000000000002/" "$raw_nbf"
mkdir -p "$(dirname -- "$output")"
cp "$raw_nbf" "$output"

echo "NBF=$output"
sha256sum "$elfloader" "$firmware" "$output"
