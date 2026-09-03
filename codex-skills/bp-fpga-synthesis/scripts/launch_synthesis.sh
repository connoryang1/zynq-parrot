#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=${ZP_REPO_DIR:-$(git -C "$script_dir" rev-parse --show-toplevel)}
repo_dir=$(cd "$repo_dir" && pwd)
seed_repo_dir=${ZP_FPGA_SEED_REPO_DIR:-$repo_dir}
seed_repo_dir=$(cd "$seed_repo_dir" && pwd)
run_root=${ZP_FPGA_LOG_ROOT:-"$repo_dir/logs/fpga"}
run_root=$(mkdir -p "$run_root" && cd "$run_root" && pwd)
# Allow a clean detached source snapshot to drive the build while retaining
# logs in the active checkout.  This avoids mixing unrelated development edits
# into an otherwise immutable routed implementation.
export ZP_REPO_DIR="$repo_dir"
export ZP_FPGA_SEED_REPO_DIR="$seed_repo_dir"
export ZP_FPGA_LOG_ROOT="$run_root"

# Keep the immutable worker and its recorded configuration in lock-step.  The
# historical full-system flow defaults to the stock aviary configuration, but
# the context-cache PYNQ build must explicitly select its custom dimensions.
fpga_cfg=${FPGA_CFG:-e_bp_unicore_zynqparrot_cfg}
fpga_threads=${FPGA_VIVADO_THREADS:-4}
fpga_num_threads=${FPGA_NUM_THREADS:-}
fpga_num_contexts=${FPGA_NUM_CONTEXTS:-}

if [[ -n "$fpga_num_threads" || -n "$fpga_num_contexts" ]]; then
  if [[ -z "$fpga_num_threads" || -z "$fpga_num_contexts" ]]; then
    echo "FPGA_NUM_THREADS and FPGA_NUM_CONTEXTS must be supplied together." >&2
    exit 2
  fi
fi

# The worker is a fresh tmux-launched invocation of this script.  Export the
# resolved values so it cannot fall back to a different configuration.
export FPGA_CFG="$fpga_cfg"
export FPGA_VIVADO_THREADS="$fpga_threads"
export FPGA_NUM_THREADS="$fpga_num_threads"
export FPGA_NUM_CONTEXTS="$fpga_num_contexts"

usage() {
  echo "usage: $0 start | list | status <job-id> | worker <job-id> <commit>"
  echo "optional environment: FPGA_CFG, FPGA_VIVADO_THREADS, FPGA_NUM_THREADS, FPGA_NUM_CONTEXTS, ZP_FPGA_SEED_REPO_DIR"
}

case ${1:-} in
  start)
    "$script_dir/check_build_ready.sh"
    # The worker builds an isolated worktree at the recorded commit.  Untracked
    # analysis artifacts cannot affect it and should not block a routed build;
    # tracked modifications still make the requested revision ambiguous.
    if [[ -n "$(git -C "$repo_dir" status --porcelain --untracked-files=no)" ]]; then
      echo "Refusing comparison build from a dirty checkout." >&2
      exit 1
    fi
    mkdir -p "$run_root"
    for status_file in "$run_root"/*/status; do
      [[ -e "$status_file" ]] || continue
      [[ "$(cat "$status_file")" == RUNNING ]] || continue
      active_dir=$(dirname "$status_file")
      active_session=$(cat "$active_dir/session" 2>/dev/null || true)
      active_pid=$(cat "$active_dir/pid" 2>/dev/null || true)
      if { [[ -n "$active_session" ]] && tmux has-session -t "$active_session" 2>/dev/null; } \
        || { [[ "$active_pid" =~ ^[0-9]+$ ]] && kill -0 "$active_pid" 2>/dev/null; }; then
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
    # A Codex turn interruption can tear down tmux even though the routed job
    # must continue independently.  Ignore SIGHUP before exec so the worker,
    # make, and Vivado children inherit that disposition and survive loss of
    # the tmux server/PTY.  The pane PID becomes the worker PID after exec and
    # is also used above as an independent liveness check.
    tmux new-session -d -s "$session_name" \
      "trap '' HUP; exec $0 worker $job_id $commit >$job_dir/console.log 2>&1"
    pid=$(tmux display-message -p -t "$session_name" '#{pane_pid}')
    printf '%s\n' "$session_name" >"$job_dir/session"
    printf '%s\n' "$pid" >"$job_dir/pid"
    printf 'RUNNING\n' >"$job_dir/status"
    printf 'job=%s\npid=%s\nlog=%s\nconfig=%s threads=%s contexts=%s\n' \
      "$job_id" "$pid" "$job_dir/console.log" "$fpga_cfg" \
      "${fpga_num_threads:-<default>}" "${fpga_num_contexts:-<default>}"
    ;;
  worker)
    job_id=$2
    commit=$3
    job_dir="$run_root/$job_id"
    worktree="/tmp/zynq-parrot-fpga-$job_id"
    # A shell exit code alone is not enough: interrupted Vivado child runs have
    # previously made GNU make print "No child processes" while the worker's
    # EXIT trap still observed zero.  Keep the pessimistic marker until every
    # routed acceptance artifact has been checked explicitly.
    worker_ok=0
    trap 'code=$?; if (( worker_ok )); then printf "PASS\n" >"$job_dir/status"; else printf "FAIL\n" >"$job_dir/status"; fi; exit $code' EXIT
    printf 'top_commit=%s\n' "$commit" >"$job_dir/revisions.txt"
    printf 'cfg=%s\nvivado_threads=%s\nnum_threads=%s\nnum_contexts=%s\n' \
      "$fpga_cfg" "$fpga_threads" "${fpga_num_threads:-<default>}" \
      "${fpga_num_contexts:-<default>}" >>"$job_dir/revisions.txt"
    git -C "$repo_dir" worktree add --detach "$worktree" "$commit"
    # Optimization checkpoints may pin local BlackParrot or BaseJump commits
    # that have not been pushed upstream yet. Seed those submodules from the
    # source checkout; other immutable dependencies use their normal URLs.
    git -C "$worktree" submodule init \
      import/basejump_stl import/black-parrot import/black-parrot-subsystems
    git -C "$worktree" config --local submodule.import/black-parrot.url "$repo_dir/import/black-parrot"
    git -C "$worktree" config --local submodule.import/basejump_stl.url "$repo_dir/import/basejump_stl"
    git -c protocol.file.allow=always -C "$worktree" submodule update --init \
      import/basejump_stl import/black-parrot import/black-parrot-subsystems
    git -C "$worktree/import/black-parrot" submodule init \
      external/basejump_stl external/HardFloat external/bedrock
    git -C "$worktree/import/black-parrot" config --local \
      submodule.external/basejump_stl.url \
      "$seed_repo_dir/import/black-parrot/external/basejump_stl"
    # A detached source worktree may have only the top-level BlackParrot
    # gitlink populated.  Seed its pinned nested dependencies before using it
    # as the local source for the isolated implementation worktree below.
    # A detached source snapshot may have only gitlinks, while the active
    # checkout owns pinned nested submodule objects that old upstream remotes
    # no longer advertise. Seed the snapshot from that checkout before the
    # implementation worktree asks for the same exact objects.
    for nested in external/basejump_stl external/HardFloat external/bedrock; do
      if [[ ! -d "$seed_repo_dir/import/black-parrot/$nested/.git" \
            && ! -f "$seed_repo_dir/import/black-parrot/$nested/.git" ]]; then
        echo "Missing nested submodule seed: $seed_repo_dir/import/black-parrot/$nested" >&2
        exit 1
      fi
    done
    git -C "$repo_dir/import/black-parrot" config --local \
      submodule.external/basejump_stl.url \
      "$seed_repo_dir/import/black-parrot/external/basejump_stl"
    git -C "$repo_dir/import/black-parrot" config --local \
      submodule.external/HardFloat.url \
      "$seed_repo_dir/import/black-parrot/external/HardFloat"
    git -C "$repo_dir/import/black-parrot" config --local \
      submodule.external/bedrock.url \
      "$seed_repo_dir/import/black-parrot/external/bedrock"
    git -C "$repo_dir/import/black-parrot" submodule init \
      external/basejump_stl external/HardFloat external/bedrock
    git -c protocol.file.allow=always -C "$repo_dir/import/black-parrot" \
      submodule update --init \
      external/basejump_stl external/HardFloat external/bedrock
    git -c protocol.file.allow=always -C "$worktree/import/black-parrot" \
      submodule update --init \
      external/basejump_stl external/HardFloat external/bedrock
    git -C "$worktree/import/black-parrot-subsystems" submodule update --init \
      import/riscv-dbg
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
    if [[ ! -s "$repo_dir/install/gen/v/rv_plic/rtl/rv_plic_reg_pkg.sv" ]]; then
      echo "Missing generated OpenTitan PLIC RTL in the shared install prefix." >&2
      exit 1
    fi
    git -C "$worktree/import/black-parrot" rev-parse HEAD | sed 's/^/black_parrot_commit=/' >>"$job_dir/revisions.txt"
    git -C "$worktree/import/basejump_stl" rev-parse HEAD | sed 's/^/basejump_commit=/' >>"$job_dir/revisions.txt"
    git -C "$worktree/import/black-parrot/external/basejump_stl" rev-parse HEAD \
      | sed 's/^/black_parrot_basejump_commit=/' >>"$job_dir/revisions.txt"
    build_args=(
      "BOARDNAME=pynqz2"
      "VIVADO_VERSION=2024.2"
      "VIVADO_MODE=batch"
      "CFG=$fpga_cfg"
      "THREADS=$fpga_threads"
      "VIVADO_RUN=$script_dir/run_vivado_2024_2.sh"
      "ZP_INSTALL_DIR=$repo_dir/install"
      "ZP_RISCV_DIR=$repo_dir/riscv"
    )
    if [[ -n "$fpga_num_threads" ]]; then
      build_args+=("NUM_THREADS=$fpga_num_threads" "NUM_CONTEXTS=$fpga_num_contexts")
    fi
    make -j1 -C "$worktree/cosim/black-parrot-example/vivado" clean "${build_args[@]}"
    make -j1 -C "$worktree/cosim/black-parrot-example/vivado" fpga_build pack_bitstream \
      "${build_args[@]}"
    vivado_dir="$worktree/cosim/black-parrot-example/vivado"
    example_dir="$worktree/cosim/black-parrot-example"
    "$script_dir/summarize_vivado.sh" "$vivado_dir" >"$job_dir/summary.txt"

    timing=$(find "$vivado_dir" -type f -name '*timing_summary_routed.rpt' -print -quit)
    util=$(find "$vivado_dir" -type f \
      \( -name '*utilization*placed*.rpt' -o -name '*utilization*routed*.rpt' \) \
      -print -quit)
    for required in \
      "$vivado_dir/black_parrot_bd_1.bit" \
      "$vivado_dir/black_parrot_bd_1.hwh" \
      "$vivado_dir/black_parrot_bd_1.map" \
      "$timing" "$util"; do
      if [[ -z "$required" || ! -s "$required" ]]; then
        echo "Missing routed acceptance artifact: ${required:-<report not found>}" >&2
        exit 1
      fi
    done

    packed=$(find "$example_dir" -maxdepth 1 -name '*.tar.xz.b64' -print -quit)
    if [[ -z "$packed" || ! -s "$packed" ]]; then
      echo "Missing packed bitstream artifact." >&2
      exit 1
    fi
    cp -p "$packed" "$job_dir/"
    worker_ok=1
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
