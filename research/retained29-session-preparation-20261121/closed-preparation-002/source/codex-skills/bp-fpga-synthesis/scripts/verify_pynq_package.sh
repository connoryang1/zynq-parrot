#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <packed-bitstream.tar.xz.b64> [expected-bit-sha256]" >&2
  exit 2
}

[[ $# -ge 1 && $# -le 2 ]] || usage
package=$1
expected_sha=${2:-}
[[ -f "$package" ]] || { echo "FAIL: package not found: $package" >&2; exit 1; }

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
base64 -d "$package" | tar -xJf - -C "$work_dir"

mapfile -t bits < <(find "$work_dir" -maxdepth 1 -type f -name '*.bit' -printf '%f\n' | sort)
[[ ${#bits[@]} -eq 1 ]] || {
  echo "FAIL: expected exactly one .bit file, found ${#bits[@]}" >&2
  exit 1
}

stem=${bits[0]%.bit}
for suffix in bit hwh map; do
  [[ -s "$work_dir/$stem.$suffix" ]] || {
    echo "FAIL: missing or empty $stem.$suffix" >&2
    exit 1
  }
done

bit_sha=$(sha256sum "$work_dir/$stem.bit" | awk '{print $1}')
package_sha=$(sha256sum "$package" | awk '{print $1}')
if [[ -n "$expected_sha" && "$bit_sha" != "$expected_sha" ]]; then
  echo "FAIL: bitstream SHA mismatch" >&2
  echo "expected: $expected_sha" >&2
  echo "actual:   $bit_sha" >&2
  exit 1
fi

printf 'PACKAGE_OK=1\n'
printf 'PACKAGE=%s\n' "$(realpath "$package")"
printf 'PACKAGE_SHA256=%s\n' "$package_sha"
printf 'ARTIFACT_STEM=%s\n' "$stem"
printf 'BIT_SHA256=%s\n' "$bit_sha"
printf 'MEMBERS=%s.bit,%s.hwh,%s.map\n' "$stem" "$stem" "$stem"
