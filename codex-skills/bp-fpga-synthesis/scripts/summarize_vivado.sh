#!/usr/bin/env bash
set -euo pipefail

vivado_dir=${1:-.}
timing=$(find "$vivado_dir" -type f -name '*timing_summary_routed.rpt' -print -quit 2>/dev/null || true)
util=$(find "$vivado_dir" -type f \( -name '*utilization*placed*.rpt' -o -name '*utilization*routed*.rpt' -o -name '*utilization*.rpt' \) -print -quit 2>/dev/null || true)

echo "Vivado directory: $vivado_dir"
if [[ -n "$timing" ]]; then
  echo "Timing report: $timing"
  grep -m 1 -A 3 'WNS(ns)' "$timing" || grep -m 1 -A 3 'WNS' "$timing" || true
else
  echo "Timing report: MISSING"
fi

if [[ -n "$util" ]]; then
  echo "Utilization report: $util"
  grep -E '^\| *(Slice LUTs|Slice Registers|Block RAM Tile|RAMB36|RAMB18|DSPs|DSP48)' "$util" || true
else
  echo "Utilization report: MISSING"
fi

echo "Artifacts:"
{ find "$vivado_dir" -maxdepth 2 -type f \( -name '*.bit' -o -name '*.hwh' -o -name '*.map' -o -name '*.tar.xz.b64' \) -printf '%s %p\n' 2>/dev/null || true; } | sort -n
