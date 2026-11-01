#!/bin/sh
# Configure the pinned protected-RPC case with the software backend on QEMU.

set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 /path/to/sel4test-checkout /path/to/new-build-dir" >&2
    exit 2
fi

checkout=$(realpath "$1")
build_dir=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
validation_patch="$project_root/sel4/patches/sel4test-blackparrot-rpc-validation.patch"
test_dir="$checkout/projects/sel4test/apps/sel4test-tests/src/tests"

command -v cmake >/dev/null || { echo "cmake is not on PATH" >&2; exit 1; }
command -v ninja >/dev/null || { echo "ninja is not on PATH" >&2; exit 1; }
command -v qemu-system-riscv64 >/dev/null \
    || { echo "qemu-system-riscv64 is not on PATH" >&2; exit 1; }

"$script_dir/materialize_sel4test_ipc_baseline.sh" "$checkout"

if git -C "$checkout/projects/sel4test" apply --reverse --check \
    "$validation_patch" 2>/dev/null; then
    :
elif git -C "$checkout/projects/sel4test" apply --check "$validation_patch"; then
    git -C "$checkout/projects/sel4test" apply "$validation_patch"
else
    echo "cannot apply sel4test protected-RPC validation patch" >&2
    exit 1
fi

if [ ! -L "$test_dir/protected_rpc_hardware_stub.c" ] \
    || [ -e "$test_dir/protected_rpc_hardware_blackparrot.c" ] \
    || [ -e "$test_dir/protected_rpc_blackparrot_sel4.c" ]; then
    echo "QEMU protected-RPC backend materialization is not exclusive" >&2
    exit 1
fi

mkdir -p "$build_dir"
build_dir=$(realpath "$build_dir")
(
    cd "$build_dir"
    "$checkout/init-build.sh" \
        -DPLATFORM=qemu-riscv-virt \
        -DKernelSel4Arch=riscv64 \
        -DSIMULATION=ON \
        -DRELEASE=ON \
        -DKernelFastpath=ON \
        -DSel4testRpcOnly=ON \
        -DSel4testRpcPrinting=ON \
        -DLibSel4MuslcSysMorecoreBytes=65536 \
        -DLibSel4TestPrinterRegex='^SEL4IPCRPC0002$'
)

echo "configured QEMU protected-RPC build in $build_dir"
