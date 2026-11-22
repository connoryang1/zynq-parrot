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
