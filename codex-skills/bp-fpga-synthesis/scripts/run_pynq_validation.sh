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

if remote "grep -q -- '-DDRAM_TEST' build.log"; then
  echo "FAIL: board control-program build.log contains -DDRAM_TEST" >&2
  exit 1
fi

remote "sha256sum blackparrot_bd_1.bit 2>/dev/null || sha256sum black_parrot_bd_1.bit"

for test_name in "${tests[@]}"; do
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
  # The control program runs as root, so wrapping sudo with a user-owned
  # timeout cannot reliably signal the actual worker.  Pass the bound to the
  # control program itself; it shuts down the target and exits with 124.
  remote "sudo -n \"\$(pwd)/control-program\" $image $runtime_limit_ms" >"$log" 2>&1
  run_rc=$?
  set -e
  if grep -Eq 'CORE FAIL|BSG-FAIL' "$log" || ! grep -Eq 'CORE\[0\] PASS|CORE PASS' "$log"; then
    echo "FAIL $test_name host_rc=$run_rc (see $log)" >&2
    exit 1
  fi
  echo "PASS $test_name host_rc=$run_rc"
done

echo "PYNQ VALIDATION PASS"
