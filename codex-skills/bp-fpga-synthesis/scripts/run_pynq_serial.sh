#!/usr/bin/env bash
# Launch one PYNQ control-program run, retain its transcript on the board, and
# wait for that exact runner.  The board has one PL/DRAM control path: concurrent
# control-program instances corrupt each other's state, so a board-side mkdir
# lock is deliberately used in addition to a process check.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <ssh-host> <program.nbf> [remote-zynq-directory]" >&2
  exit 2
fi

ssh_host=$1
image=$(basename -- "$2")
remote_dir=${3:-'~/zynq-parrot/cosim/black-parrot-example/zynq'}
# Let callers bound a run without wrapping the launcher in GNU timeout: the
# latter can kill only the local SSH process and leave the privileged board
# worker alive.  control-program itself owns clean target shutdown.
runtime_limit_ms=${PYNQ_CONTROL_PROGRAM_TIMEOUT_MS:-}
[[ -z "$runtime_limit_ms" || "$runtime_limit_ms" =~ ^[1-9][0-9]*$ ]] || {
  echo "FAIL: PYNQ_CONTROL_PROGRAM_TIMEOUT_MS must be a positive integer" >&2
  exit 2
}
[[ "$image" =~ ^[A-Za-z0-9._-]+\.nbf$ ]] || {
  echo "FAIL: program must be a simple .nbf filename" >&2
  exit 2
}

run_id="${image%.nbf}-$(date -u +%Y%m%dT%H%M%SZ)-$$"

set +e
launch_output=$(ssh -o BatchMode=yes "$ssh_host" bash -s -- "$remote_dir" "$image" "$run_id" "$runtime_limit_ms" <<'REMOTE'
set -euo pipefail
remote_dir=$1
image=$2
run_id=$3
runtime_limit_ms=$4
eval "cd $remote_dir"
mkdir -p "$HOME/bp-logs"
lock="$HOME/bp-logs/.control-program.lock"
log="$HOME/bp-logs/$run_id.log"
status="$HOME/bp-logs/$run_id.status"
pidfile="$HOME/bp-logs/$run_id.pid"

# Do not merely trust a stale pidfile.  Reject a live serial wrapper or a
# legacy/manual direct runner.  A lock whose recorded wrapper PID is dead is
# safe to reclaim (for example after a board power cycle).
if [[ -d "$lock" ]]; then
  owner=$(cat "$lock/owner" 2>/dev/null || true)
  if [[ "$owner" =~ ^[0-9]+$ ]] && kill -0 "$owner" 2>/dev/null; then
    echo "ACTIVE_RUNNER"
    exit 75
  fi
  if pgrep -x control-program >/dev/null || pgrep -f '[s]cript .*control-program' >/dev/null; then
    echo "ACTIVE_RUNNER"
    pgrep -af 'control-program' || true
    exit 75
  fi
  rm -f "$lock/owner"
  rmdir "$lock" || { echo "ACTIVE_RUNNER"; exit 75; }
  echo "STALE_RUNNER_LOCK_RECLAIMED"
fi
if pgrep -x control-program >/dev/null || pgrep -f '[s]cript .*control-program' >/dev/null; then
  echo "ACTIVE_RUNNER"
  pgrep -af 'control-program' || true
  exit 75
fi
[[ -f "$image" ]] || { echo "MISSING_NBF=$image"; exit 66; }

# mkdir is atomic, closing the race between two simultaneous SSH launchers.
mkdir "$lock" || { echo "ACTIVE_RUNNER"; exit 75; }
rm -f "$log" "$status" "$pidfile"
nohup bash -c '
  set +e
  log=$1
  status=$2
  lock=$3
  image=$4
  cd "$5" || exit 111
  if [[ -n "$6" ]]; then
    /usr/bin/script -qef -c "sudo -n ./control-program $image $6" "$log"
  else
    /usr/bin/script -qef -c "sudo -n ./control-program $image" "$log"
  fi
  rc=$?
  printf "RUNNER_EXIT=%s\\n" "$rc" > "$status"
  rm -f "$lock/owner"
  rmdir "$lock"
  exit "$rc"
' bash "$log" "$status" "$lock" "$image" "$PWD" "$runtime_limit_ms" </dev/null >"$HOME/bp-logs/$run_id.launch.log" 2>&1 &
runner_pid=$!
printf '%s\n' "$runner_pid" > "$lock/owner"
printf '%s\n' "$runner_pid" > "$pidfile"
printf 'RUNNER_STARTED_PID=%s LOG=%s STATUS=%s\n' "$runner_pid" "$log" "$status"
REMOTE
)
launch_rc=$?
set -e
printf '%s\n' "$launch_output"

start_line=$(grep '^RUNNER_STARTED_PID=' <<<"$launch_output" || true)
if [[ $launch_rc -ne 0 || -z "$start_line" ]]; then
  echo "FAIL: board refused serial launch" >&2
  [[ $launch_rc -ne 0 ]] && exit "$launch_rc"
  exit 1
fi

runner_pid=$(sed -n 's/^RUNNER_STARTED_PID=\([0-9][0-9]*\).*/\1/p' <<<"$start_line")
log=$(sed -n 's/^RUNNER_STARTED_PID=[0-9][0-9]* LOG=\([^ ]*\).*/\1/p' <<<"$start_line")
status=$(sed -n 's/.* STATUS=\([^ ]*\)$/\1/p' <<<"$start_line")

while true; do
  poll=$(ssh -o BatchMode=yes "$ssh_host" bash -s -- "$runner_pid" "$status" <<'REMOTE'
set -euo pipefail
runner_pid=$1
status=$2
if [[ -s "$status" ]]; then
  cat "$status"
  exit 0
fi
if kill -0 "$runner_pid" 2>/dev/null; then
  echo RUNNER_ACTIVE
  exit 0
fi
echo "RUNNER_LOST_WITHOUT_STATUS"
exit 1
REMOTE
) || {
    echo "FAIL: runner disappeared before writing its status" >&2
    exit 1
  }
  if [[ "$poll" == RUNNER_EXIT=* ]]; then
    printf '%s\n' "$poll"
    break
  fi
  sleep 2
done

ssh -o BatchMode=yes "$ssh_host" "tail -n 160 '$log'"
[[ "$poll" == "RUNNER_EXIT=0" ]]
