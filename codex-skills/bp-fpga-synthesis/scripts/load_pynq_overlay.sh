#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: $0 <ssh-host>" >&2
  exit 2
}

ssh_host=$1
output=$(ssh -o BatchMode=yes "$ssh_host" \
  'sudo -n /usr/local/sbin/load-blackparrot-overlay')
printf '%s\n' "$output"

grep -qx 'OVERLAY_LOAD_OK=1' <<<"$output" || {
  echo "FAIL: overlay helper did not report success" >&2
  exit 1
}

echo "REMOTE_OVERLAY_LOAD_OK=1"
