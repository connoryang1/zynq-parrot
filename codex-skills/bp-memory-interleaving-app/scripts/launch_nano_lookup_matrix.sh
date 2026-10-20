#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
artifact_root=${1:-"$repo_root/logs/nano-lookup-$(date -u +%Y%m%dT%H%M%SZ)"}
runner="$repo_root/codex-skills/bp-memory-interleaving-app/scripts/run_nano_lookup_matrix.sh"
mkdir -p "$artifact_root"
artifact_root=$(realpath "$artifact_root")

nohup "$runner" "$artifact_root" > "$artifact_root/background.log" 2>&1 &
pid=$!
echo "$pid" > "$artifact_root/background.pid"
echo "launched PID $pid; monitor $artifact_root/background.log"
