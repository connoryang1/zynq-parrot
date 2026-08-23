#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(git rev-parse --show-toplevel)
sim_dir="$repo_dir/cosim/black-parrot-example/verilator"
nbf_dir="$repo_dir/riscv/bp-tests"
log_dir=${FPGA_VALIDATION_LOG_DIR:-"$repo_dir/logs/fpga-validation-exact"}
mkdir -p "$log_dir"

if (( $# )); then
  tests=("$@")
else
  tests=(
    mt_fpga_current_toolchain_smoke
    mt_ctxtsw_fpga_stage_test
    mt_global_cycle_csr_test
    mt_ctxtsw_nonresident_ring_test
    mt_ctxtsw_gpr_ring_stress
    mt_ctxtsw_late_wb_hazard_test
    mt_ctxtsw_nonresident_cold_icache_benchmark
  )
fi

for test_name in "${tests[@]}"; do
  nbf="$nbf_dir/${test_name}_fpga.nbf"
  log="$log_dir/${test_name}.log"
  [[ -s "$nbf" ]] || { echo "FAIL: missing $nbf" >&2; exit 1; }
  echo "RUN  $test_name"
  set +e
  timeout "${FPGA_EXACT_TIMEOUT_SECONDS:-180}" \
    make -C "$sim_dir" run \
      CFG=e_bp_unicore_zynqparrot_cfg TRACE=1 NBF_FILE="$nbf" \
      </dev/null >"$log" 2>&1
  run_rc=$?
  set -e
  if grep -Eq 'CORE FAIL|BSG-FAIL' "$log" || ! grep -Eq 'CORE PASS|CORE\[0\] PASS' "$log"; then
    echo "FAIL $test_name host_rc=$run_rc (see $log)" >&2
    exit 1
  fi
  if [[ "$test_name" == mt_ctxtsw_nonresident_cold_icache_benchmark ]]; then
    cp "$sim_dir/dump.fst" "$log_dir/${test_name}.fst"
  fi
  echo "PASS $test_name host_rc=$run_rc"
done

echo "FPGA EXACT VALIDATION PASS"
