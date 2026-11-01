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

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"$project_root/sel4/tests/mock_sel4" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc_blackparrot_sel4.c" \
    "$project_root/sel4/tests/protected_rpc_blackparrot_binding_test.c" \
    -o "$build_dir/protected_rpc_blackparrot_binding_test"
"$build_dir/protected_rpc_blackparrot_binding_test"

# Physical UART capture is nested under script(1) and arrives as CRCRLF.  Keep
# the strict evidence checker compatible with that transport without relaxing
# its exact row/count requirements.
uart_log="$build_dir/physical-uart.log"
printf '%s\r\r\n' \
    'SEL4_RPC_ADAPTER path=hardware calls=256 total_cycles=95978 cycles_per_call=374' \
    'SEL4_RPC_ADAPTER path=software-fallback calls=8 total_cycles=25493 cycles_per_call=3186' \
    'Test SEL4IPCRPC0002 passed' \
    'halting...INFO:    CORE PASS' \
    'INFO:    BSG PASS' > "$uart_log"
"$script_dir/check_blackparrot_rpc_result.sh" --physical "$uart_log"
