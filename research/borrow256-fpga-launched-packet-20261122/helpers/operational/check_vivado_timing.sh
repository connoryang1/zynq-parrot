#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -s "$1" ]]; then
  echo "usage: $0 <timing-summary-routed.rpt>" >&2
  exit 2
fi

row=$(awk '
  /^[[:space:]]*WNS\(ns\)/ {
    getline
    getline
    print
    exit
  }
' "$1")
read -r wns _ <<<"$row"
if [[ ! "${wns:-}" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
  echo "Unable to parse routed WNS from $1" >&2
  exit 2
fi

printf 'WNS_NS=%s\n' "$wns"
if ! awk -v value="$wns" 'BEGIN { exit !(value >= 0) }'; then
  echo "Routed timing failed: WNS=${wns} ns" >&2
  exit 1
fi

