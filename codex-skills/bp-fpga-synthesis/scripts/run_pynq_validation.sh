#!/usr/bin/env bash
set -euo pipefail

[[ $# -ge 1 && $# -le 2 ]] || {
  echo "usage: $0 <ssh-host> [remote-zynq-directory]" >&2
  exit 2
}

ssh_host=$1
remote_dir=${2:-'~/zynq-parrot/cosim/black-parrot-example/zynq'}
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
serial_runner="$script_dir/run_pynq_serial.sh"
nbf_dir="$repo_dir/riscv/bp-tests"
log_dir=${PYNQ_VALIDATION_LOG_DIR:-"$repo_dir/logs/pynq-validation"}
timeout_seconds=${PYNQ_VALIDATION_TIMEOUT_SECONDS:-180}
runtime_limit_ms=$((timeout_seconds * 1000))
mkdir -p "$log_dir"

if [[ -n "${PYNQ_VALIDATION_TESTS:-}" ]]; then
  read -r -a tests <<<"$PYNQ_VALIDATION_TESTS"
else
  tests=(
    mt_fpga_current_toolchain_smoke
    mt_amo_swap_return_test
    mt_ctxtsw_fpga_stage_test
    mt_global_cycle_csr_test
    mt_ctxtsw_nonresident_ring_test
    mt_ctxtsw_nonresident_fp_target_test
    mt_ctxtsw_nonresident_fp_ring_test
    mt_ctxtsw_gpr_ring_stress
    mt_ctxtsw_late_wb_hazard_test
    mt_ctxtsw_nonresident_overhead_benchmark
    mt_ctxtsw_nonresident_fp_overhead_benchmark
    mt_ctxtsw_nonresident_cold_icache_benchmark
  )
fi

remote() {
  ssh -o BatchMode=yes "$ssh_host" "cd $remote_dir && $1"
}

require_idle_runner() {
  # The board has one PL/DRAM control path.  A previously orphaned manual
  # control-program run invalidates every later result, even if this harness
  # itself is otherwise sequential.
  if remote "pgrep -x control-program >/dev/null || pgrep -f '[s]cript .*control-program' >/dev/null"; then
    echo "FAIL: board already has an active control-program runner" >&2
    remote "pgrep -af 'control-program' || true" >&2
    exit 1
  fi
}

if remote "grep -q -- '-DDRAM_TEST' build.log"; then
  echo "FAIL: board control-program build.log contains -DDRAM_TEST" >&2
  exit 1
fi

remote "sha256sum blackparrot_bd_1.bit 2>/dev/null || sha256sum black_parrot_bd_1.bit"

for test_name in "${tests[@]}"; do
  require_idle_runner
  image="${test_name}_fpga.nbf"
  local_image="$nbf_dir/$image"
  log="$log_dir/${test_name}.log"
  [[ -s "$local_image" ]] || { echo "FAIL: missing $local_image" >&2; exit 1; }
  local_sha=$(sha256sum "$local_image" | awk '{print $1}')
  remote_sha=$(remote "sha256sum $image" | awk '{print $1}')
  [[ "$local_sha" == "$remote_sha" ]] || {
    echo "FAIL: NBF SHA mismatch for $image" >&2
    exit 1
  }
  echo "RUN  $test_name sha256=$local_sha"
  set +e
  # The serial wrapper owns the atomic board lock and waits for the exact
  # privileged worker.  Passing the limit through control-program preserves
  # its clean shutdown semantics without leaving an orphan behind.
  PYNQ_CONTROL_PROGRAM_TIMEOUT_MS="$runtime_limit_ms" \
    "$serial_runner" "$ssh_host" "$image" "$remote_dir" >"$log" 2>&1
  run_rc=$?
  set -e
  if grep -Eq 'CORE FAIL|BSG-FAIL' "$log" || ! grep -Eq 'CORE\[0\] PASS|CORE PASS' "$log"; then
    echo "FAIL $test_name host_rc=$run_rc (see $log)" >&2
    exit 1
  fi
  echo "PASS $test_name host_rc=$run_rc"
done

echo "PYNQ VALIDATION PASS"
