#!/bin/sh
# Link the versioned IPC baseline into a pinned external sel4test checkout.

set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 /path/to/sel4test-checkout" >&2
    exit 2
fi

checkout=$(realpath "$1")
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
source_file="$project_root/sel4/sel4test/sel4_ipc_baseline.c"
test_dir="$checkout/projects/sel4test/apps/sel4test-tests/src/tests"

if [ ! -d "$test_dir" ]; then
    echo "not a sel4test manifest checkout: $checkout" >&2
    exit 1
fi

manifest_revision=$(git -C "$checkout/.repo/manifests" rev-parse HEAD)
if [ "$manifest_revision" != "ae4780bcdc221959949a0ec0aeb559337ea503d0" ]; then
    echo "unexpected sel4test manifest revision: $manifest_revision" >&2
    exit 1
fi

ln -sfn "$source_file" "$test_dir/sel4_ipc_baseline.c"
echo "linked $test_dir/sel4_ipc_baseline.c"
