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
adapter_test="$project_root/sel4/sel4test/sel4_rpc_adapter_test.c"
test_dir="$checkout/projects/sel4test/apps/sel4test-tests/src/tests"

# A checkout may be reused after a BlackParrot build; keep backend selection
# exclusive so the normal source glob cannot link both implementations.
rm -f "$test_dir/protected_rpc_hardware_blackparrot.c" \
    "$test_dir/protected_rpc_blackparrot_sel4.c" \
    "$test_dir/protected_rpc_blackparrot.h" \
    "$test_dir/blackparrot_rpc_abi.h"

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
ln -sfn "$adapter_test" "$test_dir/sel4_rpc_adapter_test.c"
ln -sfn "$project_root/sel4/src/protected_rpc.c" "$test_dir/protected_rpc.c"
ln -sfn "$project_root/sel4/src/protected_rpc_sel4.c" "$test_dir/protected_rpc_sel4.c"
ln -sfn "$project_root/sel4/src/protected_rpc_hardware_stub.c" \
    "$test_dir/protected_rpc_hardware_stub.c"
ln -sfn "$project_root/sel4/include/protected_rpc.h" "$test_dir/protected_rpc.h"
ln -sfn "$project_root/sel4/include/protected_rpc_backend.h" \
    "$test_dir/protected_rpc_backend.h"
echo "linked protected-RPC tests and sources into $test_dir"
