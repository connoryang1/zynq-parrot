#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: $0 <ssh-host>" >&2
  exit 2
}

ssh_host=$1
expected_bit_sha=${PYNQ_BITSTREAM_SHA256:-}
[[ -z "$expected_bit_sha" || "$expected_bit_sha" =~ ^[0-9a-fA-F]{64}$ ]] || {
  echo "FAIL: PYNQ_BITSTREAM_SHA256 must be a 64-character SHA-256" >&2
  exit 2
}
load_ok=0
for attempt in 1 2; do
  # Programming the PL can briefly interrupt the board's network stack.  The
  # remote helper prints its success marker before that interruption, so keep
  # and validate its output even when ssh observes a late disconnect.
  output=''
  if output=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_host" bash -s <<'REMOTE'
set -euo pipefail
mkdir -p "$HOME/bp-logs"
lock="$HOME/bp-logs/.control-program.lock"
if [[ -d "$lock" ]]; then
  owner=$(cat "$lock/owner" 2>/dev/null || true)
  if [[ "$owner" =~ ^[0-9]+$ ]] && kill -0 "$owner" 2>/dev/null; then
    echo ACTIVE_RUNNER
    exit 75
  fi
  if pgrep -x control-program >/dev/null \
     || pgrep -f '[s]cript .*control-program' >/dev/null; then
    echo ACTIVE_RUNNER
    exit 75
  fi
  rm -f "$lock/owner"
  rmdir "$lock" || { echo ACTIVE_RUNNER; exit 75; }
fi
if pgrep -x control-program >/dev/null \
   || pgrep -f '[s]cript .*control-program' >/dev/null; then
  echo ACTIVE_RUNNER
  exit 75
fi
mkdir "$lock" || { echo ACTIVE_RUNNER; exit 75; }
printf '%s\n' "$$" > "$lock/owner"
cleanup() { rm -f "$lock/owner"; rmdir "$lock" 2>/dev/null || true; }
trap cleanup EXIT HUP INT TERM
sudo -n /usr/local/sbin/load-blackparrot-overlay
REMOTE
  ); then
    :
  fi
  printf '%s\n' "$output"
  if grep -qx 'ACTIVE_RUNNER' <<<"$output"; then
    echo "FAIL: refusing to reload the overlay while a runner owns the board" >&2
    exit 75
  fi
  if grep -qx 'OVERLAY_LOAD_OK=1' <<<"$output"; then
    loaded_sha=$(sed -n 's/^LOADING_BIT_SHA256=//p' <<<"$output")
    if [[ -n "$expected_bit_sha" && "$loaded_sha" != "$expected_bit_sha" ]]; then
      echo "FAIL: overlay SHA mismatch: expected=$expected_bit_sha actual=$loaded_sha" >&2
      exit 1
    fi
    load_ok=1
    break
  fi
  (( attempt < 2 )) && sleep 2
done

(( load_ok == 1 )) || {
  echo "FAIL: overlay helper did not report success" >&2
  exit 1
}

fpga_state=''
deadline=$((SECONDS + 30))
while (( SECONDS < deadline )); do
  if fpga_state=$(ssh -o BatchMode=yes -o ConnectTimeout=3 "$ssh_host" \
      'cat /sys/class/fpga_manager/fpga0/state' 2>/dev/null) \
      && [[ "$fpga_state" == operating ]]; then
    break
  fi
  sleep 1
done
printf 'REMOTE_FPGA_STATE=%s\n' "$fpga_state"
[[ "$fpga_state" == operating ]] || {
  echo "FAIL: FPGA manager is not operating after overlay load" >&2
  exit 1
}

echo "REMOTE_FPGA_STATE_OK=1"
echo "REMOTE_OVERLAY_LOAD_OK=1"
