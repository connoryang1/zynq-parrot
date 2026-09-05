#!/usr/bin/env bash
# Run one interactive BlackParrot image through the board's fixed checkout.
# This helper is installed as the unprivileged xilinx user; sudo remains
# limited to the already-reviewed control-program command.
set -euo pipefail

[[ $# -eq 4 ]] || {
  echo "usage: $0 <program.nbf> <nbf-sha256> <runner-sha256> <runtime-ms>" >&2
  exit 2
}

image=$1
expected_nbf_sha=$2
expected_runner_sha=$3
runtime_limit_ms=$4

[[ "$image" =~ ^[A-Za-z0-9._-]+\.nbf$ ]] || { echo "unsafe NBF name" >&2; exit 2; }
[[ "$expected_nbf_sha" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "invalid NBF SHA" >&2; exit 2; }
[[ "$expected_runner_sha" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "invalid runner SHA" >&2; exit 2; }
[[ "$runtime_limit_ms" =~ ^[1-9][0-9]*$ ]] || { echo "invalid runtime limit" >&2; exit 2; }

cd "$HOME/zynq-parrot/cosim/black-parrot-example/zynq"
mkdir -p "$HOME/bp-logs"
lock="$HOME/bp-logs/.control-program.lock"

if [[ -d "$lock" ]]; then
  owner=$(cat "$lock/owner" 2>/dev/null || true)
  if [[ "$owner" =~ ^[0-9]+$ ]] && kill -0 "$owner" 2>/dev/null; then
    echo "ACTIVE_RUNNER"
    exit 75
  fi
  if pgrep -x control-program >/dev/null || pgrep -f '[s]cript .*control-program' >/dev/null; then
    echo "ACTIVE_RUNNER"
    pgrep -af control-program || true
    exit 75
  fi
  rm -f "$lock/owner"
  rmdir "$lock" || { echo "ACTIVE_RUNNER"; exit 75; }
fi
if pgrep -x control-program >/dev/null || pgrep -f '[s]cript .*control-program' >/dev/null; then
  echo "ACTIVE_RUNNER"
  pgrep -af control-program || true
  exit 75
fi

[[ -f "$image" ]] || { echo "MISSING_NBF=$image"; exit 66; }
actual_nbf_sha=$(sha256sum "$image" | awk '{print $1}')
[[ "$actual_nbf_sha" == "$expected_nbf_sha" ]] || {
  echo "NBF_SHA_MISMATCH expected=$expected_nbf_sha actual=$actual_nbf_sha" >&2
  exit 65
}
actual_runner_sha=$(sha256sum ./control-program | awk '{print $1}')
[[ "$actual_runner_sha" == "$expected_runner_sha" ]] || {
  echo "CONTROL_PROGRAM_SHA_MISMATCH expected=$expected_runner_sha actual=$actual_runner_sha" >&2
  exit 64
}

mkdir "$lock" || { echo "ACTIVE_RUNNER"; exit 75; }
printf '%s\n' "$$" > "$lock/owner"
run_id="${image%.nbf}-interactive-$(date -u +%Y%m%dT%H%M%SZ)-$$"
log="$HOME/bp-logs/$run_id.log"
status="$HOME/bp-logs/$run_id.status"
cleanup() {
  rc=$?
  printf 'RUNNER_EXIT=%s\n' "$rc" > "$status"
  rm -f "$lock/owner"
  rmdir "$lock" 2>/dev/null || true
}
trap cleanup EXIT

printf 'CONTROL_PROGRAM_SHA256=%s\nNBF_SHA256=%s\nLOG=%s\n' \
  "$actual_runner_sha" "$actual_nbf_sha" "$log"
command=(sudo -n ./control-program "$image" "$runtime_limit_ms")
printf -v command_text '%q ' "${command[@]}"
set +e
/usr/bin/script -qef -c "$command_text" "$log"
rc=$?
set -e
exit "$rc"
