#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "usage: sudo $0" >&2
  exit 2
}
[[ $# -eq 0 ]] || {
  echo "usage: sudo $0" >&2
  exit 2
}

helper=/usr/local/sbin/load-blackparrot-overlay
sudoers=/etc/sudoers.d/blackparrot-overlay
helper_tmp=$(mktemp /usr/local/sbin/.load-blackparrot-overlay.XXXXXX)
sudoers_tmp=$(mktemp /etc/sudoers.d/.blackparrot-overlay.XXXXXX)

cleanup() {
  rm -f "$helper_tmp" "$sudoers_tmp"
}
trap cleanup EXIT

cat >"$helper_tmp" <<'EOF'
#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  echo "usage: sudo -n /usr/local/sbin/load-blackparrot-overlay" >&2
  exit 2
fi

zynq_dir=/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq
overlay=$zynq_dir/blackparrot_bd_1.bit
hwh=$zynq_dir/blackparrot_bd_1.hwh
pynq_path=/home/xilinx/zynq-parrot/cosim/py

[ -s "$overlay" ] || { echo "FAIL: missing overlay: $overlay" >&2; exit 1; }
[ -s "$hwh" ] || { echo "FAIL: missing handoff: $hwh" >&2; exit 1; }

bit_sha=$(/usr/bin/sha256sum "$overlay" | /usr/bin/awk '{print $1}')
echo "LOADING_BIT_SHA256=$bit_sha"
/usr/bin/env PYTHONPATH="$pynq_path" /usr/bin/python3 -c \
  'from pynq import PL, Overlay; PL.reset(); Overlay("/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/blackparrot_bd_1.bit")'
echo "OVERLAY_LOAD_OK=1"
EOF

cat >"$sudoers_tmp" <<'EOF'
xilinx ALL=(root) NOPASSWD: /usr/local/sbin/load-blackparrot-overlay
EOF

chown root:root "$helper_tmp" "$sudoers_tmp"
chmod 0755 "$helper_tmp"
chmod 0440 "$sudoers_tmp"
/usr/sbin/visudo -cf "$sudoers_tmp"

mv -f "$helper_tmp" "$helper"
mv -f "$sudoers_tmp" "$sudoers"
/usr/sbin/visudo -cf /etc/sudoers

echo "INSTALLED_HELPER=$helper"
echo "INSTALLED_SUDOERS=$sudoers"
echo "INSTALL_OK=1"
