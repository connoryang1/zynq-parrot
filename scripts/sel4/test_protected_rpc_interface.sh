#!/bin/sh
# Compile and run the host-side protected-RPC interface contract test.

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(realpath "$script_dir/../..")
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
internal_include="-I$project_root/sel4/internal"

# Applications receive exactly one header; trusted runtime and transport
# details must not drift back onto the public include path.
public_headers=$(find "$project_root/sel4/include" -maxdepth 1 -type f \
    -printf '%f\n' | LC_ALL=C sort)
if [ "$public_headers" != "protected_rpc.h" ]; then
    echo "unexpected protected-RPC public headers: $public_headers" >&2
    exit 1
fi

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/tests/protected_rpc_interface_test.c" \
    -o "$build_dir/protected_rpc_interface_test"
"$build_dir/protected_rpc_interface_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    "$internal_include" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc.c" \
    "$project_root/sel4/tests/protected_rpc_dispatch_test.c" \
    -o "$build_dir/protected_rpc_dispatch_test"
"$build_dir/protected_rpc_dispatch_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    "$internal_include" \
    -I"$project_root/sel4/tests/mock_sel4" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc_sel4.c" \
    "$project_root/sel4/tests/protected_rpc_server_config_test.c" \
    -o "$build_dir/protected_rpc_server_config_test"
"$build_dir/protected_rpc_server_config_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    "$internal_include" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/tests/blackparrot_rpc_abi_test.c" \
    -o "$build_dir/blackparrot_rpc_abi_test"
"$build_dir/blackparrot_rpc_abi_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -DPROTECTED_RPC_BLACKPARROT_TEST_HOOK \
    "$internal_include" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc.c" \
    "$project_root/sel4/src/protected_rpc_hardware_blackparrot.c" \
    "$project_root/sel4/tests/protected_rpc_blackparrot_backend_test.c" \
    -o "$build_dir/protected_rpc_blackparrot_backend_test"
"$build_dir/protected_rpc_blackparrot_backend_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    "$internal_include" \
    -I"$project_root/sel4/tests/mock_sel4" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc_blackparrot_sel4.c" \
    "$project_root/sel4/tests/protected_rpc_blackparrot_binding_test.c" \
    -o "$build_dir/protected_rpc_blackparrot_binding_test"
"$build_dir/protected_rpc_blackparrot_binding_test"

${CC:-cc} -std=c11 -Wall -Wextra -Werror -pedantic \
    -DPROTECTED_RPC_BLACKPARROT_SERVER_TEST_HOOK \
    "$internal_include" \
    -I"$project_root/sel4/tests/mock_sel4" \
    -I"$project_root/sel4/include" \
    "$project_root/sel4/src/protected_rpc_sel4.c" \
    "$project_root/sel4/src/protected_rpc_blackparrot_server.c" \
    "$project_root/sel4/tests/protected_rpc_blackparrot_server_test.c" \
    -o "$build_dir/protected_rpc_blackparrot_server_test"
"$build_dir/protected_rpc_blackparrot_server_test"

# The application server selects a handler and publishes runtime state; only
# the trusted transport runtime may touch installed registers or preturn.
if grep -Eq '0x809|mv %0, (s1|tp)' \
    "$project_root/sel4/sel4test/sel4_rpc_server.c"; then
    echo "application server contains BlackParrot transport instructions" >&2
    exit 1
fi

# The shared service source must see seL4's generated platform macro even when
# compiled into the separate stripped server executable. The package gate then
# checks the resulting instructions rather than trusting this source guard.
grep -Fq '#include <sel4/config.h>' \
    "$project_root/sel4/sel4test/sel4_rpc_search_service.c"
grep -Fq 'RPC server has wrong privileged instructions' \
    "$project_root/scripts/sel4/package_blackparrot_rpc_nbf.sh"

# Physical UART capture is nested under script(1) and arrives as CRCRLF.  Keep
# the strict evidence checker compatible with that transport without relaxing
# its exact row/count requirements.
uart_log="$build_dir/physical-uart.log"
printf '%s\r\r\n' \
    'SEL4_RPC_REGION_GUARD physical-mismatch=denied write-escalation=denied runtime-state=denied' \
    'SEL4_RPC_LIFECYCLE map-revoke=verified stale-token=verified rebind=verified' \
    'SEL4_RPC_CALLER_BADGE value=24090 software=verified hardware=verified' \
    'SEL4_RPC_WORKLOAD name=libc-bounded-search bytes=1024' \
    'SEL4_RPC_ADAPTER path=in-process calls=256 total_cycles=760832 cycles_per_call=2972' \
    'SEL4_RPC_ADAPTER path=hardware calls=256 total_cycles=856576 cycles_per_call=3346' \
    'SEL4_RPC_ADAPTER path=software calls=256 total_cycles=1664000 cycles_per_call=6500' \
    'SEL4_RPC_ADAPTER path=notification calls=256 total_cycles=1536000 cycles_per_call=6000' \
    'SEL4_RPC_ADAPTER path=software-fallback calls=8 total_cycles=52880 cycles_per_call=6610' \
    'SEL4_RPC_DISTRIBUTION path=in-process samples=64 min=2960 median=2970 p95=2990 max=3010' \
    'SEL4_RPC_DISTRIBUTION path=hardware samples=64 min=3330 median=3340 p95=3370 max=3400' \
    'SEL4_RPC_DISTRIBUTION path=software samples=64 min=6450 median=6500 p95=6600 max=6700' \
    'SEL4_RPC_DISTRIBUTION path=notification samples=64 min=5900 median=6000 p95=6100 max=6200' \
    'SEL4_RPC_TIMEBASE counter=blackparrot-global-cycle-csr-0xcc0 scope=core-wide' \
    'SEL4_RPC_COMPONENTS path=in-process samples=64 pre_median=20 service_median=2900 post_median=50' \
    'SEL4_RPC_COMPONENTS path=hardware samples=64 pre_median=180 service_median=2900 post_median=260' \
    'SEL4_RPC_COMPONENTS path=software samples=64 pre_median=1500 service_median=2900 post_median=2100' \
    'SEL4_RPC_COMPONENTS path=notification samples=64 pre_median=3500 service_median=2900 post_median=3600' \
    'SEL4_RPC_NOTIFICATION_BASELINE mailbox=shared-rw data-region=server-ro request-signal=notification reply-signal=notification' \
    'SEL4_RPC_CACHE_STATE kind=l1d-cold lower-cache=warm method=blackparrot-flush-all samples=64' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/in-process samples=64 min=4000 median=4100 p95=4300 max=4500' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/hardware samples=64 min=4400 median=4500 p95=4800 max=5000' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/software samples=64 min=7000 median=7200 p95=7600 max=8000' \
    'SEL4_RPC_DISTRIBUTION path=l1d-cold/notification samples=64 min=6500 median=6700 p95=7100 max=7500' \
    'SEL4_RPC_CACHE_STATE kind=data-hierarchy-cold l1d=cold l2=cold l1i=warm dram-row=uncontrolled method=4x-l2-evict samples=64' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/in-process samples=64 min=5000 median=5200 p95=5700 max=6100' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/hardware samples=64 min=5700 median=5900 p95=6400 max=6900' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/software samples=64 min=9000 median=9400 p95=10100 max=11000' \
    'SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/notification samples=64 min=8200 median=8600 p95=9300 max=10000' \
    'Test SEL4IPCRPC0002 passed' \
    'halting...INFO:    CORE PASS' \
    'INFO:    BSG PASS' > "$uart_log"
"$script_dir/check_blackparrot_rpc_result.sh" --physical "$uart_log"
"$script_dir/check_blackparrot_rpc_result.sh" --physical --shared-buffer "$uart_log"
"$script_dir/check_blackparrot_rpc_result.sh" --physical --shared-buffer \
    --components --lifecycle --caller-badge 24090 "$uart_log"

lifecycle_missing_log="$build_dir/physical-uart-lifecycle-missing.log"
grep -v '^SEL4_RPC_LIFECYCLE ' "$uart_log" > "$lifecycle_missing_log"
if "$script_dir/check_blackparrot_rpc_result.sh" --physical --shared-buffer \
    --components --lifecycle --caller-badge 24090 \
    "$lifecycle_missing_log" >/dev/null 2>&1; then
    echo "lifecycle checker accepted a missing marker" >&2
    exit 1
fi

badge_missing_log="$build_dir/physical-uart-badge-missing.log"
grep -v '^SEL4_RPC_CALLER_BADGE ' "$uart_log" > "$badge_missing_log"
if "$script_dir/check_blackparrot_rpc_result.sh" --physical --shared-buffer \
    --components --caller-badge 24090 "$badge_missing_log" >/dev/null 2>&1; then
    echo "caller-badge checker accepted a missing marker" >&2
    exit 1
fi
if "$script_dir/check_blackparrot_rpc_result.sh" --physical --shared-buffer \
    --components --caller-badge 24091 "$uart_log" >/dev/null 2>&1; then
    echo "caller-badge checker accepted the wrong badge" >&2
    exit 1
fi
