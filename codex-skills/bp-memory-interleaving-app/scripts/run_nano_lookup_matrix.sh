#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
artifact_root=${1:?usage: run_nano_lookup_matrix.sh ARTIFACT_DIR}
sim_dir="$repo_root/cosim/black-parrot-minimal-example/verilator"
elf="$repo_root/riscv/bp-tests/mt_nano_lookup_benchmark.riscv"
toolchain=${ZP_INSTALL_DIR:-/home/coyang/zynq-parrot/install}
modes=${NANO_MODES:-"0 1 2 3 4"}
sim_defines=${NANO_SIM_DEFINES:-"BP_AXI_MEM_PIPELINED BP_AXI_MEM_READ_LATENCY=200 BP_AXI_MEM_READ_QUEUE_DEPTH=10"}

mkdir -p "$artifact_root"
artifact_root=$(realpath "$artifact_root")
lock_file=$(git -C "$repo_root" rev-parse --git-path nano-lookup-matrix.lock)
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "another Nano lookup matrix owns $sim_dir" >&2
  exit 2
fi

if [[ -n $(git -C "$repo_root" status --porcelain --untracked-files=normal) ]]; then
  echo "refusing an asynchronous matrix from a dirty worktree" >&2
  exit 2
fi
if [[ ! -f "$repo_root/riscv/bootrom/bootrom.none.riscv" ]]; then
  echo "missing local riscv/bootrom/bootrom.none.riscv prerequisite" >&2
  exit 2
fi

{
  echo "top_commit=$(git -C "$repo_root" rev-parse HEAD)"
  echo "rtl_commit=$(git -C "$repo_root/import/black-parrot" rev-parse HEAD)"
  echo "toolchain=$toolchain"
  echo "modes=$modes"
  echo "sim_defines=$sim_defines"
  echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$artifact_root/RUN_METADATA"

if [[ ${NANO_REBUILD_SIM:-0} == 1 ]]; then
  make -C "$sim_dir" clean
fi

for mode in $modes; do
  mode_dir="$artifact_root/mode-$mode"
  mkdir -p "$mode_dir"
  set +e
  make -C "$repo_root/testing" run-mt_nano_lookup_benchmark \
    NUM_THREADS=2 NUM_CONTEXTS=10 PREFETCH_ELS=10 NANO_MODE="$mode" \
    TRACE=1 VERILATOR_BUILD_JOBS="${VERILATOR_BUILD_JOBS:-8}" \
    ZP_INSTALL_DIR="$toolchain" SIM_DEFINES="$sim_defines" \
    > "$mode_dir/driver.log" 2>&1
  run_rc=$?
  set -e

  for path in \
    "$sim_dir/run.log" "$sim_dir/dump.fst" "$sim_dir/prog.nbf" \
    "$elf" "$repo_root/testing/logs/verilator_build.log"; do
    [[ -f "$path" ]] && cp -p "$path" "$mode_dir/"
  done
  echo "$run_rc" > "$mode_dir/driver.exit-code"
  (cd "$mode_dir" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 |
    sort -z | xargs -0 sha256sum > SHA256SUMS)
  if [[ $run_rc -ne 0 ]]; then
    echo "mode $mode failed; see $mode_dir/driver.log" >&2
    exit "$run_rc"
  fi

  measured_addr=$($toolchain/bin/riscv64-unknown-elf-nm -n "$elf" |
    awk '$3 == "nano_measured_indexes" {print "0x" $1; exit}')
  case "$mode" in
    0) consume_symbol=nano_serial_consume_load ;;
    1|2) consume_symbol=nano_worker_consume_load ;;
    3) consume_symbol=nano_batch_consume_load ;;
    4) consume_symbol= ;;
    *) echo "unsupported mode $mode" >&2; exit 2 ;;
  esac
  if [[ -n "$consume_symbol" ]]; then
    consume_pc=$($toolchain/bin/riscv64-unknown-elf-nm -n "$elf" |
      awk -v symbol="$consume_symbol" '$3 == symbol {print "0x" $1; exit}')
    extra=()
    [[ "$mode" == 0 || "$mode" == 1 ]] && extra+=(--allow-no-prefetch)
    set +e
    fst2vcd "$mode_dir/dump.fst" |
      python3 -B "$repo_root/tools/prefetch_overlap_vcd.py" \
        --uce-prefix dcache_uce --axi-prefix axi_mem --fill-bytes 8 \
        --prefetch-slots 10 --address "$measured_addr" --span-bytes "$((10 * 11 * 64))" \
        --consume-pc "$consume_pc" --run-log "$mode_dir/run.log" \
        --begin-marker "$((0x60 + mode))" --end-marker "$((0x70 + mode))" \
        --matched-only "${extra[@]}" > "$mode_dir/trace-summary.txt" 2>&1
    trace_rc=${PIPESTATUS[1]}
    set -e
    echo "$trace_rc" > "$mode_dir/trace.exit-code"
    if [[ $trace_rc -ne 0 ]]; then
      echo "mode $mode trace analysis failed; see $mode_dir/trace-summary.txt" >&2
      exit "$trace_rc"
    fi
  fi
done

echo "completed_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$artifact_root/RUN_METADATA"
echo "Nano lookup matrix complete: $artifact_root"
