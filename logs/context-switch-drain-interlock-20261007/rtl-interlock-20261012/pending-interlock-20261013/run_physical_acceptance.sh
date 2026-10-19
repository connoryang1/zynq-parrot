#!/usr/bin/env bash
# Run the exact physical acceptance ladder for the pending first-target
# interlock. Every target receives a fresh overlay and all source, runner,
# program, package, and bitstream hashes are retained beside raw transcripts.
set -euo pipefail

[[ $# -eq 2 ]] || {
  echo "usage: $0 <package.tar.xz.b64> <output-directory>" >&2
  exit 2
}

package=$(realpath "$1")
output=$(realpath -m "$2")
repo=$(git rev-parse --show-toplevel)
job_dir=$(dirname "$package")
ssh_host=xilinx@192.168.4.35
remote_dir=/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq
runner_sha=2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30
k10=$repo/logs/context-switch-drain-interlock-20261007/stack-slot-diagnostics/context4-sim-120-124/steps124/only4-steps124.nbf
k2=$repo/logs/context-switch-drain-interlock-20261007/stack-slot-diagnostics/post-switch-bubble/fast-k2-control/original-k2.nbf
k10_sha=cfa9ededb6cc73c65acb0d7b5cc61100031e08908237db5af0c9c44f912cc7df
k2_sha=92b0bdbe635486053a23ca9fc86074678a8f28b11e07626d43a23a11af6a5b0c

[[ "$(sha256sum "$k10" | awk '{print $1}')" == "$k10_sha" ]]
[[ "$(sha256sum "$k2" | awk '{print $1}')" == "$k2_sha" ]]
[[ -s "$job_dir/revisions.txt" ]]
source_top=$(sed -n 's/^top_commit=//p' "$job_dir/revisions.txt")
source_bp=$(sed -n 's/^black_parrot_commit=//p' "$job_dir/revisions.txt")
[[ "$source_top" =~ ^[0-9a-f]{40}$ && "$source_bp" =~ ^[0-9a-f]{40}$ ]]
mkdir -p "$output"

cat > "$output/README.md" <<'EOF'
This directory records the exact physical acceptance ladder for the pending first-target context-switch interlock. It uses a fresh overlay for every run and retains hash-pinned raw guest transcripts so host cleanup cannot mask a guest failure.

# Pending interlock physical acceptance

Acceptance requires the formerly failing exact ten-stream image to reach its workload marker and `CORE PASS` twice, followed by the exact two-stream control reaching the same markers with its measured cycle count.
EOF

verify=$($repo/codex-skills/bp-fpga-synthesis/scripts/verify_pynq_package.sh "$package")
printf '%s\n' "$verify" > "$output/package-verification.log"
package_sha=$(sed -n 's/^PACKAGE_SHA256=//p' <<<"$verify")
bit_sha=$(sed -n 's/^BIT_SHA256=//p' <<<"$verify")
[[ "$package_sha" =~ ^[0-9a-f]{64}$ && "$bit_sha" =~ ^[0-9a-f]{64}$ ]]

if ! grep -qx 'STAGE_OK=1' "$output/stage.log" 2>/dev/null \
   || ! grep -qx "BOARD_BIT_SHA256=$bit_sha" "$output/stage.log" 2>/dev/null \
   || ! grep -qx "NBF_OK=only4-steps124.nbf:$k10_sha" "$output/stage.log" 2>/dev/null \
   || ! grep -qx "NBF_OK=original-k2.nbf:$k2_sha" "$output/stage.log" 2>/dev/null; then
  $repo/codex-skills/bp-fpga-synthesis/scripts/stage_pynq_artifacts.sh \
    "$package" "$ssh_host" "$k10" "$k2" > "$output/stage.log" 2>&1
fi
grep -qx 'STAGE_OK=1' "$output/stage.log"
grep -qx "BOARD_BIT_SHA256=$bit_sha" "$output/stage.log"
grep -qx "NBF_OK=only4-steps124.nbf:$k10_sha" "$output/stage.log"
grep -qx "NBF_OK=original-k2.nbf:$k2_sha" "$output/stage.log"

printf 'label\tnbf_sha256\tclassification\tcycles\tlog_sha256\n' > "$output/results.tsv"
overall=0
for spec in \
  00-original-k10-a:only4-steps124.nbf:$k10_sha \
  01-original-k10-b:only4-steps124.nbf:$k10_sha \
  02-original-k2:original-k2.nbf:$k2_sha; do
  IFS=: read -r label image expected_sha <<<"$spec"
  overlay_log=$output/$label-overlay.log
  target_log=$output/$label.log

  loaded=0
  for attempt in 1 2 3 4 5; do
    if $repo/codex-skills/bp-fpga-synthesis/scripts/load_pynq_overlay.sh \
         "$ssh_host" > "$overlay_log" 2>&1 \
       && grep -qx 'REMOTE_FPGA_STATE=operating' "$overlay_log" \
       && grep -qx "LOADING_BIT_SHA256=$bit_sha" "$overlay_log"; then
      loaded=1
      break
    fi
    sleep 2
  done
  if (( ! loaded )); then
    echo "overlay load failed for $label" >&2
    exit 1
  fi

  set +e
  ssh -tt -o BatchMode=yes -o ConnectTimeout=8 "$ssh_host" \
    "$remote_dir/run-blackparrot-interactive" \
    "$image" "$expected_sha" "$runner_sha" 30000 > "$target_log" 2>&1
  target_rc=$?
  set -e

  classification=unknown
  if grep -Eqi 'CORE(\[[0-9]+\])?[[:space:]]+FAIL|BSG[- ]FAIL' "$target_log"; then
    classification=fail
  elif grep -Eq '\[BSG-PASS\] dependent streams, checksums and completion' "$target_log" \
       && grep -Eq 'CORE(\[[0-9]+\])?[[:space:]]+PASS' "$target_log" \
       && grep -Eq '\bBSG PASS\b' "$target_log"; then
    classification=pass
  elif (( target_rc == 124 )) || grep -Eqi 'runtime limit|timed out|timeout' "$target_log"; then
    classification=timeout
  fi

  cycles_hex=$(sed -n 's/.*cycles=0x\([0-9a-fA-F]*\).*/\1/p' "$target_log" | head -n1)
  cycles=
  if [[ -n "$cycles_hex" ]]; then
    cycles=$(python3 -c 'import sys; print(int(sys.argv[1], 16))' "$cycles_hex")
  fi
  log_sha=$(sha256sum "$target_log" | awk '{print $1}')
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$label" "$expected_sha" "$classification" "$cycles" "$log_sha" \
    >> "$output/results.tsv"
  [[ "$classification" == pass ]] || overall=1
done

cat > "$output/identities.txt" <<EOF
top_commit=$source_top
black_parrot_commit=$source_bp
package_sha256=$package_sha
bitstream_sha256=$bit_sha
control_program_sha256=$runner_sha
k10_nbf_sha256=$k10_sha
k2_nbf_sha256=$k2_sha
fresh_overlay_before_every_run=true
EOF

exit "$overall"
