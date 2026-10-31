#!/bin/sh
# Link the versioned BlackParrot platform glue into the pinned sel4test tree.

set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 /path/to/sel4test-checkout" >&2
    exit 2
fi

checkout=$(realpath "$1")
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
platform="$project_root/sel4/platform/blackparrot"
kernel="$checkout/kernel"
utils="$checkout/projects/util_libs"

if [ ! -d "$checkout/.repo/manifests" ] || [ ! -d "$kernel/libsel4" ]; then
    echo "not a sel4test manifest checkout: $checkout" >&2
    exit 1
fi

manifest_revision=$(git -C "$checkout/.repo/manifests" rev-parse HEAD)
kernel_revision=$(git -C "$kernel" rev-parse HEAD)
utils_revision=$(git -C "$utils" rev-parse HEAD)
if [ "$manifest_revision" != "ae4780bcdc221959949a0ec0aeb559337ea503d0" ]; then
    echo "unexpected sel4test manifest revision: $manifest_revision" >&2
    exit 1
fi
if [ "$kernel_revision" != "15ec7bf82864e0505dc682051c0d688a946f5ece" ]; then
    echo "unexpected seL4 kernel revision: $kernel_revision" >&2
    exit 1
fi
if [ "$utils_revision" != "ef49a397b7044fc38b609a99a8c6265a97913b8e" ]; then
    echo "unexpected util_libs revision: $utils_revision" >&2
    exit 1
fi

link_file()
{
    source=$1
    destination=$2
    mkdir -p "$(dirname -- "$destination")"
    ln -sfn "$source" "$destination"
}

link_file "$platform/kernel/config.cmake" \
    "$kernel/src/plat/blackparrot/config.cmake"
link_file "$platform/kernel/blackparrot.dts" \
    "$kernel/tools/dts/blackparrot.dts"
link_file "$platform/kernel/overlay-blackparrot.dts" \
    "$kernel/src/plat/blackparrot/overlay-blackparrot.dts"
link_file "$platform/kernel/constants.h" \
    "$kernel/libsel4/sel4_plat_include/blackparrot/sel4/plat/api/constants.h"
link_file "$platform/libplatsupport/serial.h" \
    "$utils/libplatsupport/plat_include/blackparrot/platsupport/plat/serial.h"
link_file "$platform/libplatsupport/timer.h" \
    "$utils/libplatsupport/plat_include/blackparrot/platsupport/plat/timer.h"
link_file "$platform/libplatsupport/clock.h" \
    "$utils/libplatsupport/plat_include/blackparrot/platsupport/plat/clock.h"
link_file "$platform/libplatsupport/chardev.c" \
    "$utils/libplatsupport/src/plat/blackparrot/chardev.c"

echo "linked BlackParrot seL4 platform glue into $checkout"
