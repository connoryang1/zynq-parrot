#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(git -C "$script_dir" rev-parse --show-toplevel)
subsystems="$repo_dir/import/black-parrot-subsystems"
opentitan="$subsystems/import/opentitan"
python_dir="$repo_dir/install/python"
output_dir="$repo_dir/install/gen/v/rv_plic"

if ! PYTHONPATH="$python_dir" python3 -c \
  'import hjson, importlib_resources, mako, semantic_version; from Crypto.Cipher import AES'; then
  python3 -m pip install --disable-pip-version-check --target "$python_dir" \
    hjson==3.1.0 importlib-resources==5.13.0 mako==1.1.6 \
    semantic-version==2.10.0 pycryptodome==3.23.0
fi

work_dir=$(mktemp -d /tmp/zynq-parrot-plic.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT

git -C "$opentitan" archive HEAD | tar -x -C "$work_dir"
while IFS= read -r patch_file; do
  patch -d "$work_dir" -p1 <"$patch_file"
done < <(find "$subsystems/patches/import/opentitan" -name '*.patch' -print | sort)

PYTHONPATH="$python_dir" python3 "$work_dir/util/ipgen.py" generate \
  -c "$subsystems/zynq/cfg/rv_plic.ipconfig.hjson" \
  -C "$work_dir/hw/ip_templates/rv_plic" \
  -o "$work_dir/generated"

mkdir -p "$(dirname "$output_dir")"
if [[ -e "$output_dir" ]]; then
  mv "$output_dir" "$work_dir/previous"
fi
mv "$work_dir/generated" "$output_dir"

for required in rv_plic.sv rv_plic_gateway.sv rv_plic_reg_pkg.sv rv_plic_target.sv; do
  test -s "$output_dir/rtl/$required"
done
echo "Generated OpenTitan PLIC RTL in $output_dir"
