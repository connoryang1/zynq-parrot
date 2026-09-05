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
  farm_synthesis.sh launch <builder> <label> <top-branch> <black-parrot-branch> [workers]
  farm_synthesis.sh list <builder|all>
  farm_synthesis.sh status <builder> <job-id> <remote-log-root>
  farm_synthesis.sh collect <builder> <job-id> <remote-log-root> [destination]
EOF
}

builder_fields() {
  case ${1:-} in
    bp1) printf '%s\t%s\t%s\n' 'coyang@haight.chillysky.com' '30041' '12' ;;
    bp2) printf '%s\t%s\t%s\n' 'coyang@haight.chillysky.com' '30042' '64' ;;
    bp3) printf '%s\t%s\t%s\n' 'coyang@haight.chillysky.com' '30043' '64' ;;
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
  local target port workers
  IFS=$'\t' read -r target port workers < <(builder_fields "$builder")
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    -p "$port" "$target" "$@"
}

case ${1:-} in
  builders)
    printf 'builder\ttarget\tport\tworkers\n'
    for builder in bp1 bp2 bp3; do
      IFS=$'\t' read -r target port workers < <(builder_fields "$builder")
      printf '%s\t%s\t%s\t%s\n' "$builder" "$target" "$port" "$workers"
    done
    ;;
  probe)
    while read -r builder; do
      printf '=== %s ===\n' "$builder"
      ssh_builder "$builder" 'set -eu; printf "host=%s\nworkers=%s\n" "$(hostname)" "$(nproc)"; free -h | sed -n "1,2p"; df -h /home | tail -1; test -d /tools/Xilinx/Vivado/2024.2 && echo vivado_2024_2=present || echo vivado_2024_2=missing; if pgrep -af "[/]tools/Xilinx/.*/vivado|[/]bin/vivado"; then echo vivado_job=active; else echo vivado_job=idle; fi'
    done < <(builder_names "${2:?builder or all required}")
    ;;
  launch)
    builder=${2:?builder required}
    label=${3:?label required}
    top_branch=${4:?top branch required}
    bp_branch=${5:?BlackParrot branch required}
    IFS=$'\t' read -r target port default_workers < <(builder_fields "$builder")
    workers=${6:-$default_workers}
    if [[ ! $label =~ ^[A-Za-z0-9._-]+$ || ! $workers =~ ^[1-9][0-9]*$ ]]; then
      echo "Label or worker count is invalid." >&2
      exit 2
    fi
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
    } >"$manifest"
    printf 'manifest=%s\n' "$manifest"
    ;;
  list)
    while read -r builder; do
      printf '=== %s ===\n' "$builder"
      ssh_builder "$builder" 'set -eu; shopt -s nullglob; found=0; for status in /home/coyang/fpga-logs-*/*/status; do found=1; printf "%s %s\n" "$(basename "$(dirname "$status")")" "$(cat "$status")"; done; (( found )) || echo no_farm_jobs'
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
    IFS=$'\t' read -r target port workers < <(builder_fields "$builder")
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
