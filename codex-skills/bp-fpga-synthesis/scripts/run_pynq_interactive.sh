#!/usr/bin/env bash
# Open one hash-verified, serialized interactive BlackParrot console session.
# Invoke this from a real terminal (or an allocated PTY) so guest shell input
# reaches control-program without bypassing the board lock.
set -euo pipefail

[[ $# -eq 2 ]] || { echo "usage: $0 <ssh-host> <program.nbf>" >&2; exit 2; }
ssh_host=$1
local_nbf=$2
image=$(basename -- "$local_nbf")
runtime_limit_ms=${PYNQ_CONTROL_PROGRAM_TIMEOUT_MS:-300000}
expected_runner_sha=${PYNQ_CONTROL_PROGRAM_SHA256:-}

[[ "$image" =~ ^[A-Za-z0-9._-]+\.nbf$ ]] || { echo "unsafe NBF name" >&2; exit 2; }
[[ "$runtime_limit_ms" =~ ^[1-9][0-9]*$ ]] || { echo "invalid runtime limit" >&2; exit 2; }
[[ "$expected_runner_sha" =~ ^[0-9a-fA-F]{64}$ ]] || {
  echo "PYNQ_CONTROL_PROGRAM_SHA256 is required" >&2
  exit 2
}
[[ -t 0 && -t 1 ]] || { echo "interactive runner requires a PTY" >&2; exit 2; }

expected_nbf_sha=$(sha256sum "$local_nbf" | awk '{print $1}')
remote_dir='~/zynq-parrot/cosim/black-parrot-example/zynq'
remote_nbf_sha=$(ssh -o BatchMode=yes "$ssh_host" \
  "cd $remote_dir && sha256sum '$image'" | awk '{print $1}')
[[ "$remote_nbf_sha" == "$expected_nbf_sha" ]] || {
  echo "remote NBF SHA mismatch" >&2
  exit 1
}

exec ssh -tt -o BatchMode=yes "$ssh_host" \
  "$remote_dir/run-blackparrot-interactive '$image' '$expected_nbf_sha' '$expected_runner_sha' '$runtime_limit_ms'"
