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
# The Linux image is coupled to the host-side control-program protocol as well
# as the bitstream.  A caller may pin the expected runner hash so an accidental
# replacement cannot masquerade as an RTL regression.  The board sudo rule
# deliberately still names only ./control-program; selecting a reviewed
# archived runner therefore happens explicitly before launch.
expected_runner_sha=${PYNQ_CONTROL_PROGRAM_SHA256:-}
[[ -z "$expected_runner_sha" || "$expected_runner_sha" =~ ^[0-9a-fA-F]{64}$ ]] || {
  echo "FAIL: PYNQ_CONTROL_PROGRAM_SHA256 must be a 64-character SHA-256" >&2
  exit 2
}
# A full-width register-state terminal probe writes into a fixed DRAM scratch
# area, then asks ps.cpp to dump that bounded range after the target stops.
# Keep the sole optional control-program argument syntactically narrow: this
# helper is also the board's concurrency and sudo boundary.
extra_arg=${PYNQ_CONTROL_PROGRAM_EXTRA_ARG:-}
[[ -z "$extra_arg" || "$extra_arg" =~ ^--state-dump=0x[0-9A-Fa-f]+:[1-9][0-9]*$ ]] || {
  echo "FAIL: PYNQ_CONTROL_PROGRAM_EXTRA_ARG supports only --state-dump=0xOFFSET:WORDS" >&2
  exit 2
}
foreground=${PYNQ_CONTROL_PROGRAM_FOREGROUND:-0}
[[ "$foreground" == 0 || "$foreground" == 1 ]] || {
  echo "FAIL: PYNQ_CONTROL_PROGRAM_FOREGROUND must be 0 or 1" >&2
  exit 2
}
[[ "$image" =~ ^[A-Za-z0-9._-]+\.nbf$ ]] || {
  echo "FAIL: program must be a simple .nbf filename" >&2
  exit 2
}

run_id="${image%.nbf}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
expected_sha=$(sha256sum "$2" | awk '{print $1}')

set +e
# OpenSSH serializes the remote command as text and drops a trailing empty
# argument.  Preserve "no target runtime limit" explicitly so the remote
# script always receives its required fourth parameter.
remote_timeout_arg=${runtime_limit_ms:--}
# SSH drops an empty trailing positional parameter when it serializes the
# remote command.  Encode the optional argument explicitly so foreground is
# never shifted out of the remote script's argument vector.
remote_extra_arg=${extra_arg:--}
launch_output=$(ssh -o BatchMode=yes "$ssh_host" bash -s -- "$remote_dir" "$image" "$run_id" "$remote_timeout_arg" "$expected_sha" "$remote_extra_arg" "$foreground" "$expected_runner_sha" <<'REMOTE'
set -euo pipefail
remote_dir=$1
image=$2
run_id=$3
runtime_limit_ms=$4
expected_sha=$5
extra_arg=$6
foreground=$7
expected_runner_sha=$8
[[ "$runtime_limit_ms" == '-' ]] && runtime_limit_ms=
[[ "$extra_arg" == '-' ]] && extra_arg=
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
actual_sha=$(sha256sum "$image" | awk '{print $1}')
[[ "$actual_sha" == "$expected_sha" ]] || {
  echo "NBF_SHA_MISMATCH=$image expected=$expected_sha actual=$actual_sha"
  exit 65
}
actual_runner_sha=$(sha256sum ./control-program | awk '{print $1}')
if [[ -n "$expected_runner_sha" && "$actual_runner_sha" != "$expected_runner_sha" ]]; then
  echo "CONTROL_PROGRAM_SHA_MISMATCH expected=$expected_runner_sha actual=$actual_runner_sha"
  exit 64
fi
echo "CONTROL_PROGRAM_SHA256=$actual_runner_sha"

# mkdir is atomic, closing the race between two simultaneous SSH launchers.
mkdir "$lock" || { echo "ACTIVE_RUNNER"; exit 75; }
rm -f "$log" "$status" "$pidfile"
if [[ "$foreground" == 1 ]]; then
  # A foreground diagnostic is resilient to PYNQ's SSH-session child reaper.
  # It still retains the same transcript, lock, and completion status as the
  # detached path, but is preferable for a short state-capture probe.
  printf 'RUNNER_STARTED_PID=%s LOG=%s STATUS=%s\n' "$$" "$log" "$status"
  command=(sudo -n ./control-program "$image")
  [[ -n "$runtime_limit_ms" ]] && command+=("$runtime_limit_ms")
  [[ -n "$extra_arg" ]] && command+=("$extra_arg")
  printf -v command_text '%q ' "${command[@]}"
  set +e
  # The remote wrapper itself arrives on bash's stdin through an SSH heredoc.
  # Do not let an interactive guest consume the unread remainder as console
  # input after it reaches /init.
  /usr/bin/script -qef -c "$command_text" "$log" </dev/null
  rc=$?
  set -e
  printf 'RUNNER_EXIT=%s\n' "$rc" > "$status"
  rmdir "$lock"
  exit "$rc"
fi
nohup setsid --wait env RUN_LOG="$log" RUN_STATUS="$status" RUN_LOCK="$lock" \
  RUN_IMAGE="$image" RUN_DIRECTORY="$PWD" RUN_TIMEOUT="$runtime_limit_ms" \
  RUN_EXTRA="$extra_arg" bash -c '
  set +e
  cd "$RUN_DIRECTORY" || exit 111
  command=(sudo -n ./control-program "$RUN_IMAGE")
  [[ -n "$RUN_TIMEOUT" ]] && command+=("$RUN_TIMEOUT")
  [[ -n "$RUN_EXTRA" ]] && command+=("$RUN_EXTRA")
  printf -v command_text '%q ' "${command[@]}"
  /usr/bin/script -qef -c "$command_text" "$RUN_LOG"
  rc=$?
  printf "RUNNER_EXIT=%s\\n" "$rc" > "$RUN_STATUS"
  rm -f "$RUN_LOCK/owner"
  rmdir "$RUN_LOCK"
  exit "$rc"
' </dev/null >"$HOME/bp-logs/$run_id.launch.log" 2>&1 &
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
# A foreground run keeps the SSH session attached to control-program.  Its
# target result is consequently also the SSH result (for example 124 after a
# deliberate target-runtime limit).  Once the remote side has emitted the
# atomic start record, retain and report that completed run below instead of
# mislabeling it as a failed launch.  A nonzero launch without that record is
# still a genuine pre-launch failure.
if [[ -z "$start_line" ]]; then
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
