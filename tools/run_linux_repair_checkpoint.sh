#!/usr/bin/env bash
# Stage, reload, and run one immutable FPGA checkpoint from the late Linux
# repair stack.  This is intentionally one checkpoint per invocation: Linux
# runs share the PYNQ PL/DRAM control path and must never overlap.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: tools/run_linux_repair_checkpoint.sh <checkpoint> [ssh-host]

Checkpoints are ordered oldest to newest.  They all contain the completed
SRAM-backed context-switch implementation; each adds a prefix of the late
Linux-compatibility repair stack:
  19aa  19aa50ad  no late repair
  332   332f47a7  I-cache refill arbitration repair
  b5ef  b5ef69f0  normal resume repair
  453   453185ec  DTLB replay + context CSR seed repairs
  51bb  51bbb0e8  SATP-mode filter repair
  current 1c42e9f2 complete current repair stack

The script refuses to change board files while a control-program runner is
active, records package/NBF/bit identities, then uses the scoped overlay and
serialized-run helpers.  A Linux result is valid only when its retained
transcript reaches /init and CORE[0] PASS.

The current package is supplied through LINUX_REPAIR_CURRENT_PACKAGE when it
has not yet been promoted into logs/fpga/.
EOF
}

[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }

checkpoint=$1
ssh_host=${2:-xilinx@192.168.4.35}
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
stage_helper="$root/codex-skills/bp-fpga-synthesis/scripts/stage_pynq_artifacts.sh"
load_helper="$root/codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh"
run_helper="$root/codex-skills/bp-fpga-synthesis/scripts/run_pynq_serial.sh"
linux_nbf="$root/riscv/linux/linux-6.6-jhumphri-20250125.nbf"
current_package=${LINUX_REPAIR_CURRENT_PACKAGE:-}

case "$checkpoint" in
  19aa|19aa50ad)
    revision=19aa50ad
    package="$root/logs/fpga/20260831T095954Z-a5ce9ec/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64"
    ;;
  332|332f47a7)
    revision=332f47a7
    package="$root/logs/fpga/20260831T111442Z-afe59e5/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64"
    ;;
  b5ef|b5ef69f0)
    revision=b5ef69f0
    package="$root/logs/fpga/20260831T132559Z-8ccfbd5/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64"
    ;;
  453|453185ec)
    revision=453185ec
    package="$root/logs/fpga/20260831T205319Z-a534aed/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64"
    ;;
  51bb|51bbb0e8)
    revision=51bbb0e8
    package="$root/logs/fpga/20260901T020240Z-0514bbe/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64"
    ;;
  current|1c42|1c42e9f2)
    revision=1c42e9f2
    package=$current_package
    ;;
  *)
    usage
    exit 2
    ;;
esac

[[ -x "$stage_helper" && -x "$load_helper" && -x "$run_helper" ]] || {
  echo "FAIL: required PYNQ helper is unavailable" >&2
  exit 1
}
[[ -n "$package" && -f "$package" && -s "$package" ]] || {
  [[ "$revision" == 1c42e9f2 ]] && \
    echo "HINT: set LINUX_REPAIR_CURRENT_PACKAGE to the immutable current routed package" >&2
  echo "FAIL: missing routed package for $revision: $package" >&2
  exit 1
}
[[ -f "$linux_nbf" && -s "$linux_nbf" ]] || {
  echo "FAIL: missing maintained Linux NBF: $linux_nbf" >&2
  exit 1
}

# Avoid even staging a package while a target can be executing.  The run
# helper repeats this stronger check at launch to close the staging-to-run race.
if ssh -o BatchMode=yes "$ssh_host" \
    "pgrep -x control-program >/dev/null || pgrep -f '[s]cript .*control-program' >/dev/null"; then
  echo "ACTIVE_RUNNER: board still has a control-program process; no files changed" >&2
  exit 75
fi

run_dir="$root/logs/pynq-validation/repair-stack-bisect/$(date -u +%Y%m%dT%H%M%SZ)-$revision"
mkdir -p "$run_dir"
{
  echo "checkpoint=$checkpoint"
  echo "black_parrot_commit=$revision"
  echo "package=$package"
  sha256sum "$package"
  echo "linux_nbf=$linux_nbf"
  sha256sum "$linux_nbf"
  git -C "$root" rev-parse HEAD
} | tee "$run_dir/identity.txt"

"$stage_helper" "$package" "$ssh_host" "$linux_nbf" | tee "$run_dir/stage.log"
"$load_helper" "$ssh_host" | tee "$run_dir/load.log"

set +e
"$run_helper" "$ssh_host" "$(basename "$linux_nbf")" | tee "$run_dir/board.log"
run_rc=${PIPESTATUS[0]}
set -e

if grep -q 'Run /init as init process' "$run_dir/board.log" \
  && grep -q 'CORE\[0\] PASS' "$run_dir/board.log"; then
  echo "LINUX_BOOT_RESULT=PASS" | tee "$run_dir/result.txt"
  exit 0
fi

echo "LINUX_BOOT_RESULT=NO_INIT_OR_NO_PASS run_rc=$run_rc" | tee "$run_dir/result.txt"
exit 1
