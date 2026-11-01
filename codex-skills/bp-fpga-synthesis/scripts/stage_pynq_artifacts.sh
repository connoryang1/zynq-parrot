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

assert_no_active_runner() {
  if ! ssh -o BatchMode=yes "$ssh_host" \
    'test ! -d "$HOME/bp-logs/.control-program.lock" && ! pgrep -x control-program >/dev/null && ! pgrep -f "[s]cript .*control-program" >/dev/null'; then
    echo "FAIL: refusing to replace FPGA artifacts while a runner owns the board" >&2
    return 75
  fi
}

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

assert_no_active_runner || exit $?

# A runner can read an NBF as soon as it appears at its final name. Transfer
# every artifact to a private temporary name first; one remote transaction
# below acquires the shared board lock before installing any of them.
incoming_paths=()
last_remote_tmp=
transfer_temporary() {
  local source=$1
  local remote_dir=$2
  local final_name=$3
  local local_sha remote_sha remote_tmp

  local_sha=$(sha256sum "$source" | awk '{print $1}')
  remote_tmp=".${final_name}.incoming-$$"
  incoming_paths+=("$remote_dir/$remote_tmp")
  scp -o BatchMode=yes -- "$source" "$ssh_host:$remote_dir/$remote_tmp"
  remote_sha=$(ssh -o BatchMode=yes "$ssh_host" \
    "cd $remote_dir && sha256sum $remote_tmp" | awk '{print $1}')
  if [[ "$remote_sha" != "$local_sha" ]]; then
    ssh -o BatchMode=yes "$ssh_host" "cd $remote_dir && rm -f $remote_tmp" || true
    echo "FAIL: temporary remote SHA mismatch for $final_name" >&2
    exit 1
  fi
  last_remote_tmp=$remote_tmp
}

cleanup_incoming() {
  ((${#incoming_paths[@]} == 0)) && return
  ssh -o BatchMode=yes "$ssh_host" bash -s -- "${incoming_paths[@]}" <<'REMOTE' >/dev/null 2>&1 || true
set -euo pipefail
for path; do
  path=${path/#\~/$HOME}
  rm -f -- "$path"
done
REMOTE
}
trap cleanup_incoming EXIT HUP INT TERM

transfer_temporary "$package" "$remote_example_dir" "$package_name"
package_tmp=$last_remote_tmp
nbf_args=()
for nbf in "$@"; do
  nbf_name=$(basename "$nbf")
  [[ "$nbf_name" =~ ^[A-Za-z0-9_.-]+\.nbf$ ]] || {
    echo "FAIL: unsafe NBF filename: $nbf_name" >&2
    exit 1
  }
  nbf_sha=$(sha256sum "$nbf" | awk '{print $1}')
  transfer_temporary "$nbf" "$remote_zynq_dir" "$nbf_name"
  nbf_tmp=$last_remote_tmp
  nbf_args+=("$nbf_tmp" "$nbf_name" "$nbf_sha")
done

commit_output=$(ssh -o BatchMode=yes "$ssh_host" bash -s -- \
  "$remote_example_dir" "$remote_zynq_dir" "$package_tmp" "$package_name" \
  "$package_sha" "$actual_stem" "$load_stem" "$bit_sha" "${nbf_args[@]}" <<'REMOTE'
set -euo pipefail
remote_example_dir=$1
remote_zynq_dir=$2
package_tmp=$3
package_name=$4
package_sha=$5
actual_stem=$6
load_stem=$7
bit_sha=$8
shift 8
remote_example_dir=${remote_example_dir/#\~/$HOME}
remote_zynq_dir=${remote_zynq_dir/#\~/$HOME}
mkdir -p "$HOME/bp-logs"
lock="$HOME/bp-logs/.control-program.lock"
if [[ -d "$lock" ]]; then
  owner=$(cat "$lock/owner" 2>/dev/null || true)
  if [[ "$owner" =~ ^[0-9]+$ ]] && kill -0 "$owner" 2>/dev/null; then
    echo ACTIVE_RUNNER
    exit 75
  fi
  if pgrep -x control-program >/dev/null \
     || pgrep -f '[s]cript .*control-program' >/dev/null; then
    echo ACTIVE_RUNNER
    exit 75
  fi
  rm -f "$lock/owner"
  rmdir "$lock" || { echo ACTIVE_RUNNER; exit 75; }
fi
if pgrep -x control-program >/dev/null \
   || pgrep -f '[s]cript .*control-program' >/dev/null; then
  echo ACTIVE_RUNNER
  exit 75
fi
mkdir "$lock" || { echo ACTIVE_RUNNER; exit 75; }
printf '%s\n' "$$" > "$lock/owner"
cleanup() { rm -f "$lock/owner"; rmdir "$lock" 2>/dev/null || true; }
trap cleanup EXIT HUP INT TERM

cd "$remote_example_dir"
[[ $(sha256sum "$package_tmp" | awk '{print $1}') == "$package_sha" ]]
mv -f "$package_tmp" "$package_name"

cd "$remote_zynq_dir"
while (($#)); do
  nbf_tmp=$1
  nbf_name=$2
  nbf_sha=$3
  shift 3
  [[ $(sha256sum "$nbf_tmp" | awk '{print $1}') == "$nbf_sha" ]]
  mv -f "$nbf_tmp" "$nbf_name"
  echo "NBF_OK=$nbf_name:$nbf_sha"
done

base64 -d "../$package_name" | tar xvJ
if [[ "$load_stem" != "$actual_stem" ]]; then
  for extension in bit hwh map; do
    cp "$actual_stem.$extension" "$load_stem.$extension"
  done
fi
remote_bit_sha=$(sha256sum "$load_stem.bit" | awk '{print $1}')
[[ "$remote_bit_sha" == "$bit_sha" ]] || {
  echo "FAIL: board load-target bitstream SHA mismatch" >&2
  exit 1
}
echo "BOARD_BIT_SHA256=$remote_bit_sha"
echo "STAGE_COMMIT_OK=1"
REMOTE
)
printf '%s\n' "$commit_output"
grep -qx 'STAGE_COMMIT_OK=1' <<<"$commit_output" || {
  echo "FAIL: board did not commit staged artifacts" >&2
  exit 1
}
remote_bit_sha=$(sed -n 's/^BOARD_BIT_SHA256=//p' <<<"$commit_output")
incoming_paths=()
trap - EXIT HUP INT TERM

echo "LOAD_STEM=$load_stem"
echo "STAGE_OK=1"
