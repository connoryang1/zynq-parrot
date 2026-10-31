#!/bin/sh
# Compile and run the host-side protected-RPC interface contract test.

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/tests/protected_rpc_interface_test.c" \
    -o "$build_dir/protected_rpc_interface_test"
"$build_dir/protected_rpc_interface_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc.c" \
    "$project_root/sel4/tests/protected_rpc_dispatch_test.c" \
    -o "$build_dir/protected_rpc_dispatch_test"
"$build_dir/protected_rpc_dispatch_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/tests/blackparrot_rpc_abi_test.c" \
    -o "$build_dir/blackparrot_rpc_abi_test"
"$build_dir/blackparrot_rpc_abi_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -DPROTECTED_RPC_BLACKPARROT_TEST_HOOK \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc.c" \
    "$project_root/sel4/src/protected_rpc_hardware_blackparrot.c" \
    "$project_root/sel4/tests/protected_rpc_blackparrot_backend_test.c" \
    -o "$build_dir/protected_rpc_blackparrot_backend_test"
"$build_dir/protected_rpc_blackparrot_backend_test"
