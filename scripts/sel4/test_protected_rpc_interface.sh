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
    'SEL4_RPC_REGION_GUARD physical-mismatch=denied write-escalation=denied runtime-state=denied' \
    'SEL4_RPC_WORKLOAD name=libc-bounded-search bytes=1024' \
    'SEL4_RPC_ADAPTER path=in-process calls=256 total_cycles=760832 cycles_per_call=2972' \
    'SEL4_RPC_ADAPTER path=hardware calls=256 total_cycles=856576 cycles_per_call=3346' \
    'SEL4_RPC_ADAPTER path=software calls=256 total_cycles=1664000 cycles_per_call=6500' \
    'SEL4_RPC_ADAPTER path=software-fallback calls=8 total_cycles=52880 cycles_per_call=6610' \
    'SEL4_RPC_DISTRIBUTION path=in-process samples=64 min=2960 median=2970 p95=2990 max=3010' \
    'SEL4_RPC_DISTRIBUTION path=hardware samples=64 min=3330 median=3340 p95=3370 max=3400' \
    'SEL4_RPC_DISTRIBUTION path=software samples=64 min=6450 median=6500 p95=6600 max=6700' \
    'SEL4_RPC_CACHE_STATE kind=l1d-cold lower-cache=warm method=blackparrot-flush-all samples=64' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/in-process samples=64 min=4000 median=4100 p95=4300 max=4500' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/hardware samples=64 min=4400 median=4500 p95=4800 max=5000' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/software samples=64 min=7000 median=7200 p95=7600 max=8000' \
    'SEL4_RPC_CACHE_STATE kind=data-hierarchy-cold l1d=cold l2=cold l1i=warm dram-row=uncontrolled method=4x-l2-evict samples=64' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/in-process samples=64 min=5000 median=5200 p95=5700 max=6100' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/hardware samples=64 min=5700 median=5900 p95=6400 max=6900' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/software samples=64 min=9000 median=9400 p95=10100 max=11000' \
    'Test SEL4IPCRPC0002 passed' \
    'halting...INFO:    CORE PASS' \
    'INFO:    BSG PASS' > "$uart_log"
"$script_dir/check_blackparrot_rpc_result.sh" --physical "$uart_log"
"$script_dir/check_blackparrot_rpc_result.sh" --physical --shared-buffer "$uart_log"
