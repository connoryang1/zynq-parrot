#!/usr/bin/env bash
# Equal-area crossover sweep (native RTL sim, bare metal, delay 160):
# retention design (1536+1536 lines, 16 KiB L2) vs equal-area baseline
# (no retained lines, 128 KiB L2), across background footprints.
# The first case of each design builds the model; the rest run in parallel.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/retained_fgbg_ijoint_benchmark.c
export SRC BUILD_JOBS=4
# bg data KiB : bg code KiB
BGS=("16:8" "64:48" "256:48")
run_design() {  # name I D L2
  local name=$1; export I_LINES=$2 D_LINES=$3 L2_SETS=$4
  local first=1
  for bg in "${BGS[@]}"; do
    local d=${bg%:*} c=${bg#*:}
    local label=xo-$name-bg$d-c$c
    if (( first )); then
      bash "$HERE/run_native_src.sh" "$label" 160 256 -DFG_KIB=12 -DFG_CODE_KIB=12 -DBG_KIB=$d -DBG_CODE_KIB=$c > "$HERE/$label.out" 2>&1 &
      local p=$!
      # wait for the model to exist before starting the others
      until [[ -x /run/user/1001/zp-retained-fgbg-model-d160-s256-i$2-d$3-l2s$4/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench ]] || ! kill -0 $p 2>/dev/null; do sleep 20; done
      first=0
    else
      bash "$HERE/run_native_src.sh" "$label" 160 256 -DFG_KIB=12 -DFG_CODE_KIB=12 -DBG_KIB=$d -DBG_CODE_KIB=$c > "$HERE/$label.out" 2>&1 &
    fi
  done
  wait
}
run_design ret 1536 1536 64
run_design iso 0 0 512
grep -H "mode=" "$HERE"/xo-*.out
