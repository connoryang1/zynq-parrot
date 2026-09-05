#!/usr/bin/env bash
# Install the reviewed user-owned interactive serialization helper on a PYNQ.
# The helper does not expand sudo authority and always runs from the fixed
# BlackParrot board checkout.
set -euo pipefail

[[ $# -eq 1 ]] || { echo "usage: $0 <ssh-host>" >&2; exit 2; }
ssh_host=$1
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source_file="$script_dir/board_run_pynq_interactive.sh"
source_sha=$(sha256sum "$source_file" | awk '{print $1}')
remote_tmp=".run-blackparrot-interactive.incoming-$$"
remote_path="/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/run-blackparrot-interactive"

scp -o BatchMode=yes -- "$source_file" "$ssh_host:$remote_tmp"
ssh -o BatchMode=yes "$ssh_host" \
  "test \"\$(sha256sum $remote_tmp | awk '{print \$1}')\" = '$source_sha' && install -m 0755 $remote_tmp '$remote_path' && rm -f $remote_tmp"
remote_sha=$(ssh -o BatchMode=yes "$ssh_host" "sha256sum '$remote_path'" | awk '{print $1}')
[[ "$remote_sha" == "$source_sha" ]] || { echo "interactive helper SHA mismatch" >&2; exit 1; }
echo "PYNQ_INTERACTIVE_RUNNER_OK=1"
echo "PYNQ_INTERACTIVE_RUNNER_SHA256=$remote_sha"
