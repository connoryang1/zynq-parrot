#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source_repo=${ZP_BG_VERIFY_SOURCE_REPO:-$(git -C "$script_dir" rev-parse --show-toplevel)}
source_repo=$(cd "$source_repo" && pwd)
repo_name=$(basename "$source_repo")
repo_parent=$(dirname "$source_repo")
state_root=${ZP_BG_VERIFY_STATE_ROOT:-"$repo_parent/.${repo_name}-background-verification"}
log_root=${ZP_BG_VERIFY_LOG_ROOT:-"$source_repo/logs/background-verification"}
build_jobs=${ZP_BG_VERIFY_BUILD_JOBS:-2}
min_free_kb=${ZP_BG_VERIFY_MIN_FREE_KB:-10485760}
timeout_s=${ZP_BG_VERIFY_TIMEOUT_S:-1200}

if [[ ! "$build_jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo "ZP_BG_VERIFY_BUILD_JOBS must be a positive integer." >&2
  exit 2
fi
if [[ ! "$min_free_kb" =~ ^[1-9][0-9]*$ ]]; then
  echo "ZP_BG_VERIFY_MIN_FREE_KB must be a positive integer." >&2
  exit 2
fi
if [[ ! "$timeout_s" =~ ^[1-9][0-9]*$ ]]; then
  echo "ZP_BG_VERIFY_TIMEOUT_S must be a positive integer." >&2
  exit 2
fi

usage() {
  cat <<'EOF'
usage: background_verification.sh start <smoke|targeted|exact|full>
       background_verification.sh plan <smoke|targeted|exact|full>
       background_verification.sh list
       background_verification.sh status <job-id>
       background_verification.sh tail <job-id> [lines]
       background_verification.sh worker <job-id> <layer> <commit>

Environment:
  ZP_BG_VERIFY_SOURCE_REPO   canonical source checkout
  ZP_BG_VERIFY_STATE_ROOT    persistent isolated worktrees and model caches
  ZP_BG_VERIFY_LOG_ROOT      retained job manifests, logs, programs, and traces
  ZP_BG_VERIFY_BUILD_JOBS    low-priority Verilator compiler jobs (default: 2)
  ZP_BG_VERIFY_MIN_FREE_KB   required free space before a traced run (default: 10 GiB)
  ZP_BG_VERIFY_TIMEOUT_S     per-test simulator watchdog (default: 1200 seconds)
EOF
}

validate_layer() {
  case "$1" in
    smoke|targeted|exact|full) ;;
    *) echo "Unknown verification layer: $1" >&2; exit 2 ;;
  esac
}

print_plan() {
  local layer=$1
  validate_layer "$layer"
  case "$layer" in
    smoke)
      printf '%s\n' '2/4 mt_protected_rpc_hardware_test'
      ;;
    targeted)
      printf '%s\n' \
        '2/4 mt_protected_rpc_hardware_test' \
        '2/4 mt_rpc_context_transport_benchmark' \
        '2/4 mt_ctxtsw_smoke_test' \
        '2/4 mt_machine_trap_test' \
        '2/4 mt_csr_isolation_test' \
        '2/4 mt_umode_resident_sv39_data_handoff_test'
      ;;
    exact)
      printf '%s\n' \
        '2/10 mt_protected_rpc_hardware_test' \
        '2/10 mt_rpc_context_transport_benchmark'
      ;;
    full)
      printf '%s\n' \
        'host check-harness' \
        '2/4 mt_protected_rpc_hardware_test' \
        '2/4 mt_rpc_context_transport_benchmark' \
        '2/4 mt_ctxtsw_smoke_test' \
        '2/4 mt_machine_trap_test' \
        '2/4 mt_csr_isolation_test' \
        '2/4 mt_umode_resident_sv39_data_handoff_test' \
        '2/10 mt_protected_rpc_hardware_test' \
        '2/10 mt_rpc_context_transport_benchmark'
      ;;
  esac
}

shell_quote() {
  printf "'%s'" "${1//\'/\'\\\'\'}"
}

job_is_live() {
  local job_dir=$1
  local session pid
  session=$(cat "$job_dir/session" 2>/dev/null || true)
  pid=$(cat "$job_dir/pid" 2>/dev/null || true)
  if [[ -n "$session" ]] && tmux has-session -t "$session" 2>/dev/null; then
    return 0
  fi
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  return 1
}

ensure_no_active_job() {
  local status_file job_dir state
  for status_file in "$log_root"/*/status; do
    [[ -e "$status_file" ]] || continue
    state=$(cat "$status_file")
    [[ "$state" == QUEUED || "$state" == RUNNING ]] || continue
    job_dir=$(dirname "$status_file")
    if job_is_live "$job_dir"; then
      echo "Background verification job $(basename "$job_dir") is already active." >&2
      exit 1
    fi
    printf 'STALE\n' >"$status_file"
  done
}

configure_local_submodule() {
  local checkout=$1
  local relative=$2
  local seed=$3
  git -C "$checkout" submodule init "$relative" >&2
  git -C "$checkout" config --local "submodule.$relative.url" "$seed" >&2
}

prepare_lane() {
  local lane=$1
  local commit=$2
  local lane_dir="$state_root/worktrees/$lane"
  mkdir -p "$state_root/worktrees"

  if [[ ! -e "$lane_dir/.git" ]]; then
    git -C "$source_repo" worktree add --detach "$lane_dir" "$commit" >&2
  else
    if [[ -n "$(git -C "$lane_dir" status --porcelain --untracked-files=no)" ]]; then
      echo "Refusing to overwrite tracked changes in background lane $lane_dir" >&2
      exit 1
    fi
    git -C "$lane_dir" checkout --detach "$commit" >&2
  fi

  configure_local_submodule "$lane_dir" import/basejump_stl "$source_repo/import/basejump_stl"
  configure_local_submodule "$lane_dir" import/black-parrot "$source_repo/import/black-parrot"
  configure_local_submodule "$lane_dir" import/black-parrot-subsystems "$source_repo/import/black-parrot-subsystems"
  git -c protocol.file.allow=always -C "$lane_dir" submodule update --init \
    import/basejump_stl import/black-parrot import/black-parrot-subsystems >&2

  local nested
  for nested in external/basejump_stl external/HardFloat external/bedrock; do
    configure_local_submodule "$lane_dir/import/black-parrot" "$nested" \
      "$source_repo/import/black-parrot/$nested"
  done
  git -c protocol.file.allow=always -C "$lane_dir/import/black-parrot" \
    submodule update --init external/basejump_stl external/HardFloat external/bedrock >&2

  for nested in import/basejump_stl import/opentitan import/riscv-dbg; do
    configure_local_submodule "$lane_dir/import/black-parrot-subsystems" "$nested" \
      "$source_repo/import/black-parrot-subsystems/$nested"
  done
  git -c protocol.file.allow=always -C "$lane_dir/import/black-parrot-subsystems" \
    submodule update --init import/basejump_stl import/opentitan import/riscv-dbg >&2

  printf '%s\n' "$lane_dir"
}

hardware_fingerprint() {
  local lane_dir=$1
  local threads=$2
  local contexts=$3
  {
    printf 'threads=%s\ncontexts=%s\ntrace=1\n' "$threads" "$contexts"
    git -C "$lane_dir" rev-parse HEAD:cosim HEAD:Makefile.env HEAD:testing/Makefile
    git -C "$lane_dir/import/basejump_stl" rev-parse HEAD
    git -C "$lane_dir/import/black-parrot" rev-parse HEAD
    git -C "$lane_dir/import/black-parrot-subsystems" rev-parse HEAD
    git -C "$lane_dir/import/black-parrot/external/basejump_stl" rev-parse HEAD
    git -C "$lane_dir/import/black-parrot/external/HardFloat" rev-parse HEAD
    git -C "$lane_dir/import/black-parrot/external/bedrock" rev-parse HEAD
  } | sha256sum | awk '{print $1}'
}

prepare_model_cache() {
  local lane_dir=$1
  local threads=$2
  local contexts=$3
  local fingerprint_file="$lane_dir/.background-model-fingerprint"
  local current previous=''
  current=$(hardware_fingerprint "$lane_dir" "$threads" "$contexts")
  [[ ! -f "$fingerprint_file" ]] || previous=$(cat "$fingerprint_file")
  if [[ "$current" != "$previous" ]]; then
    local sim_dir="$lane_dir/cosim/black-parrot-minimal-example/verilator"
    echo "Model fingerprint changed; discarding only the isolated lane model."
    rm -rf "$sim_dir/obj_dir"
    rm -f "$sim_dir/bsg_blackparrot_pkg.sv"
    printf '%s\n' "$current" >"$fingerprint_file"
  else
    echo "Reusing matching isolated Verilator model fingerprint $current"
  fi
}

check_trace_space() {
  local available
  available=$(df -Pk "$state_root" | awk 'NR == 2 {print $4}')
  if (( available < min_free_kb )); then
    echo "Insufficient free space for traced verification: ${available} KiB available, ${min_free_kb} KiB required." >&2
    exit 1
  fi
}

archive_run() {
  local lane_dir=$1
  local riscv_dir=$2
  local test=$3
  local artifact_dir=$4
  local sim_dir="$lane_dir/cosim/black-parrot-minimal-example/verilator"
  mkdir -p "$artifact_dir"
  local source
  for source in \
    "$sim_dir/run.log" \
    "$sim_dir/dump.fst" \
    "$sim_dir/prog.nbf" \
    "$sim_dir/prog.riscv" \
    "$riscv_dir/bp-tests/$test.riscv"; do
    [[ -s "$source" ]] || continue
    cp -p "$source" "$artifact_dir/"
  done
  (
    cd "$artifact_dir"
    local files=()
    while IFS= read -r -d '' source; do files+=("${source#./}"); done \
      < <(find . -maxdepth 1 -type f ! -name SHA256SUMS -print0)
    ((${#files[@]} == 0)) || sha256sum "${files[@]}" >SHA256SUMS
  )
}

run_one_test() {
  local lane_dir=$1
  local riscv_dir=$2
  local threads=$3
  local contexts=$4
  local test=$5
  local job_dir=$6
  local lane_name=$7
  local test_dir="$job_dir/artifacts/$lane_name/$test"
  mkdir -p "$test_dir"
  echo "BEGIN test=$test topology=$threads/$contexts time=$(date -u +%FT%TZ)"
  set +e
  env ZP_INSTALL_DIR="$source_repo/install" ZP_RISCV_DIR="$riscv_dir" \
    BSG_TRACE_TIMEOUT_S="$timeout_s" \
    make -C "$lane_dir/testing" "run-$test" \
      NUM_THREADS="$threads" NUM_CONTEXTS="$contexts" TRACE=1 \
      VERILATOR_BUILD_JOBS="$build_jobs" 2>&1 | tee "$test_dir/command.log"
  local rc=${PIPESTATUS[0]}
  set -e
  archive_run "$lane_dir" "$riscv_dir" "$test" "$test_dir"
  printf '%s\t%s\t%s/%s\n' "$test" "$rc" "$threads" "$contexts" >>"$job_dir/results.tsv"
  if (( rc != 0 )); then
    echo "FAIL test=$test exit=$rc"
    return "$rc"
  fi
  echo "PASS test=$test"
}

run_lane() {
  local commit=$1
  local threads=$2
  local contexts=$3
  local job_dir=$4
  shift 4
  local tests=("$@")
  local lane_name="t${threads}-c${contexts}-trace"
  local lane_dir
  lane_dir=$(prepare_lane "$lane_name" "$commit")
  local riscv_dir="$state_root/riscv/$lane_name"
  mkdir -p "$riscv_dir/bp-tests"
  prepare_model_cache "$lane_dir" "$threads" "$contexts"
  check_trace_space
  env ZP_INSTALL_DIR="$source_repo/install" ZP_RISCV_DIR="$riscv_dir" \
    make -C "$lane_dir/testing" clean
  local test
  for test in "${tests[@]}"; do
    run_one_test "$lane_dir" "$riscv_dir" "$threads" "$contexts" \
      "$test" "$job_dir" "$lane_name"
  done
}

finalize_worker() {
  local worker_ok=$1
  local job_dir=$2
  local job_id=$3
  local layer=$4
  local commit=$5
  local verdict=FAIL
  (( worker_ok )) && verdict=PASS
  {
    printf 'job=%s\nlayer=%s\nrevision=%s\nverdict=%s\n\n' \
      "$job_id" "$layer" "$commit" "$verdict"
    column -t -s $'\t' "$job_dir/results.tsv" 2>/dev/null \
      || cat "$job_dir/results.tsv"
  } >"$job_dir/summary.txt"
  printf '%s\n' "$verdict" >"$job_dir/status"
}

worker_main() {
  local job_id=$1
  local layer=$2
  local commit=$3
  local job_dir="$log_root/$job_id"
  local worker_ok=0
  mkdir -p "$state_root" "$log_root"
  [[ -d "$job_dir" ]] || { echo "Missing background job directory: $job_dir" >&2; exit 1; }
  exec 8>"$state_root/worker.lock"
  if ! flock -n 8; then
    echo "Another background verification worker owns $state_root/worker.lock" >&2
    exit 1
  fi
  trap 'code=$?; finalize_worker "$worker_ok" "$job_dir" "$job_id" "$layer" "$commit"; exit "$code"' EXIT
  printf 'RUNNING\n' >"$job_dir/status"
  printf 'test\texit_code\ttopology\n' >"$job_dir/results.tsv"
  {
    printf 'top_commit=%s\nlayer=%s\nbuild_jobs=%s\ntimeout_s=%s\n' \
      "$commit" "$layer" "$build_jobs" "$timeout_s"
    git -C "$source_repo" show -s --format='top_subject=%s' "$commit"
    git -C "$source_repo" ls-tree "$commit" import/black-parrot \
      | awk '{print "black_parrot_commit=" $3}'
    git -C "$source_repo" ls-tree "$commit" import/black-parrot-subsystems \
      | awk '{print "black_parrot_subsystems_commit=" $3}'
    git -C "$source_repo" ls-tree "$commit" import/basejump_stl \
      | awk '{print "basejump_commit=" $3}'
  } >"$job_dir/revisions.txt"
  print_plan "$layer" >"$job_dir/plan.txt"

  if [[ "$layer" == full ]]; then
    local harness_lane
    harness_lane=$(prepare_lane t2-c4-trace "$commit")
    set +e
    python3 -m unittest discover -s "$harness_lane/testing" -p test_check_run.py \
      2>&1 | tee "$job_dir/harness.log"
    local harness_rc=${PIPESTATUS[0]}
    set -e
    printf 'check-harness\t%s\thost\n' "$harness_rc" >>"$job_dir/results.tsv"
    (( harness_rc == 0 )) || return "$harness_rc"
  fi

  if [[ "$layer" == smoke ]]; then
    run_lane "$commit" 2 4 "$job_dir" mt_protected_rpc_hardware_test
  elif [[ "$layer" == targeted || "$layer" == full ]]; then
    run_lane "$commit" 2 4 "$job_dir" \
      mt_protected_rpc_hardware_test \
      mt_rpc_context_transport_benchmark \
      mt_ctxtsw_smoke_test \
      mt_machine_trap_test \
      mt_csr_isolation_test \
      mt_umode_resident_sv39_data_handoff_test
  fi

  if [[ "$layer" == exact || "$layer" == full ]]; then
    run_lane "$commit" 2 10 "$job_dir" \
      mt_protected_rpc_hardware_test \
      mt_rpc_context_transport_benchmark
  fi

  worker_ok=1
}

case ${1:-} in
  plan)
    layer=${2:?verification layer required}
    print_plan "$layer"
    ;;
  start)
    layer=${2:?verification layer required}
    validate_layer "$layer"
    mkdir -p "$state_root" "$log_root"
    command -v tmux >/dev/null || { echo "tmux is required for detached verification." >&2; exit 1; }
    command -v flock >/dev/null || { echo "flock is required for serialized verification." >&2; exit 1; }
    if [[ -n "$(git -C "$source_repo" status --porcelain)" ]]; then
      echo "Refusing background verification from an uncommitted checkout." >&2
      exit 1
    fi
    if [[ ! -x "$source_repo/install/bin/riscv64-unknown-elf-gcc" ]]; then
      echo "Missing shared read-only RISC-V toolchain under $source_repo/install." >&2
      exit 1
    fi
    exec 9>"$state_root/start.lock"
    flock -n 9 || { echo "Another launcher is starting a job." >&2; exit 1; }
    ensure_no_active_job
    commit=$(git -C "$source_repo" rev-parse HEAD)
    job_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "$source_repo" rev-parse --short HEAD)-$layer"
    job_dir="$log_root/$job_id"
    mkdir -p "$job_dir"
    session="bp-bg-${job_id//[^A-Za-z0-9_-]/-}"
    worker_args=(env
      "ZP_BG_VERIFY_SOURCE_REPO=$source_repo"
      "ZP_BG_VERIFY_STATE_ROOT=$state_root"
      "ZP_BG_VERIFY_LOG_ROOT=$log_root"
      "ZP_BG_VERIFY_BUILD_JOBS=$build_jobs"
      "ZP_BG_VERIFY_MIN_FREE_KB=$min_free_kb"
      "ZP_BG_VERIFY_TIMEOUT_S=$timeout_s"
      "$script_dir/background_verification.sh" worker "$job_id" "$layer" "$commit")
    worker_command="trap '' HUP; exec"
    if command -v ionice >/dev/null; then worker_command+=" ionice -c 3"; fi
    worker_command+=" nice -n 15"
    for arg in "${worker_args[@]}"; do worker_command+=" $(shell_quote "$arg")"; done
    worker_command+=" >$(shell_quote "$job_dir/console.log") 2>&1"
    printf 'QUEUED\n' >"$job_dir/status"
    tmux new-session -d -s "$session" "$worker_command"
    pid=$(tmux display-message -p -t "$session" '#{pane_pid}')
    printf '%s\n' "$session" >"$job_dir/session"
    printf '%s\n' "$pid" >"$job_dir/pid"
    printf 'job=%s\nlayer=%s\nrevision=%s\npid=%s\nlog=%s\n' \
      "$job_id" "$layer" "$commit" "$pid" "$job_dir/console.log"
    ;;
  worker)
    worker_main "${2:?job id required}" "${3:?layer required}" "${4:?commit required}"
    ;;
  list)
    [[ -d "$log_root" ]] || exit 0
    for status_file in "$log_root"/*/status; do
      [[ -e "$status_file" ]] || continue
      printf '%s %s\n' "$(basename "$(dirname "$status_file")")" "$(cat "$status_file")"
    done
    ;;
  status)
    job_id=${2:?job id required}
    job_dir="$log_root/$job_id"
    [[ -d "$job_dir" ]] || { echo "Unknown job: $job_id" >&2; exit 1; }
    printf 'status=%s\n' "$(cat "$job_dir/status")"
    [[ ! -f "$job_dir/revisions.txt" ]] || cat "$job_dir/revisions.txt"
    [[ ! -f "$job_dir/summary.txt" ]] || cat "$job_dir/summary.txt"
    printf 'log=%s\n' "$job_dir/console.log"
    ;;
  tail)
    job_id=${2:?job id required}
    lines=${3:-80}
    [[ "$lines" =~ ^[1-9][0-9]*$ ]] || { echo "lines must be a positive integer." >&2; exit 2; }
    job_dir="$log_root/$job_id"
    [[ -f "$job_dir/console.log" ]] || { echo "No console log for job $job_id" >&2; exit 1; }
    tail -n "$lines" "$job_dir/console.log"
    ;;
  *)
    usage
    exit 2
    ;;
esac
