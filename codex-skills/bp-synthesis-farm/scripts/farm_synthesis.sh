#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
manifest_root=${BP_FARM_MANIFEST_ROOT:-"$repo_dir/logs/fpga-farm"}

usage() {
  cat <<'EOF'
usage:
  farm_synthesis.sh builders
  farm_synthesis.sh probe <bp1|bp2|bp3|all>
  farm_synthesis.sh link <top-worktree> <black-parrot-worktree>
  BP_SYNTH_DECISION='...' BP_SYNTH_CHEAPER_GATES='...' \
    BP_SYNTH_PASS_ACTION='...' BP_SYNTH_FAIL_ACTION='...' \
    farm_synthesis.sh admit <builder> <label> <top-branch> <black-parrot-branch> <priority>
  farm_synthesis.sh plan <builder> <label> <top-branch> <black-parrot-branch>
  farm_synthesis.sh launch <builder> <label> <top-branch> <black-parrot-branch> [workers]
  farm_synthesis.sh cancel <builder> <job-id> <remote-log-root>
  farm_synthesis.sh list <builder|all>
  farm_synthesis.sh status <builder> <job-id> <remote-log-root>
  farm_synthesis.sh collect <builder> <job-id> <remote-log-root> [destination]
EOF
}

admission_path() {
  local builder=$1
  local label=$2
  printf '%s/admissions/%s/%s.env\n' "$manifest_root" "$builder" "$label"
}

require_admission_text() {
  local name=$1
  local value=$2
  if [[ -z $value || $value == *$'\n'* || $value == *$'\r'* ]]; then
    echo "$name must be a non-empty single-line statement." >&2
    return 2
  fi
}

load_admission() {
  local file=$1
  admission_builder=
  admission_label=
  admission_top_branch=
  admission_bp_branch=
  admission_priority=
  admission_decision=
  admission_cheaper_gates=
  admission_pass_action=
  admission_fail_action=
  admission_created_utc=
  admission_launched_job=
  # Admission files are generated locally by this script with shell-escaped values.
  # shellcheck disable=SC1090
  source "$file"
  require_admission_text admission_decision "$admission_decision"
  require_admission_text admission_cheaper_gates "$admission_cheaper_gates"
  require_admission_text admission_pass_action "$admission_pass_action"
  require_admission_text admission_fail_action "$admission_fail_action"
  if [[ ! $admission_priority =~ ^[1-9][0-9]*$ ]]; then
    echo "Admission priority must be a positive integer (1 is highest)." >&2
    return 2
  fi
}

print_admission() {
  printf 'admission=%s\n' "$1"
  printf 'candidate=%s/%s top=%s black_parrot=%s priority=%s\n' \
    "$admission_builder" "$admission_label" "$admission_top_branch" \
    "$admission_bp_branch" "$admission_priority"
  printf 'decision=%s\ncheaper_gates_insufficient=%s\npass_next=%s\nfail_next=%s\n' \
    "$admission_decision" "$admission_cheaper_gates" \
    "$admission_pass_action" "$admission_fail_action"
}

require_admission_match() {
  local builder=$1
  local label=$2
  local top_branch=$3
  local bp_branch=$4
  if [[ $admission_builder != "$builder" || $admission_label != "$label" \
     || $admission_top_branch != "$top_branch" || $admission_bp_branch != "$bp_branch" ]]; then
    echo "Admission does not match the requested builder, label, or branches." >&2
    return 1
  fi
}

builder_fields() {
  case ${1:-} in
    bp1) printf '%s\t%s\t%s\t%s\n' 'coyang@haight.chillysky.com' '30041' '12' '8' ;;
    bp2) printf '%s\t%s\t%s\t%s\n' 'coyang@haight.chillysky.com' '30042' '64' '8' ;;
    bp3) printf '%s\t%s\t%s\t%s\n' 'coyang@haight.chillysky.com' '30043' '64' '8' ;;
    *) echo "Unknown builder: ${1:-<empty>}" >&2; return 2 ;;
  esac
}

builder_names() {
  if [[ ${1:-} == all ]]; then
    printf '%s\n' bp1 bp2 bp3
  else
    builder_fields "${1:?builder required}" >/dev/null
    printf '%s\n' "$1"
  fi
}

ssh_builder() {
  local builder=$1
  shift
  local target port host_cores vivado_threads
  IFS=$'\t' read -r target port host_cores vivado_threads < <(builder_fields "$builder")
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    -p "$port" "$target" "$@"
}

case ${1:-} in
  builders)
    printf 'builder\ttarget\tport\thost_cores\tdefault_vivado_threads\n'
    for builder in bp1 bp2 bp3; do
      IFS=$'\t' read -r target port host_cores vivado_threads < <(builder_fields "$builder")
      printf '%s\t%s\t%s\t%s\t%s\n' "$builder" "$target" "$port" "$host_cores" "$vivado_threads"
    done
    ;;
  probe)
    while read -r builder; do
      printf '=== %s ===\n' "$builder"
      ssh_builder "$builder" 'set -eu; printf "host=%s\nworkers=%s\n" "$(hostname)" "$(nproc)"; free -h | sed -n "1,2p"; df -h /home | tail -1; test -d /tools/Xilinx/Vivado/2024.2 && echo vivado_2024_2=present || echo vivado_2024_2=missing; if pgrep -a -x vivado; then echo vivado_job=active; else echo vivado_job=idle; fi' </dev/null
    done < <(builder_names "${2:?builder or all required}")
    ;;
  link)
    top_worktree=${2:?top-level worktree required}
    bp_worktree=${3:?BlackParrot worktree required}
    git -C "$top_worktree" rev-parse --show-toplevel >/dev/null
    git -C "$bp_worktree" rev-parse --show-toplevel >/dev/null
    if ! git -C "$top_worktree" diff --quiet -- import/black-parrot \
       || ! git -C "$top_worktree" diff --cached --quiet -- import/black-parrot; then
      echo "Refusing to replace a modified import/black-parrot gitlink." >&2
      exit 1
    fi
    bp_commit=$(git -C "$bp_worktree" rev-parse HEAD)
    git -C "$top_worktree" update-index \
      --cacheinfo 160000,"$bp_commit",import/black-parrot
    indexed=$(git -C "$top_worktree" ls-files -s import/black-parrot | awk '{print $2}')
    if [[ $indexed != "$bp_commit" ]]; then
      echo "Indexed gitlink $indexed does not match BlackParrot $bp_commit." >&2
      exit 1
    fi
    printf 'top_worktree=%s\nblack_parrot_worktree=%s\nblack_parrot_commit=%s\n' \
      "$(git -C "$top_worktree" rev-parse --show-toplevel)" \
      "$(git -C "$bp_worktree" rev-parse --show-toplevel)" \
      "$bp_commit"
    ;;
  admit)
    builder=${2:?builder required}
    label=${3:?label required}
    top_branch=${4:?top branch required}
    bp_branch=${5:?BlackParrot branch required}
    priority=${6:?candidate priority required; use 1 for highest}
    builder_fields "$builder" >/dev/null
    if [[ ! $label =~ ^[A-Za-z0-9._-]+$ || ! $priority =~ ^[1-9][0-9]*$ ]]; then
      echo "Label or priority is invalid; priority is a positive integer (1 is highest)." >&2
      exit 2
    fi
    decision=${BP_SYNTH_DECISION:-}
    cheaper_gates=${BP_SYNTH_CHEAPER_GATES:-}
    pass_action=${BP_SYNTH_PASS_ACTION:-}
    fail_action=${BP_SYNTH_FAIL_ACTION:-}
    require_admission_text BP_SYNTH_DECISION "$decision"
    require_admission_text BP_SYNTH_CHEAPER_GATES "$cheaper_gates"
    require_admission_text BP_SYNTH_PASS_ACTION "$pass_action"
    require_admission_text BP_SYNTH_FAIL_ACTION "$fail_action"
    admission_file=$(admission_path "$builder" "$label")
    if [[ -e $admission_file ]]; then
      echo "Refusing to replace existing admission: $admission_file" >&2
      echo "Use a new candidate label so every synthesis decision remains immutable." >&2
      exit 1
    fi
    mkdir -p "$(dirname "$admission_file")"
    {
      printf 'admission_builder=%q\n' "$builder"
      printf 'admission_label=%q\n' "$label"
      printf 'admission_top_branch=%q\n' "$top_branch"
      printf 'admission_bp_branch=%q\n' "$bp_branch"
      printf 'admission_priority=%q\n' "$priority"
      printf 'admission_decision=%q\n' "$decision"
      printf 'admission_cheaper_gates=%q\n' "$cheaper_gates"
      printf 'admission_pass_action=%q\n' "$pass_action"
      printf 'admission_fail_action=%q\n' "$fail_action"
      printf 'admission_created_utc=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$admission_file"
    load_admission "$admission_file"
    print_admission "$admission_file"
    ;;
  plan)
    builder=${2:?builder required}
    label=${3:?label required}
    top_branch=${4:?top branch required}
    bp_branch=${5:?BlackParrot branch required}
    builder_fields "$builder" >/dev/null
    admission_file=$(admission_path "$builder" "$label")
    if [[ ! -f $admission_file ]]; then
      echo "No admission exists for $builder/$label." >&2
      exit 1
    fi
    load_admission "$admission_file"
    require_admission_match "$builder" "$label" "$top_branch" "$bp_branch"
    print_admission "$admission_file"
    if [[ -n $admission_launched_job ]]; then
      printf 'state=launched job=%s\n' "$admission_launched_job"
    else
      printf 'state=admitted\n'
    fi
    ;;
  launch)
    builder=${2:?builder required}
    label=${3:?label required}
    top_branch=${4:?top branch required}
    bp_branch=${5:?BlackParrot branch required}
    IFS=$'\t' read -r target port host_cores default_workers < <(builder_fields "$builder")
    workers=${6:-$default_workers}
    if [[ ! $label =~ ^[A-Za-z0-9._-]+$ || ! $workers =~ ^[1-9][0-9]*$ ]]; then
      echo "Label or worker count is invalid." >&2
      exit 2
    fi
    admission_file=$(admission_path "$builder" "$label")
    if [[ ! -f $admission_file ]]; then
      echo "Refusing unadmitted synthesis candidate: $builder/$label" >&2
      echo "Run 'farm_synthesis.sh admit' with a decision and both outcome actions first." >&2
      exit 1
    fi
    load_admission "$admission_file"
    if ! require_admission_match "$builder" "$label" "$top_branch" "$bp_branch"; then
      print_admission "$admission_file" >&2
      exit 1
    fi
    if [[ -n $admission_launched_job ]]; then
      echo "Admission was already consumed by job $admission_launched_job; use a new label." >&2
      exit 1
    fi
    print_admission "$admission_file"
    mkdir -p "$manifest_root/$builder"
    output=$(ssh_builder "$builder" bash -s -- "$label" "$top_branch" "$bp_branch" "$workers" <<'REMOTE'
set -euo pipefail
label=$1
top_branch=$2
bp_branch=$3
workers=$4
main=/home/coyang/zynq-parrot
bp_seed=$main/import/black-parrot
source_root=/home/coyang/fpga-sources
log_root=/home/coyang/fpga-logs-$label

if pgrep -af '[/]tools/Xilinx/.*/vivado|[/]bin/vivado' >/dev/null; then
  echo "Refusing to compete with an active Vivado process on $(hostname)." >&2
  exit 1
fi
test -x "$main/codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh"
git -C "$main" fetch --no-tags origin \
  "refs/heads/$top_branch:refs/remotes/origin/$top_branch"
top_commit=$(git -C "$main" rev-parse "refs/remotes/origin/$top_branch")
if ! git -C "$bp_seed" remote get-url connoryang >/dev/null 2>&1; then
  git -C "$bp_seed" remote add connoryang git@github.com:connoryang1/black-parrot.git
fi
git -C "$bp_seed" fetch --no-tags connoryang \
  "refs/heads/$bp_branch:refs/remotes/connoryang/$bp_branch"
bp_commit=$(git -C "$bp_seed" rev-parse "refs/remotes/connoryang/$bp_branch")
gitlink=$(git -C "$main" ls-tree "$top_commit" import/black-parrot | awk '{print $3}')
if [[ $gitlink != "$bp_commit" ]]; then
  echo "Top gitlink $gitlink does not match BlackParrot $bp_commit." >&2
  exit 1
fi

source_dir=$source_root/${label}-${top_commit:0:8}
mkdir -p "$source_root"
if [[ -e $source_dir ]]; then
  test "$(git -C "$source_dir" rev-parse HEAD)" = "$top_commit"
  test -z "$(git -C "$source_dir" status --porcelain --untracked-files=no)"
else
  git -C "$main" worktree add --detach "$source_dir" "$top_commit"
fi
git -C "$source_dir" submodule init \
  import/basejump_stl import/black-parrot import/black-parrot-subsystems
git -C "$source_dir" config --local submodule.import/black-parrot.url "$bp_seed"
git -C "$source_dir" config --local submodule.import/basejump_stl.url "$main/import/basejump_stl"
git -C "$source_dir" config --local submodule.import/black-parrot-subsystems.url "$main/import/black-parrot-subsystems"
git -c protocol.file.allow=always -C "$source_dir" submodule update --init \
  import/basejump_stl import/black-parrot import/black-parrot-subsystems
test "$(git -C "$source_dir/import/black-parrot" rev-parse HEAD)" = "$bp_commit"
git -C "$source_dir/import/black-parrot" submodule init \
  external/basejump_stl external/HardFloat external/bedrock
for nested in basejump_stl HardFloat bedrock; do
  git -C "$source_dir/import/black-parrot" config --local \
    "submodule.external/$nested.url" "$bp_seed/external/$nested"
done
git -c protocol.file.allow=always -C "$source_dir/import/black-parrot" \
  submodule update --init external/basejump_stl external/HardFloat external/bedrock
git -C "$source_dir/import/black-parrot-subsystems" submodule update --init import/riscv-dbg
[[ -e $source_dir/install ]] || ln -s "$main/install" "$source_dir/install"
[[ -e $source_dir/riscv ]] || ln -s "$main/riscv" "$source_dir/riscv"
ZP_REPO_DIR="$source_dir" \
  "$main/codex-skills/bp-fpga-synthesis/scripts/check_build_ready.sh"
launch_output=$(env \
  ZP_REPO_DIR="$source_dir" \
  ZP_FPGA_SEED_REPO_DIR="$source_dir" \
  ZP_FPGA_LOG_ROOT="$log_root" \
  FPGA_CFG=e_bp_unicore_zynqparrot_cfg \
  FPGA_VIVADO_THREADS="$workers" \
  "$main/codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh" start)
printf '%s\n' "$launch_output"
job_id=$(printf '%s\n' "$launch_output" | sed -n 's/^job=//p' | head -1)
printf 'FARM_BUILDER=%s\nFARM_JOB=%s\nFARM_TOP=%s\nFARM_BP=%s\nFARM_LOG_ROOT=%s\nFARM_SOURCE=%s\n' \
  "$(hostname)" "$job_id" "$top_commit" "$bp_commit" "$log_root" "$source_dir"
REMOTE
)
    printf '%s\n' "$output"
    job_id=$(printf '%s\n' "$output" | sed -n 's/^FARM_JOB=//p' | tail -1)
    top_commit=$(printf '%s\n' "$output" | sed -n 's/^FARM_TOP=//p' | tail -1)
    bp_commit=$(printf '%s\n' "$output" | sed -n 's/^FARM_BP=//p' | tail -1)
    log_root=$(printf '%s\n' "$output" | sed -n 's/^FARM_LOG_ROOT=//p' | tail -1)
    source_dir=$(printf '%s\n' "$output" | sed -n 's/^FARM_SOURCE=//p' | tail -1)
    manifest=$manifest_root/$builder/$job_id.env
    {
      printf 'builder=%q\n' "$builder"
      printf 'label=%q\n' "$label"
      printf 'job_id=%q\n' "$job_id"
      printf 'top_commit=%q\n' "$top_commit"
      printf 'black_parrot_commit=%q\n' "$bp_commit"
      printf 'remote_log_root=%q\n' "$log_root"
      printf 'remote_source_dir=%q\n' "$source_dir"
      printf 'workers=%q\n' "$workers"
      printf 'admission_file=%q\n' "$admission_file"
      printf 'candidate_priority=%q\n' "$admission_priority"
      printf 'decision=%q\n' "$admission_decision"
      printf 'cheaper_gates_insufficient=%q\n' "$admission_cheaper_gates"
      printf 'pass_next=%q\n' "$admission_pass_action"
      printf 'fail_next=%q\n' "$admission_fail_action"
    } >"$manifest"
    printf 'admission_launched_job=%q\n' "$job_id" >>"$admission_file"
    printf 'manifest=%s\n' "$manifest"
    ;;
  cancel)
    builder=${2:?builder required}
    job_id=${3:?job id required}
    log_root=${4:?remote log root required}
    if [[ ! $job_id =~ ^[A-Za-z0-9._-]+$ || ! $log_root =~ ^/home/coyang/fpga-logs-[A-Za-z0-9._/-]+$ ]]; then
      echo "Job ID or remote log root is invalid." >&2
      exit 2
    fi
    ssh_builder "$builder" bash -s -- "$job_id" "$log_root" <<'REMOTE'
set -euo pipefail
job_id=$1
log_root=$2
job_dir=$log_root/$job_id
test -d "$job_dir"
test "$(cat "$job_dir/status")" = RUNNING
session=$(cat "$job_dir/session" 2>/dev/null || true)
pid=$(cat "$job_dir/pid" 2>/dev/null || true)
pgid=
if [[ $pid =~ ^[0-9]+$ ]]; then
  pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ' || true)
fi
if [[ -n $session ]] && tmux has-session -t "$session" 2>/dev/null; then
  tmux kill-session -t "$session"
fi
if [[ $pgid =~ ^[0-9]+$ ]]; then
  kill -TERM -- "-$pgid" 2>/dev/null || true
  for attempt in {1..20}; do
    kill -0 -- "-$pgid" 2>/dev/null || break
    sleep 0.5
  done
  kill -KILL -- "-$pgid" 2>/dev/null || true
  sleep 1
  if kill -0 -- "-$pgid" 2>/dev/null; then
    echo "Job process group $pgid remains after cancellation." >&2
    exit 1
  fi
fi
if pgrep -a -x vivado; then
  echo "Vivado processes remain on the builder after cancellation." >&2
  exit 1
fi
printf 'CANCELLED\n' >"$job_dir/status"
printf 'cancelled=%s\n' "$job_id"
REMOTE
    ;;
  list)
    while read -r builder; do
      printf '=== %s ===\n' "$builder"
      ssh_builder "$builder" 'set -eu; shopt -s nullglob; found=0; for status in /home/coyang/fpga-logs-*/*/status; do found=1; printf "%s %s\n" "$(basename "$(dirname "$status")")" "$(cat "$status")"; done; (( found )) || echo no_farm_jobs' </dev/null
    done < <(builder_names "${2:?builder or all required}")
    ;;
  status)
    builder=${2:?builder required}
    job_id=${3:?job id required}
    log_root=${4:?remote log root required}
    ssh_builder "$builder" "ZP_FPGA_LOG_ROOT=$(printf %q "$log_root") /home/coyang/zynq-parrot/codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh status $(printf %q "$job_id")"
    ;;
  collect)
    builder=${2:?builder required}
    job_id=${3:?job id required}
    log_root=${4:?remote log root required}
    destination=${5:-"$manifest_root/$builder/$job_id"}
    status=$(ssh_builder "$builder" "cat $(printf %q "$log_root/$job_id/status")")
    if [[ $status != PASS ]]; then
      echo "Refusing to collect job $job_id with status $status." >&2
      exit 1
    fi
    mkdir -p "$destination"
    IFS=$'\t' read -r target port host_cores vivado_threads < <(builder_fields "$builder")
    ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
      -p "$port" "$target" \
      "tar -C $(printf %q "$log_root/$job_id") -cf - ." \
      | tar -C "$destination" -xf -
    for required in status revisions.txt summary.txt console.log; do
      if [[ ! -s $destination/$required ]]; then
        echo "Collected job is missing $required." >&2
        exit 1
      fi
    done
    package=$(find "$destination" -maxdepth 1 -name '*.tar.xz.b64' -print -quit)
    if [[ -z $package || ! -s $package ]]; then
      echo "Collected job is missing its packed bitstream." >&2
      exit 1
    fi
    printf 'collected=%s\n' "$destination"
    ;;
  *)
    usage
    exit 2
    ;;
esac
