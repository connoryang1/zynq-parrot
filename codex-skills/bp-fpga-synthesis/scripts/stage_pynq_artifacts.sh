#!/usr/bin/env bash
set -euo pipefail

[[ $# -ge 2 ]] || {
  echo "usage: $0 <package.tar.xz.b64> <ssh-host> [program.nbf ...]" >&2
  exit 2
}

package=$1
ssh_host=$2
shift 2

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
remote_example_dir=${PYNQ_REMOTE_EXAMPLE_DIR:-'~/zynq-parrot/cosim/black-parrot-example'}
remote_zynq_dir="$remote_example_dir/zynq"

verify_output=$($script_dir/verify_pynq_package.sh "$package")
printf '%s\n' "$verify_output"
actual_stem=$(sed -n 's/^ARTIFACT_STEM=//p' <<<"$verify_output")
package_sha=$(sed -n 's/^PACKAGE_SHA256=//p' <<<"$verify_output")
bit_sha=$(sed -n 's/^BIT_SHA256=//p' <<<"$verify_output")

[[ "$actual_stem" =~ ^[A-Za-z0-9_-]+$ ]] || {
  echo "FAIL: unsafe artifact stem: $actual_stem" >&2
  exit 1
}

package_name=$(basename "$package")
[[ "$package_name" =~ ^[A-Za-z0-9_.-]+$ ]] || {
  echo "FAIL: unsafe package filename: $package_name" >&2
  exit 1
}

load_dry_run=$(ssh -o BatchMode=yes "$ssh_host" \
  "cd $remote_zynq_dir && make -n load_bitstream BOARDNAME=pynqz2 VIVADO_VERSION=2024.2 VIVADO_MODE=batch")
load_bit=$(sed -n 's/.*Overlay("\([A-Za-z0-9_-]*\.bit\)").*/\1/p' <<<"$load_dry_run" | head -n 1)
[[ -n "$load_bit" ]] || {
  echo "FAIL: could not determine overlay filename from board Makefile" >&2
  exit 1
}
load_stem=${load_bit%.bit}

scp -o BatchMode=yes -- "$package" "$ssh_host:$remote_example_dir/$package_name"
for nbf in "$@"; do
  nbf_name=$(basename "$nbf")
  [[ "$nbf_name" =~ ^[A-Za-z0-9_.-]+\.nbf$ ]] || {
    echo "FAIL: unsafe NBF filename: $nbf_name" >&2
    exit 1
  }
  scp -o BatchMode=yes -- "$nbf" "$ssh_host:$remote_zynq_dir/$nbf_name"
done

remote_package_sha=$(ssh -o BatchMode=yes "$ssh_host" \
  "cd $remote_example_dir && sha256sum $package_name" | awk '{print $1}')
[[ "$remote_package_sha" == "$package_sha" ]] || {
  echo "FAIL: remote package SHA mismatch" >&2
  exit 1
}

ssh -o BatchMode=yes "$ssh_host" \
  "cd $remote_zynq_dir && base64 -d ../$package_name | tar xvJ"

if [[ "$load_stem" != "$actual_stem" ]]; then
  for extension in bit hwh map; do
    ssh -o BatchMode=yes "$ssh_host" \
      "cd $remote_zynq_dir && cp $actual_stem.$extension $load_stem.$extension"
  done
fi

remote_bit_sha=$(ssh -o BatchMode=yes "$ssh_host" \
  "cd $remote_zynq_dir && sha256sum $load_stem.bit" | awk '{print $1}')
[[ "$remote_bit_sha" == "$bit_sha" ]] || {
  echo "FAIL: board load-target bitstream SHA mismatch" >&2
  exit 1
}

for nbf in "$@"; do
  nbf_name=$(basename "$nbf")
  local_sha=$(sha256sum "$nbf" | awk '{print $1}')
  remote_sha=$(ssh -o BatchMode=yes "$ssh_host" \
    "cd $remote_zynq_dir && sha256sum $nbf_name" | awk '{print $1}')
  [[ "$local_sha" == "$remote_sha" ]] || {
    echo "FAIL: remote NBF SHA mismatch for $nbf_name" >&2
    exit 1
  }
  echo "NBF_OK=$nbf_name:$local_sha"
done

echo "LOAD_STEM=$load_stem"
echo "BOARD_BIT_SHA256=$remote_bit_sha"
echo "STAGE_OK=1"
