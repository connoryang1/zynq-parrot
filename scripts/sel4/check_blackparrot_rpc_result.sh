#!/usr/bin/env bash
# Validate the exact output contract of the focused BlackParrot seL4 RPC gate.

set -euo pipefail

physical=0
shared_buffer=0
while (($# > 1)); do
    case $1 in
        --physical) physical=1 ;;
        --shared-buffer) shared_buffer=1 ;;
        *) break ;;
    esac
    shift
done
if (($# != 1)); then
    echo "usage: $0 [--physical] [--shared-buffer] OUTPUT.log" >&2
    exit 2
fi

log=$1
marker='Test SEL4IPCRPC0002 passed'
hardware_re='^SEL4_RPC_ADAPTER path=hardware calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
software_re='^SEL4_RPC_ADAPTER path=software-fallback calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
direct_re='^SEL4_RPC_ADAPTER path=in-process calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
ipc_re='^SEL4_RPC_ADAPTER path=software calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'

test -r "$log" || { echo "unreadable simulator log: $log" >&2; exit 1; }

marker_count=0
hardware_count=0
software_count=0
core_pass_count=0
bsg_pass_count=0
bsg_fail_count=0
workload_count=0
guard_count=0
direct_count=0
ipc_count=0

while IFS= read -r line; do
    # A UART or nested PTY may preserve CRLF as either CRLF or CRCRLF.  Strip
    # only trailing carriage returns; do not otherwise normalize evidence.
    while [[ $line == *$'\r' ]]; do
        line=${line%$'\r'}
    done
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
    elif [[ $line =~ $direct_re ]]; then
        direct_count=$((direct_count + 1))
        direct_calls=${BASH_REMATCH[1]}
        direct_total=${BASH_REMATCH[2]}
        direct_per_call=${BASH_REMATCH[3]}
    elif [[ $line =~ $ipc_re ]]; then
        ipc_count=$((ipc_count + 1))
        ipc_calls=${BASH_REMATCH[1]}
        ipc_total=${BASH_REMATCH[2]}
        ipc_per_call=${BASH_REMATCH[3]}
    fi
    [[ $line == *"CORE PASS"* ]] && core_pass_count=$((core_pass_count + 1))
    [[ $line == *"BSG PASS"* ]] && bsg_pass_count=$((bsg_pass_count + 1))
    [[ $line == *"BSG FAIL"* ]] && bsg_fail_count=$((bsg_fail_count + 1))
    [[ $line == "SEL4_RPC_WORKLOAD name=libc-bounded-search bytes=1024" ]] \
        && workload_count=$((workload_count + 1))
    [[ $line == "SEL4_RPC_REGION_GUARD physical-mismatch=denied write-escalation=denied runtime-state=denied" ]] \
        && guard_count=$((guard_count + 1))
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
      || software_per_call != software_total / software_calls
      || hardware_per_call >= software_per_call)); then
    echo "invalid RPC cycle accounting" >&2
    exit 1
fi
if ((shared_buffer)); then
    if ((workload_count != 1 || guard_count != 1
         || direct_count != 1 || ipc_count != 1)); then
        echo "invalid shared-buffer evidence: workload=$workload_count guards=$guard_count direct=$direct_count software=$ipc_count" >&2
        exit 1
    fi
    if ((direct_calls != 256 || ipc_calls != 256
         || direct_total == 0 || ipc_total == 0
         || direct_per_call != direct_total / direct_calls
         || ipc_per_call != ipc_total / ipc_calls
         || direct_per_call >= hardware_per_call
         || hardware_per_call >= ipc_per_call)); then
        echo "invalid matched-path cycle accounting" >&2
        exit 1
    fi
fi
if ((physical)) && ((core_pass_count != 1 || bsg_pass_count != 1 || bsg_fail_count != 0)); then
    echo "invalid physical completion: core_pass=$core_pass_count bsg_pass=$bsg_pass_count bsg_fail=$bsg_fail_count" >&2
    exit 1
fi

printf 'accepted seL4 RPC gate: hardware=%s cycles/call software-fallback=%s cycles/call\n' \
    "$hardware_per_call" "$software_per_call"
if ((shared_buffer)); then
    printf 'matched warm paths: in-process=%s hardware=%s software=%s cycles/call\n' \
        "$direct_per_call" "$hardware_per_call" "$ipc_per_call"
fi
