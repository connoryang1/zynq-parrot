#!/usr/bin/env bash
set -euo pipefail

kind=${1:?report kind required}
vivado_dir=${2:?Vivado directory required}

first_sorted_match() {
  local pattern=$1
  find "$vivado_dir" -type f -name "$pattern" -print 2>/dev/null | LC_ALL=C sort | head -n 1
}

case "$kind" in
  timing)
    # Vivado can retain the timing report from route_design after a later
    # post-route phys_opt_design fixes timing.  The post-optimization report
    # describes the checkpoint used by write_bitstream and is authoritative.
    report=$(first_sorted_match '*timing_summary_postroute_physopted.rpt')
    [[ -n "$report" ]] || report=$(first_sorted_match '*timing_summary_routed.rpt')
    ;;
  utilization)
    # Use the implemented design's placed utilization.  In particular, avoid
    # matching clock_utilization_routed.rpt as a generic utilization report.
    report=$(first_sorted_match '*_utilization_placed.rpt')
    if [[ -z "$report" ]]; then
      report=$(find "$vivado_dir" -type f -name '*_utilization_routed.rpt' \
        ! -name '*_clock_utilization_routed.rpt' -print 2>/dev/null \
        | LC_ALL=C sort | head -n 1)
    fi
    ;;
  *)
    echo "Unknown report kind: $kind" >&2
    exit 2
    ;;
esac

[[ -z "$report" ]] || printf '%s\n' "$report"
