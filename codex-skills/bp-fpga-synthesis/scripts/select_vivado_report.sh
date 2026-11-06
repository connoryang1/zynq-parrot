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
    # The post-optimization report describes the checkpoint used by
    # write_bitstream.  A retained route_design report may still be negative.
    report=$(first_sorted_match '*timing_summary_postroute_physopted.rpt')
    [[ -n "$report" ]] || report=$(first_sorted_match '*timing_summary_routed.rpt')
    ;;
  utilization)
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
