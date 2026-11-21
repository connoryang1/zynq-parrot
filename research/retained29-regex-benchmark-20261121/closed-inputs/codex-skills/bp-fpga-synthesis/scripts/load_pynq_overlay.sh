#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: $0 <ssh-host>" >&2
  exit 2
}

ssh_host=$1
load_ok=0
for attempt in 1 2; do
  # Programming the PL can briefly interrupt the board's network stack.  The
  # remote helper prints its success marker before that interruption, so keep
  # and validate its output even when ssh observes a late disconnect.
  output=''
  if output=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_host" \
      'sudo -n /usr/local/sbin/load-blackparrot-overlay'); then
    :
  fi
  printf '%s\n' "$output"
  if grep -qx 'OVERLAY_LOAD_OK=1' <<<"$output"; then
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
