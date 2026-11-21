#!/usr/bin/env bash
# Wait for a power-cycled PYNQ-Z2 to finish its own Linux/PYNQ startup before
# loading an overlay. SSH becomes reachable well before boot.py and systemd are
# settled; loading the PL during that interval makes FPGA test evidence unreliable.
set -euo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: $0 <ssh-host>" >&2
  exit 2
}

ssh_host=$1
min_uptime_s=${PYNQ_READY_MIN_UPTIME_S:-90}
timeout_s=${PYNQ_READY_TIMEOUT_S:-240}
poll_s=${PYNQ_READY_POLL_S:-5}

for value in "$min_uptime_s" "$timeout_s" "$poll_s"; do
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || {
    echo "PYNQ readiness values must be positive integers" >&2
    exit 2
  }
done

deadline=$(( $(date +%s) + timeout_s ))
while (( $(date +%s) < deadline )); do
  set +e
  probe=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_host" '
    uptime_s=$(awk "{print int(\$1)}" /proc/uptime)
    if journalctl -b --no-pager -o cat 2>/dev/null | grep -Fq "Startup finished"; then
      startup_finished=1
    else
      startup_finished=0
    fi
    printf "uptime_s=%s startup_finished=%s\n" "$uptime_s" "$startup_finished"
  ' 2>/dev/null)
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    uptime_s=$(sed -n 's/.*uptime_s=\([0-9][0-9]*\).*/\1/p' <<<"$probe")
    startup_finished=$(sed -n 's/.*startup_finished=\([01]\).*/\1/p' <<<"$probe")
    if [[ -n "$uptime_s" && "$uptime_s" -ge "$min_uptime_s" && "$startup_finished" == 1 ]]; then
      printf 'PYNQ_READY_OK=1\nPYNQ_UPTIME_S=%s\n' "$uptime_s"
      exit 0
    fi
  fi
  sleep "$poll_s"
done

echo "PYNQ_READY_TIMEOUT after ${timeout_s}s for $ssh_host" >&2
exit 1
