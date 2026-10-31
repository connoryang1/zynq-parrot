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

command -v cmake >/dev/null || { echo "cmake is not on PATH" >&2; exit 1; }
command -v ninja >/dev/null || { echo "ninja is not on PATH" >&2; exit 1; }

"$script_dir/materialize_sel4test_ipc_baseline.sh" "$checkout"
"$script_dir/materialize_blackparrot_platform.sh" "$checkout"

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
        -DLibSel4TestPrinterRegex='^SEL4IPCRPC0002$'
)

echo "configured BlackParrot protected-RPC build in $build_dir"
