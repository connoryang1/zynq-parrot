#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: PYNQ_POWER_STATE_URL=<private-url> $0 <ssh-host>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
[[ -n "${PYNQ_POWER_STATE_URL:-}" ]] || {
  echo "error: PYNQ_POWER_STATE_URL is required" >&2
  exit 2
}

ssh_host=$1
off_seconds=${PYNQ_POWER_OFF_SECONDS:-3}
boot_timeout_seconds=${PYNQ_BOOT_TIMEOUT_SECONDS:-120}
poll_seconds=${PYNQ_BOOT_POLL_SECONDS:-2}

for value_name in off_seconds boot_timeout_seconds poll_seconds; do
  value=${!value_name}
  [[ $value =~ ^[1-9][0-9]*$ ]] || {
    echo "error: $value_name must be a positive integer" >&2
    exit 2
  }
done

echo "Powering off the PYNQ outlet"
curl -fsS -X PUT "$PYNQ_POWER_STATE_URL" \
  -H 'Content-Type: application/json' -d '{"on":false}' >/dev/null
sleep "$off_seconds"

echo "Powering on the PYNQ outlet"
curl -fsS -X PUT "$PYNQ_POWER_STATE_URL" \
  -H 'Content-Type: application/json' -d '{"on":true}' >/dev/null

deadline=$((SECONDS + boot_timeout_seconds))
while (( SECONDS < deadline )); do
  if ssh -o BatchMode=yes -o ConnectTimeout=2 "$ssh_host" true 2>/dev/null; then
    echo "Board SSH is reachable: $ssh_host"
    echo "Reload and verify the intended BlackParrot overlay before testing."
    exit 0
  fi
  sleep "$poll_seconds"
done

echo "error: board SSH did not return within ${boot_timeout_seconds}s" >&2
exit 1
