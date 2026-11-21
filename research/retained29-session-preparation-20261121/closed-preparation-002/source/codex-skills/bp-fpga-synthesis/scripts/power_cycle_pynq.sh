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
pl_boot_timeout_seconds=${PYNQ_PL_BOOT_TIMEOUT_SECONDS:-90}

for value_name in off_seconds boot_timeout_seconds poll_seconds pl_boot_timeout_seconds; do
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
    break
  fi
  sleep "$poll_seconds"
done

(( SECONDS < deadline )) || {
  echo "error: board SSH did not return within ${boot_timeout_seconds}s" >&2
  exit 1
}

# On this PYNQ image, sshd comes up before the PYNQ PL manager.  Reloading an
# overlay during that window can leave the board unreachable even though SSH
# was briefly available.  Wait for its service process, not just the network.
echo "Waiting for the PYNQ PL manager"
pl_deadline=$((SECONDS + pl_boot_timeout_seconds))
while (( SECONDS < pl_deadline )); do
  if ssh -o BatchMode=yes -o ConnectTimeout=2 "$ssh_host" \
      "ps -eo args | grep -q '[s]tart_pl_server.py'" 2>/dev/null; then
    echo "PYNQ PL manager is ready: $ssh_host"
    echo "Reload and verify the intended BlackParrot overlay before testing."
    exit 0
  fi
  sleep "$poll_seconds"
done

echo "error: PYNQ PL manager did not return within ${pl_boot_timeout_seconds}s" >&2
exit 1
