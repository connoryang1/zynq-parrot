#!/usr/bin/env bash
# Validate the exact output contract of the focused BlackParrot seL4 RPC gate.

set -euo pipefail

if (($# != 1)); then
    echo "usage: $0 OUTPUT.log" >&2
    exit 2
fi

log=$1
marker='Test SEL4IPCRPC0002 passed'
hardware_re='^SEL4_RPC_ADAPTER path=hardware calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
software_re='^SEL4_RPC_ADAPTER path=software-fallback calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'

test -r "$log" || { echo "unreadable simulator log: $log" >&2; exit 1; }

marker_count=0
hardware_count=0
software_count=0

while IFS= read -r line; do
    if [[ $line == "$marker" ]]; then
        marker_count=$((marker_count + 1))
    elif [[ $line =~ $hardware_re ]]; then
        hardware_count=$((hardware_count + 1))
        hardware_calls=${BASH_REMATCH[1]}
        hardware_total=${BASH_REMATCH[2]}
        hardware_per_call=${BASH_REMATCH[3]}
    elif [[ $line =~ $software_re ]]; then
        software_count=$((software_count + 1))
        software_calls=${BASH_REMATCH[1]}
        software_total=${BASH_REMATCH[2]}
        software_per_call=${BASH_REMATCH[3]}
    fi
done < "$log"

if ((marker_count != 1 || hardware_count != 1 || software_count != 1)); then
    echo "invalid RPC evidence: markers=$marker_count hardware_rows=$hardware_count software_rows=$software_count" >&2
    exit 1
fi
if ((hardware_calls != 256 || software_calls != 8)); then
    echo "unexpected RPC call counts: hardware=$hardware_calls software=$software_calls" >&2
    exit 1
fi
if ((hardware_total == 0 || software_total == 0
      || hardware_per_call != hardware_total / hardware_calls
      || software_per_call != software_total / software_calls)); then
    echo "invalid RPC cycle accounting" >&2
    exit 1
fi

printf 'accepted seL4 RPC gate: hardware=%s cycles/call software-fallback=%s cycles/call\n' \
    "$hardware_per_call" "$software_per_call"
