#!/usr/bin/env bash
# Validate the exact output contract of the focused BlackParrot seL4 RPC gate.

set -euo pipefail

physical=0
shared_buffer=0
components=0
lifecycle=0
smoke=0
fault_injection=0
caller_badge_expected=
while (($# > 1)); do
    case $1 in
        --physical) physical=1 ;;
        --shared-buffer) shared_buffer=1 ;;
        --components) components=1 ;;
        --lifecycle) lifecycle=1 ;;
        --smoke) smoke=1 ;;
        --fault-injection) fault_injection=1 ;;
        --caller-badge)
            (($# >= 3)) || break
            caller_badge_expected=$2
            shift
            ;;
        *) break ;;
    esac
    shift
done
if (($# != 1)); then
    echo "usage: $0 [--physical] [--shared-buffer] [--components] [--lifecycle] [--smoke] [--fault-injection] [--caller-badge DECIMAL] OUTPUT.log" >&2
    exit 2
fi
if [[ -n $caller_badge_expected ]] \
   && { [[ ! $caller_badge_expected =~ ^[0-9]+$ ]] \
        || ((caller_badge_expected == 0)); }; then
    echo "caller badge must be a nonzero decimal integer" >&2
    exit 2
fi

log=$1
marker='Test SEL4IPCRPC0002 passed'
hardware_re='^SEL4_RPC_ADAPTER path=hardware calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
software_re='^SEL4_RPC_ADAPTER path=software-fallback calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
direct_re='^SEL4_RPC_ADAPTER path=in-process calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
ipc_re='^SEL4_RPC_ADAPTER path=software calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
notification_re='^SEL4_RPC_ADAPTER path=notification calls=([0-9]+) total_cycles=([0-9]+) cycles_per_call=([0-9]+)$'
distribution_re='^SEL4_RPC_DISTRIBUTION path=(in-process|hardware|software|notification) samples=([0-9]+) min=([0-9]+) median=([0-9]+) p95=([0-9]+) max=([0-9]+)$'
cold_distribution_re='^SEL4_RPC_DISTRIBUTION path=l1d-cold/(in-process|hardware|software|notification) samples=([0-9]+) min=([0-9]+) median=([0-9]+) p95=([0-9]+) max=([0-9]+)$'
hierarchy_distribution_re='^SEL4_RPC_DISTRIBUTION path=data-hierarchy-cold/(in-process|hardware|software|notification) samples=([0-9]+) min=([0-9]+) median=([0-9]+) p95=([0-9]+) max=([0-9]+)$'
components_re='^SEL4_RPC_COMPONENTS path=(in-process|hardware|software|notification) samples=([0-9]+) pre_median=([0-9]+) service_median=([0-9]+) post_median=([0-9]+)$'
caller_badge_re='^SEL4_RPC_CALLER_BADGE value=([0-9]+) software=verified hardware=verified$'

test -r "$log" || { echo "unreadable simulator log: $log" >&2; exit 1; }

marker_count=0
hardware_count=0
software_count=0
core_pass_count=0
bsg_pass_count=0
bsg_fail_count=0
sel4_failure_count=0
workload_count=0
guard_count=0
direct_count=0
ipc_count=0
notification_count=0
notification_semantics_count=0
direct_distribution_count=0
hardware_distribution_count=0
software_distribution_count=0
notification_distribution_count=0
cold_state_count=0
direct_cold_distribution_count=0
hardware_cold_distribution_count=0
software_cold_distribution_count=0
notification_cold_distribution_count=0
hierarchy_state_count=0
direct_hierarchy_distribution_count=0
hardware_hierarchy_distribution_count=0
software_hierarchy_distribution_count=0
notification_hierarchy_distribution_count=0
direct_components_count=0
hardware_components_count=0
software_components_count=0
notification_components_count=0
timebase_count=0
caller_badge_count=0
lifecycle_count=0
fault_recovery_count=0

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
    elif [[ $line =~ $notification_re ]]; then
        notification_count=$((notification_count + 1))
        notification_calls=${BASH_REMATCH[1]}
        notification_total=${BASH_REMATCH[2]}
        notification_per_call=${BASH_REMATCH[3]}
    elif [[ $line =~ $distribution_re ]]; then
        distribution_path=${BASH_REMATCH[1]}
        distribution_samples=${BASH_REMATCH[2]}
        distribution_min=${BASH_REMATCH[3]}
        distribution_median=${BASH_REMATCH[4]}
        distribution_p95=${BASH_REMATCH[5]}
        distribution_max=${BASH_REMATCH[6]}
        case $distribution_path in
            in-process)
                direct_distribution_count=$((direct_distribution_count + 1))
                direct_distribution_samples=$distribution_samples
                direct_min=$distribution_min
                direct_median=$distribution_median
                direct_p95=$distribution_p95
                direct_max=$distribution_max
                ;;
            hardware)
                hardware_distribution_count=$((hardware_distribution_count + 1))
                hardware_distribution_samples=$distribution_samples
                hardware_min=$distribution_min
                hardware_median=$distribution_median
                hardware_p95=$distribution_p95
                hardware_max=$distribution_max
                ;;
            software)
                software_distribution_count=$((software_distribution_count + 1))
                software_distribution_samples=$distribution_samples
                software_min=$distribution_min
                software_median=$distribution_median
                software_p95=$distribution_p95
                software_max=$distribution_max
                ;;
            notification)
                notification_distribution_count=$((notification_distribution_count + 1))
                notification_distribution_samples=$distribution_samples
                notification_min=$distribution_min
                notification_median=$distribution_median
                notification_p95=$distribution_p95
                notification_max=$distribution_max
                ;;
        esac
    elif [[ $line =~ $cold_distribution_re ]]; then
        distribution_path=${BASH_REMATCH[1]}
        distribution_samples=${BASH_REMATCH[2]}
        distribution_min=${BASH_REMATCH[3]}
        distribution_median=${BASH_REMATCH[4]}
        distribution_p95=${BASH_REMATCH[5]}
        distribution_max=${BASH_REMATCH[6]}
        case $distribution_path in
            in-process)
                direct_cold_distribution_count=$((direct_cold_distribution_count + 1))
                direct_cold_samples=$distribution_samples
                direct_cold_min=$distribution_min
                direct_cold_median=$distribution_median
                direct_cold_p95=$distribution_p95
                direct_cold_max=$distribution_max
                ;;
            hardware)
                hardware_cold_distribution_count=$((hardware_cold_distribution_count + 1))
                hardware_cold_samples=$distribution_samples
                hardware_cold_min=$distribution_min
                hardware_cold_median=$distribution_median
                hardware_cold_p95=$distribution_p95
                hardware_cold_max=$distribution_max
                ;;
            software)
                software_cold_distribution_count=$((software_cold_distribution_count + 1))
                software_cold_samples=$distribution_samples
                software_cold_min=$distribution_min
                software_cold_median=$distribution_median
                software_cold_p95=$distribution_p95
                software_cold_max=$distribution_max
                ;;
            notification)
                notification_cold_distribution_count=$((notification_cold_distribution_count + 1))
                notification_cold_samples=$distribution_samples
                notification_cold_min=$distribution_min
                notification_cold_median=$distribution_median
                notification_cold_p95=$distribution_p95
                notification_cold_max=$distribution_max
                ;;
        esac
    elif [[ $line =~ $hierarchy_distribution_re ]]; then
        distribution_path=${BASH_REMATCH[1]}
        distribution_samples=${BASH_REMATCH[2]}
        distribution_min=${BASH_REMATCH[3]}
        distribution_median=${BASH_REMATCH[4]}
        distribution_p95=${BASH_REMATCH[5]}
        distribution_max=${BASH_REMATCH[6]}
        case $distribution_path in
            in-process)
                direct_hierarchy_distribution_count=$((direct_hierarchy_distribution_count + 1))
                direct_hierarchy_samples=$distribution_samples
                direct_hierarchy_min=$distribution_min
                direct_hierarchy_median=$distribution_median
                direct_hierarchy_p95=$distribution_p95
                direct_hierarchy_max=$distribution_max
                ;;
            hardware)
                hardware_hierarchy_distribution_count=$((hardware_hierarchy_distribution_count + 1))
                hardware_hierarchy_samples=$distribution_samples
                hardware_hierarchy_min=$distribution_min
                hardware_hierarchy_median=$distribution_median
                hardware_hierarchy_p95=$distribution_p95
                hardware_hierarchy_max=$distribution_max
                ;;
            software)
                software_hierarchy_distribution_count=$((software_hierarchy_distribution_count + 1))
                software_hierarchy_samples=$distribution_samples
                software_hierarchy_min=$distribution_min
                software_hierarchy_median=$distribution_median
                software_hierarchy_p95=$distribution_p95
                software_hierarchy_max=$distribution_max
                ;;
            notification)
                notification_hierarchy_distribution_count=$((notification_hierarchy_distribution_count + 1))
                notification_hierarchy_samples=$distribution_samples
                notification_hierarchy_min=$distribution_min
                notification_hierarchy_median=$distribution_median
                notification_hierarchy_p95=$distribution_p95
                notification_hierarchy_max=$distribution_max
                ;;
        esac
    elif [[ $line =~ $components_re ]]; then
        component_path=${BASH_REMATCH[1]}
        component_samples=${BASH_REMATCH[2]}
        component_pre=${BASH_REMATCH[3]}
        component_service=${BASH_REMATCH[4]}
        component_post=${BASH_REMATCH[5]}
        case $component_path in
            in-process)
                direct_components_count=$((direct_components_count + 1))
                direct_component_samples=$component_samples
                direct_pre_median=$component_pre
                direct_service_median=$component_service
                direct_post_median=$component_post
                ;;
            hardware)
                hardware_components_count=$((hardware_components_count + 1))
                hardware_component_samples=$component_samples
                hardware_pre_median=$component_pre
                hardware_service_median=$component_service
                hardware_post_median=$component_post
                ;;
            software)
                software_components_count=$((software_components_count + 1))
                software_component_samples=$component_samples
                software_pre_median=$component_pre
                software_service_median=$component_service
                software_post_median=$component_post
                ;;
            notification)
                notification_components_count=$((notification_components_count + 1))
                notification_component_samples=$component_samples
                notification_pre_median=$component_pre
                notification_service_median=$component_service
                notification_post_median=$component_post
                ;;
        esac
    elif [[ $line =~ $caller_badge_re ]]; then
        caller_badge_count=$((caller_badge_count + 1))
        caller_badge_actual=${BASH_REMATCH[1]}
    fi
    [[ $line == *"CORE PASS"* ]] && core_pass_count=$((core_pass_count + 1))
    [[ $line == *"BSG PASS"* ]] && bsg_pass_count=$((bsg_pass_count + 1))
    [[ $line == *"BSG FAIL"* ]] && bsg_fail_count=$((bsg_fail_count + 1))
    { [[ $line == "Test SEL4IPCRPC0002 failed" ]] \
      || [[ $line == "*** FAILURES DETECTED ***" ]]; } \
        && sel4_failure_count=$((sel4_failure_count + 1))
    [[ $line == "SEL4_RPC_WORKLOAD name=libc-bounded-search bytes=1024" ]] \
        && workload_count=$((workload_count + 1))
    [[ $line == "SEL4_RPC_REGION_GUARD physical-mismatch=denied write-escalation=denied runtime-state=denied" ]] \
        && guard_count=$((guard_count + 1))
    [[ $line == "SEL4_RPC_NOTIFICATION_BASELINE mailbox=shared-rw data-region=server-ro request-signal=notification reply-signal=notification" ]] \
        && notification_semantics_count=$((notification_semantics_count + 1))
    [[ $line == "SEL4_RPC_TIMEBASE counter=blackparrot-global-cycle-csr-0xcc0 scope=core-wide" ]] \
        && timebase_count=$((timebase_count + 1))
    [[ $line == "SEL4_RPC_CACHE_STATE kind=l1d-cold lower-cache=warm method=blackparrot-flush-all samples=64" ]] \
        && cold_state_count=$((cold_state_count + 1))
    [[ $line == "SEL4_RPC_CACHE_STATE kind=data-hierarchy-cold l1d=cold l2=cold l1i=warm dram-row=uncontrolled method=4x-l2-evict samples=64" ]] \
        && hierarchy_state_count=$((hierarchy_state_count + 1))
    [[ $line == "SEL4_RPC_LIFECYCLE map-revoke=verified stale-token=verified rebind=verified" ]] \
        && lifecycle_count=$((lifecycle_count + 1))
    [[ $line == "SEL4_RPC_FAULT_RECOVERY caller=server-fault retry=revoked record=consumed rebind=verified" ]] \
        && fault_recovery_count=$((fault_recovery_count + 1))
done < "$log"

if ((sel4_failure_count != 0)); then
    echo "seL4 failure marker present: rows=$sel4_failure_count" >&2
    exit 1
fi
if ((marker_count != 1 || hardware_count != 1 || software_count != 1)); then
    echo "invalid RPC evidence: markers=$marker_count hardware_rows=$hardware_count software_rows=$software_count" >&2
    exit 1
fi
expected_hardware_calls=256
expected_software_calls=8
if ((smoke)); then
    expected_hardware_calls=2
    expected_software_calls=1
fi
if ((hardware_calls != expected_hardware_calls
      || software_calls != expected_software_calls)); then
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
         || direct_count != 1 || ipc_count != 1
         || notification_count != 1 || notification_semantics_count != 1
         || direct_distribution_count != 1
         || hardware_distribution_count != 1
         || software_distribution_count != 1
         || notification_distribution_count != 1
         || cold_state_count != 1
         || direct_cold_distribution_count != 1
         || hardware_cold_distribution_count != 1
         || software_cold_distribution_count != 1
         || notification_cold_distribution_count != 1
         || hierarchy_state_count != 1
         || direct_hierarchy_distribution_count != 1
         || hardware_hierarchy_distribution_count != 1
         || software_hierarchy_distribution_count != 1
         || notification_hierarchy_distribution_count != 1)); then
        echo "invalid shared-buffer evidence: workload=$workload_count guards=$guard_count direct=$direct_count software=$ipc_count notification=$notification_count/$notification_semantics_count timebase=$timebase_count distributions=$direct_distribution_count/$hardware_distribution_count/$software_distribution_count/$notification_distribution_count cold=$cold_state_count:$direct_cold_distribution_count/$hardware_cold_distribution_count/$software_cold_distribution_count/$notification_cold_distribution_count hierarchy=$hierarchy_state_count:$direct_hierarchy_distribution_count/$hardware_hierarchy_distribution_count/$software_hierarchy_distribution_count/$notification_hierarchy_distribution_count" >&2
        exit 1
    fi
    if ((components)) && ((timebase_count != 1
         || direct_components_count != 1
         || hardware_components_count != 1
         || software_components_count != 1
         || notification_components_count != 1)); then
        echo "invalid component evidence: timebase=$timebase_count direct=$direct_components_count hardware=$hardware_components_count software=$software_components_count notification=$notification_components_count" >&2
        exit 1
    fi
    if ((components)) && ((direct_component_samples != 64
         || hardware_component_samples != 64
         || software_component_samples != 64
         || notification_component_samples != 64
         || direct_pre_median == 0 || direct_service_median == 0
         || direct_post_median == 0
         || hardware_pre_median == 0 || hardware_service_median == 0
         || hardware_post_median == 0
         || software_pre_median == 0 || software_service_median == 0
         || software_post_median == 0
         || notification_pre_median == 0
         || notification_service_median == 0
         || notification_post_median == 0)); then
        echo "invalid component accounting" >&2
        exit 1
    fi
    if ((direct_calls != 256 || ipc_calls != 256 || notification_calls != 256
         || direct_total == 0 || ipc_total == 0 || notification_total == 0
         || direct_per_call != direct_total / direct_calls
         || ipc_per_call != ipc_total / ipc_calls
         || notification_per_call != notification_total / notification_calls
         || direct_per_call >= hardware_per_call
         || hardware_per_call >= ipc_per_call)); then
        echo "invalid matched-path cycle accounting" >&2
        exit 1
    fi
    if ((direct_distribution_samples != 64
         || hardware_distribution_samples != 64
         || software_distribution_samples != 64
         || notification_distribution_samples != 64
         || direct_min > direct_median || direct_median > direct_p95
         || direct_p95 > direct_max
         || hardware_min > hardware_median || hardware_median > hardware_p95
         || hardware_p95 > hardware_max
         || software_min > software_median || software_median > software_p95
         || software_p95 > software_max
         || notification_min > notification_median
         || notification_median > notification_p95
         || notification_p95 > notification_max
         || direct_median >= hardware_median
         || hardware_median >= software_median)); then
        echo "invalid matched-path distribution" >&2
        exit 1
    fi
    if ((direct_cold_samples != 64
         || hardware_cold_samples != 64
         || software_cold_samples != 64
         || notification_cold_samples != 64
         || direct_cold_min > direct_cold_median
         || direct_cold_median > direct_cold_p95
         || direct_cold_p95 > direct_cold_max
         || hardware_cold_min > hardware_cold_median
         || hardware_cold_median > hardware_cold_p95
         || hardware_cold_p95 > hardware_cold_max
         || software_cold_min > software_cold_median
         || software_cold_median > software_cold_p95
         || software_cold_p95 > software_cold_max
         || notification_cold_min > notification_cold_median
         || notification_cold_median > notification_cold_p95
         || notification_cold_p95 > notification_cold_max)); then
        echo "invalid L1D-cold distribution" >&2
        exit 1
    fi
    if ((direct_hierarchy_samples != 64
         || hardware_hierarchy_samples != 64
         || software_hierarchy_samples != 64
         || notification_hierarchy_samples != 64
         || direct_hierarchy_min > direct_hierarchy_median
         || direct_hierarchy_median > direct_hierarchy_p95
         || direct_hierarchy_p95 > direct_hierarchy_max
         || hardware_hierarchy_min > hardware_hierarchy_median
         || hardware_hierarchy_median > hardware_hierarchy_p95
         || hardware_hierarchy_p95 > hardware_hierarchy_max
         || software_hierarchy_min > software_hierarchy_median
         || software_hierarchy_median > software_hierarchy_p95
         || software_hierarchy_p95 > software_hierarchy_max
         || notification_hierarchy_min > notification_hierarchy_median
         || notification_hierarchy_median > notification_hierarchy_p95
         || notification_hierarchy_p95 > notification_hierarchy_max)); then
        echo "invalid data-hierarchy-cold distribution" >&2
        exit 1
    fi
fi
if ((physical)) && ((core_pass_count != 1 || bsg_pass_count != 1 || bsg_fail_count != 0)); then
    echo "invalid physical completion: core_pass=$core_pass_count bsg_pass=$bsg_pass_count bsg_fail=$bsg_fail_count" >&2
    exit 1
fi
if [[ -n $caller_badge_expected ]] \
   && ((caller_badge_count != 1 || caller_badge_actual != caller_badge_expected)); then
    echo "invalid caller-badge evidence: rows=$caller_badge_count expected=$caller_badge_expected actual=${caller_badge_actual:-missing}" >&2
    exit 1
fi
if ((lifecycle)) && ((lifecycle_count != 1)); then
    echo "invalid lifecycle evidence: rows=$lifecycle_count" >&2
    exit 1
fi
if ((fault_injection)) && ((fault_recovery_count != 1)); then
    echo "invalid protected RPC fault-recovery evidence: rows=$fault_recovery_count" >&2
    exit 1
fi

printf 'accepted seL4 RPC gate: hardware=%s cycles/call software-fallback=%s cycles/call\n' \
    "$hardware_per_call" "$software_per_call"
if [[ -n $caller_badge_expected ]]; then
    printf 'authenticated caller badge: %s through software and hardware paths\n' \
        "$caller_badge_actual"
fi
if ((lifecycle)); then
    echo 'lifecycle revocation: map revoke, stale token rejection, and rebind verified'
fi
if ((fault_injection)); then
    echo 'fault recovery: server fault, terminal retry, record consumption, and rebind verified'
fi
if ((shared_buffer)); then
    printf 'matched warm paths: in-process=%s hardware=%s software=%s notification=%s cycles/call\n' \
        "$direct_per_call" "$hardware_per_call" "$ipc_per_call" "$notification_per_call"
    printf 'matched medians: in-process=%s hardware=%s software=%s notification=%s cycles/call\n' \
        "$direct_median" "$hardware_median" "$software_median" "$notification_median"
    printf 'L1D-cold medians: in-process=%s hardware=%s software=%s notification=%s cycles/call\n' \
        "$direct_cold_median" "$hardware_cold_median" "$software_cold_median" "$notification_cold_median"
    printf 'data-hierarchy-cold medians: in-process=%s hardware=%s software=%s notification=%s cycles/call\n' \
        "$direct_hierarchy_median" "$hardware_hierarchy_median" "$software_hierarchy_median" "$notification_hierarchy_median"
    if ((components)); then
        printf 'warm components (pre/service/post): direct=%s/%s/%s hardware=%s/%s/%s software=%s/%s/%s notification=%s/%s/%s cycles\n' \
            "$direct_pre_median" "$direct_service_median" "$direct_post_median" \
            "$hardware_pre_median" "$hardware_service_median" "$hardware_post_median" \
            "$software_pre_median" "$software_service_median" "$software_post_median" \
            "$notification_pre_median" "$notification_service_median" "$notification_post_median"
    fi
fi
