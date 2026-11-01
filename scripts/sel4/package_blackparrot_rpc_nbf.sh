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
opensbi_fw_options=${OPENSBI_FW_OPTIONS:-0x1}
opensbi_riscv_isa=${OPENSBI_RISCV_ISA:-rv64imafdc_zicsr_zifencei}
base_firmware=${OPENSBI_BASE_FIRMWARE:-}
nbf_tool=${NBF_TOOL:-$project_root/import/black-parrot/bp_common/software/py/nbf.py}
overlay="$project_root/linux-tests/opensbi-platform/blackparrot"
elfloader="$sel4_build/elfloader/elfloader"
rpc_server="$sel4_build/apps/sel4test-driver/sel4test-tests/sel4-rpc-server"
dtb="$sel4_build/kernel/kernel.dtb"

if [ "${NBF_DEBUG:-0}" != 0 ]; then
    echo "NBF_DEBUG is unsupported for OpenSBI: debug entry requires a dret startup stub" >&2
    exit 2
fi
test -x "${sel4_cross_prefix}objcopy" || { echo "missing ${sel4_cross_prefix}objcopy" >&2; exit 1; }
test -x "${sel4_cross_prefix}readelf" || { echo "missing ${sel4_cross_prefix}readelf" >&2; exit 1; }
test -x "${sel4_cross_prefix}objdump" || { echo "missing ${sel4_cross_prefix}objdump" >&2; exit 1; }
if [ -z "$base_firmware" ]; then
    test -x "${opensbi_cross_prefix}gcc" || { echo "missing ${opensbi_cross_prefix}gcc" >&2; exit 1; }
else
    base_firmware=$(realpath "$base_firmware")
    test -f "$base_firmware" || { echo "missing base OpenSBI firmware: $base_firmware" >&2; exit 1; }
fi
test -f "$nbf_tool" || { echo "missing NBF tool: $nbf_tool" >&2; exit 1; }
test -f "$elfloader" || { echo "missing seL4 elfloader: $elfloader" >&2; exit 1; }
test -f "$rpc_server" || { echo "missing seL4 RPC server: $rpc_server" >&2; exit 1; }
test -f "$dtb" || { echo "missing seL4 DTB: $dtb" >&2; exit 1; }
test "$(git -C "$opensbi_repo" rev-parse "$opensbi_revision^{commit}")" = "$opensbi_revision"

# The dedicated server is a separate translation unit from the driver. If it
# misses seL4's generated platform configuration, its timestamp helper silently
# compiles to rdcycle; the clean protected-server CSR image then traps with no
# version-1 fault continuation. Reject that image before it can be packaged.
rpc_server_disassembly=$("${sel4_cross_prefix}objdump" -d "$rpc_server")
rpc_global_cycle_reads=$(printf '%s\n' "$rpc_server_disassembly" |
    grep -c '0xcc0' || true)
rpc_arch_cycle_reads=$(printf '%s\n' "$rpc_server_disassembly" |
    grep -c '[[:space:]]rdcycle[[:space:]]' || true)
if [ "$rpc_global_cycle_reads" -lt 2 ] || [ "$rpc_arch_cycle_reads" -ne 0 ]; then
    echo "RPC server has wrong cycle-counter instructions: global=$rpc_global_cycle_reads architectural=$rpc_arch_cycle_reads" >&2
    exit 1
fi

mkdir -p "$work_dir"
work_dir=$(realpath "$work_dir")
opensbi_source="$work_dir/opensbi-src"
opensbi_build="$work_dir/opensbi-build"
payload="$work_dir/elfloader.bin"
mem="$work_dir/sel4-rpc.mem"
raw_nbf="$work_dir/sel4-rpc.raw.nbf"
firmware_base=0x80000000
payload_entry=$("${sel4_cross_prefix}readelf" -h "$elfloader" | awk '/Entry point address:/ { print $4 }')
case "$payload_entry" in
    0x*) ;;
    *) echo "could not read elfloader entry address" >&2; exit 1 ;;
esac
payload_offset=$((payload_entry - firmware_base))
if [ "$payload_offset" -lt 0 ] || [ $((payload_offset % 4096)) -ne 0 ]; then
    echo "elfloader entry is not a page-aligned OpenSBI payload address: $payload_entry" >&2
    exit 1
fi
payload_offset_hex=$(printf '0x%x' "$payload_offset")

"${sel4_cross_prefix}objcopy" -O binary "$elfloader" "$payload"
# OpenSBI's generated linker script does not depend on command-line make
# variables, and its clean target leaves that script behind.  Reusing an output
# directory after the elfloader entry moves can therefore silently retain an
# old FW_PAYLOAD_OFFSET and make the elfloader self-relocation overlap.  Rebuild
# the script-owned output directory from scratch.
rm -rf -- "$opensbi_build"
firmware="$opensbi_build/platform/generic/blackparrot/firmware/fw_payload.elf"
if [ -n "$base_firmware" ]; then
    mkdir -p "$(dirname -- "$firmware")"
    cp "$base_firmware" "$firmware"
    base_payload_entry=$("${sel4_cross_prefix}readelf" -SW "$firmware" |
        awk '$2 == ".payload" { print "0x" $4 }')
    if [ -z "$base_payload_entry" ] ||
       [ "$((base_payload_entry))" -ne "$((payload_entry))" ]; then
        echo "base OpenSBI payload at $base_payload_entry, expected $payload_entry" >&2
        exit 1
    fi
    "${sel4_cross_prefix}objcopy" --update-section ".payload=$payload" "$firmware"
    embedded_payload="$work_dir/embedded-payload.bin"
    "${sel4_cross_prefix}objcopy" --dump-section ".payload=$embedded_payload" "$firmware"
    cmp "$payload" "$embedded_payload"
else
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
    install -D -m 0644 "$overlay/rpc.c" "$opensbi_source/platform/generic/blackparrot/rpc.c"
    install -D -m 0644 "$overlay/rpc.h" "$opensbi_source/platform/generic/blackparrot/rpc.h"
    install -D -m 0644 "$project_root/sel4/internal/blackparrot_rpc_abi.h" \
        "$opensbi_source/platform/generic/blackparrot/blackparrot_rpc_abi.h"
    install -D -m 0644 "$overlay/configs/defconfig" \
        "$opensbi_source/platform/generic/blackparrot/configs/defconfig"

    make -C "$opensbi_source" -j4 \
        O="$opensbi_build" \
        PLATFORM=generic/blackparrot \
        CROSS_COMPILE="$opensbi_cross_prefix" \
        "CC=${opensbi_cross_prefix}gcc -std=gnu17" \
        PLATFORM_RISCV_XLEN=64 \
        PLATFORM_RISCV_ISA="$opensbi_riscv_isa" \
        PLATFORM_RISCV_ABI=lp64d \
        PLATFORM_FDT_PATH="$dtb" \
        PAYLOAD_PATH="$payload" \
        FW_PAYLOAD_OFFSET="$payload_offset_hex" \
        FW_OPTIONS="$opensbi_fw_options" \
        PLATFORM_ADDITIONAL_CFLAGS=-DPLATFORM_HART_COUNT=1 \
        BP_ICACHE_PREFIX_ENABLE=0 \
        FW_PAYLOAD=y
fi

embedded_payload_entry=$("${sel4_cross_prefix}readelf" -SW "$firmware" |
    awk '$2 == ".payload" { print "0x" $4 }')
if [ -z "$embedded_payload_entry" ] ||
    [ "$((embedded_payload_entry))" -ne "$((payload_entry))" ]; then
    echo "OpenSBI embedded payload at $embedded_payload_entry, expected $payload_entry" >&2
    exit 1
fi
"${sel4_cross_prefix}objcopy" -O verilog "$firmware" "$mem"
sed -i 's/@8/@0/g' "$mem"
set -- --skip_zeros --config
set -- "$@" --mem "$mem" --ncpus 1
python3 "$nbf_tool" "$@" > "$raw_nbf"

# OpenSBI has no debug-ROM resume stub.  Keep this invariant adjacent to the
# generated artifact as well as the environment check above, so a replacement
# NBF tool cannot silently reintroduce debug entry.
debug_assert='02_000000000030c000_0000000000000001'
debug_deassert='02_000000000030c000_0000000000000000'
if grep -Fqx "$debug_assert" "$raw_nbf" || grep -Fqx "$debug_deassert" "$raw_nbf"; then
    echo "generated OpenSBI NBF unexpectedly contains a debug-entry preamble" >&2
    exit 1
fi

selector='02_0000000000308000_0000000000000001'
if [ "$(grep -Fxc "$selector" "$raw_nbf")" -ne 1 ]; then
    echo "NBF does not contain exactly one default mtime selector" >&2
    exit 1
fi
sed -i "s/^$selector$/02_0000000000308000_0000000000000002/" "$raw_nbf"
mkdir -p "$(dirname -- "$output")"
cp "$raw_nbf" "$output"

echo "NBF=$output NBF_DEBUG=0"
echo "PAYLOAD_ENTRY=$payload_entry FW_PAYLOAD_OFFSET=$payload_offset_hex FW_OPTIONS=$opensbi_fw_options"
sha256sum "$elfloader" "$firmware" "$output"
