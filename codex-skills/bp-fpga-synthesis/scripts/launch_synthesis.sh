#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
run_root="$repo_dir/logs/fpga"

usage() {
  echo "usage: $0 start | list | status <job-id> | worker <job-id> <commit>"
}

case ${1:-} in
  start)
    "$script_dir/check_build_ready.sh"
    if [[ -n "$(git -C "$repo_dir" status --porcelain)" ]]; then
      echo "Refusing comparison build from a dirty checkout." >&2
      exit 1
    fi
    mkdir -p "$run_root"
    for status_file in "$run_root"/*/status; do
      [[ -e "$status_file" ]] || continue
      [[ "$(cat "$status_file")" == RUNNING ]] || continue
      active_dir=$(dirname "$status_file")
      active_session=$(cat "$active_dir/session" 2>/dev/null || true)
      if [[ -n "$active_session" ]] && tmux has-session -t "$active_session" 2>/dev/null; then
        echo "Refusing to compete with active job $(basename "$active_dir")." >&2
        exit 1
      fi
      echo "STALE" >"$status_file"
    done
    job_id=$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "$repo_dir" rev-parse --short HEAD)
    job_dir="$run_root/$job_id"
    mkdir -p "$job_dir"
    commit=$(git -C "$repo_dir" rev-parse HEAD)
    session_name="bp-fpga-$job_id"
    tmux new-session -d -s "$session_name" \
      "$0 worker $job_id $commit >$job_dir/console.log 2>&1"
    pid=$(tmux display-message -p -t "$session_name" '#{pane_pid}')
    printf '%s\n' "$session_name" >"$job_dir/session"
    printf '%s\n' "$pid" >"$job_dir/pid"
    printf 'RUNNING\n' >"$job_dir/status"
    printf 'job=%s\npid=%s\nlog=%s\n' "$job_id" "$pid" "$job_dir/console.log"
    ;;
  worker)
    job_id=$2
    commit=$3
    job_dir="$run_root/$job_id"
    worktree="/tmp/zynq-parrot-fpga-$job_id"
    trap 'code=$?; if (( code == 0 )); then echo PASS >"$job_dir/status"; else echo FAIL >"$job_dir/status"; fi; exit $code' EXIT
    printf 'top_commit=%s\n' "$commit" >"$job_dir/revisions.txt"
    git -C "$repo_dir" worktree add --detach "$worktree" "$commit"
    git -C "$worktree" submodule update --init \
      import/basejump_stl import/black-parrot import/black-parrot-subsystems
    git -C "$worktree/import/black-parrot" submodule update --init \
      external/basejump_stl external/HardFloat external/bedrock
    for required in \
      import/basejump_stl/bsg_mem/bsg_mem_1rw_sync.sv \
      import/black-parrot/external/basejump_stl/bsg_mem/bsg_mem_1rw_sync.sv \
      import/black-parrot/external/HardFloat/source/HardFloat_primitives.v \
      import/black-parrot-subsystems/blackparrot/v/bp_axi_top.sv; do
      if [[ ! -f "$worktree/$required" ]]; then
        echo "Missing required FPGA source: $required" >&2
        exit 1
      fi
    done
    git -C "$worktree/import/black-parrot" rev-parse HEAD | sed 's/^/black_parrot_commit=/' >>"$job_dir/revisions.txt"
    make -C "$worktree/cosim/black-parrot-example/vivado" fpga_build pack_bitstream \
      BOARDNAME=pynqz2 VIVADO_VERSION=2024.2 VIVADO_MODE=batch \
      CFG=e_bp_unicore_zynqparrot_cfg \
      ZP_INSTALL_DIR="$repo_dir/install" ZP_RISCV_DIR="$repo_dir/riscv"
    "$script_dir/summarize_vivado.sh" "$worktree/cosim/black-parrot-example/vivado" >"$job_dir/summary.txt"
    find "$worktree/cosim/black-parrot-example" -maxdepth 1 -name '*.tar.xz.b64' -exec cp -p {} "$job_dir/" \;
    ;;
  list)
    mkdir -p "$run_root"
    for status in "$run_root"/*/status; do
      [[ -e "$status" ]] || continue
      printf '%s %s\n' "$(basename "$(dirname "$status")")" "$(cat "$status")"
    done
    ;;
  status)
    job_id=${2:?job id required}
    job_dir="$run_root/$job_id"
    cat "$job_dir/status"
    [[ ! -e "$job_dir/revisions.txt" ]] || cat "$job_dir/revisions.txt"
    [[ ! -e "$job_dir/summary.txt" ]] || cat "$job_dir/summary.txt"
    echo "log=$job_dir/console.log"
    ;;
  *)
    usage
    exit 2
    ;;
esac
