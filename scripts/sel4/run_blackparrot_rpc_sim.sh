#!/usr/bin/env bash
# Run the reduced seL4 image and stop as soon as its exact RPC gate is visible.

set -euo pipefail

if (($# != 2)); then
    echo "usage: $0 IMAGE.nbf OUTPUT.log" >&2
    exit 2
fi

image=$(realpath "$1")
output=$2
project_root=$(realpath "$(dirname -- "$0")/../..")
result_checker=$project_root/scripts/sel4/check_blackparrot_rpc_result.sh
model=${BLACKPARROT_SIM:-$project_root/cosim/black-parrot-minimal-example/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench}
timeout_s=${BSG_TRACE_TIMEOUT_S:-14400}
marker='Test SEL4IPCRPC0002 passed'

test -f "$image" || { echo "missing NBF: $image" >&2; exit 1; }
test -x "$model" || { echo "missing simulator: $model" >&2; exit 1; }
model=$(realpath "$model")
mkdir -p "$(dirname -- "$output")"

if pgrep -f '[/]Vbsg_nonsynth_zynq_testbench([[:space:]]|$)' >/dev/null; then
    echo "a BlackParrot simulator is already running; serialize simulator use" >&2
    exit 1
fi

: > "$output"
model_sha=$(sha256sum "$model" | awk '{print $1}')
image_sha=$(sha256sum "$image" | awk '{print $1}')
printf 'SEL4_RPC_SIM model=%s model_sha256=%s image=%s image_sha256=%s timeout_s=%s\n' \
    "$model" "$model_sha" "$image" "$image_sha" "$timeout_s" | tee -a "$output"

run_env=(
    BSG_SKIP_DEBUG_ENTRY=1
    BSG_TRACE_TIMEOUT_S="$timeout_s"
    LD_LIBRARY_PATH="${ZP_INSTALL_DIR:-/home/coyang/zynq-parrot/install}/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
)
if [[ -n ${BSG_INSPECT_DRAM_ADDR:-} ]]; then
    run_env+=(BSG_INSPECT_DRAM_ADDR="$BSG_INSPECT_DRAM_ADDR")
fi

(
    env "${run_env[@]}" stdbuf -oL -eL "$model" "$image" 2>&1 \
        | tee -a "$output"
) &
runner=$!

cleanup()
{
    local children
    children=$(pgrep -P "$runner" 2>/dev/null || true)
    if [[ -n "$children" ]]; then
        kill -INT $children 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

while kill -0 "$runner" 2>/dev/null; do
    if grep -Fq "$marker" "$output"; then
        echo "exact RPC marker observed; stopping simulator"
        cleanup
        break
    fi
    sleep 5
done

runner_status=0
wait "$runner" || runner_status=$?
trap - INT TERM EXIT

if grep -Fq "$marker" "$output"; then
    "$result_checker" "$output"
    exit 0
fi
echo "simulator ended without exact RPC marker (status $runner_status)" >&2
exit 1
