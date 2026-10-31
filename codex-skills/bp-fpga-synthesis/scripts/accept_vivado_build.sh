#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
vivado_dir=${1:?Vivado directory required}
example_dir=${2:?example directory required}
job_dir=${3:?job directory required}

"$script_dir/summarize_vivado.sh" "$vivado_dir" >"$job_dir/summary.txt"
timing=$("$script_dir/select_vivado_report.sh" timing "$vivado_dir")
util=$("$script_dir/select_vivado_report.sh" utilization "$vivado_dir")

for required in \
  "$vivado_dir/black_parrot_bd_1.bit" \
  "$vivado_dir/black_parrot_bd_1.hwh" \
  "$vivado_dir/black_parrot_bd_1.map" \
  "$timing" "$util"; do
  if [[ -z "$required" || ! -s "$required" ]]; then
    echo "Missing routed acceptance artifact: ${required:-<report not found>}" >&2
    exit 1
  fi
done

# Vivado writes a bitstream and exits successfully even when routed setup
# timing is violated. Reject a package unless the report for the checkpoint
# used by write_bitstream has nonnegative WNS.
"$script_dir/check_vivado_timing.sh" "$timing"

packed=$(find "$example_dir" -maxdepth 1 -type f -name '*.tar.xz.b64' -print 2>/dev/null \
  | LC_ALL=C sort | head -n 1)
if [[ -z "$packed" || ! -s "$packed" ]]; then
  echo "Missing packed bitstream artifact." >&2
  exit 1
fi
cp -p "$packed" "$job_dir/"
