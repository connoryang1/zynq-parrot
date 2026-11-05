#!/bin/sh
# Configure the pinned upstream sel4bench checkout for RV64 IPC-only QEMU runs.

set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 /path/to/sel4bench-checkout /path/to/build-dir" >&2
    exit 2
fi

checkout=$(realpath "$1")
build_dir=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
patch_file="$project_root/sel4/patches/sel4bench-riscv-cycle-dependency.patch"

if [ ! -x "$checkout/init-build.sh" ] || [ ! -d "$checkout/.repo/manifests" ]; then
    echo "not a sel4bench manifest checkout: $checkout" >&2
    exit 1
fi

manifest_revision=$(git -C "$checkout/.repo/manifests" rev-parse HEAD)
if [ "$manifest_revision" != "c7db39cd58202dc207d292c54f68d6dcafe0c5bc" ]; then
    echo "unexpected sel4bench manifest revision: $manifest_revision" >&2
    exit 1
fi

sel4bench_project="$checkout/projects/sel4bench"
if git -C "$sel4bench_project" apply --check "$patch_file" 2>/dev/null; then
    git -C "$sel4bench_project" apply "$patch_file"
elif ! git -C "$sel4bench_project" apply --reverse --check "$patch_file" 2>/dev/null; then
    echo "sel4bench dependency workaround does not apply cleanly" >&2
    exit 1
fi

mkdir -p "$build_dir"
build_dir=$(realpath "$build_dir")
(
    cd "$build_dir"
    "$checkout/init-build.sh" \
        -DPLATFORM=qemu-riscv-virt \
        -DKernelSel4Arch=riscv64 \
        -DIPC=ON \
        -DIRQUSER=OFF \
        -DSCHED=OFF \
        -DSIGNAL=OFF \
        -DMAPPING=OFF \
        -DSYNC=OFF \
        -DFAULT=OFF \
        -DHARDWARE=OFF \
        -DSMP=OFF \
        -DVCPU=OFF \
        -DFASTPATH=ON \
        -DRELEASE=ON \
        -DAllowUnstableOverhead=ON \
        -DOutputRawResults=OFF
)
