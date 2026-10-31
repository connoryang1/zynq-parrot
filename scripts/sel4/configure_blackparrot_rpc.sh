#!/bin/sh
# Configure the pinned sel4test RPC case for the BlackParrot RV64 platform.

set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 /path/to/sel4test-checkout /path/to/build-dir" >&2
    exit 2
fi

checkout=$(realpath "$1")
build_dir=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
validation_patch="$project_root/sel4/patches/sel4test-blackparrot-rpc-validation.patch"
kernel_patch="$project_root/sel4/patches/sel4-blackparrot-rpc-kernel.patch"

command -v cmake >/dev/null || { echo "cmake is not on PATH" >&2; exit 1; }
command -v ninja >/dev/null || { echo "ninja is not on PATH" >&2; exit 1; }

"$script_dir/materialize_sel4test_ipc_baseline.sh" "$checkout"
"$script_dir/materialize_blackparrot_platform.sh" "$checkout"

apply_patch_once()
{
    repository=$1
    patch=$2
    description=$3
    if git -C "$repository" apply --reverse --check "$patch" 2>/dev/null; then
        return
    fi
    if git -C "$repository" apply --check "$patch"; then
        git -C "$repository" apply "$patch"
        return
    fi
    echo "cannot apply $description" >&2
    exit 1
}

apply_patch_once "$checkout/kernel" "$kernel_patch" \
    "BlackParrot protected-RPC kernel patch"
apply_patch_once "$checkout/projects/sel4test" "$validation_patch" \
    "BlackParrot RPC validation patch"

mkdir -p "$build_dir"
build_dir=$(realpath "$build_dir")
(
    cd "$build_dir"
    "$checkout/init-build.sh" \
        -DPLATFORM=blackparrot \
        -DKernelSel4Arch=riscv64 \
        -DSIMULATION=ON \
        -DRELEASE=ON \
        -DKernelFastpath=ON \
        -DSel4testRpcOnly=ON \
        -DSel4testRpcPrinting=ON \
        -DLibSel4MuslcSysMorecoreBytes=65536 \
        -DLibSel4TestPrinterRegex='^SEL4IPCRPC0002$'
)

echo "configured BlackParrot protected-RPC build in $build_dir"
