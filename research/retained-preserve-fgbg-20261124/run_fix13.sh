#!/bin/bash
# Fix13: I-cache freezes IF2 under the install lock (no IF2 consumption with
# IF1 empty); drain no longer waits for an empty pipeline. Validate on the
# full 24-in-flight matrix (incl. the earlier bg-tail failure h10-t3-m2).
cd "$(dirname "$0")"
ulimit -f 1048576
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
B="BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1"
export DBG_DEFINES="BP_REPLAY_STATS BP_ICACHE_INSTALL_DEBUG"
env $B PF_ELS=8 PF_OUT=8 IPF_ELS=8 MODEL_ROOT=/home/coyang/sim-models/fix13-pf8 BUILD_JOBS=5 SRC=$H \
  bash run_native_src.sh f13-pf8-t3-m2 160 256 -DTRIG=3 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > f13-pf8-t3-m2.out 2>&1 &
export $B PF_ELS=24 PF_OUT=24 IPF_ELS=24 MODEL_ROOT=/home/coyang/sim-models/replay-fix13
BUILD_JOBS=6 SRC=$P bash run_native_src.sh pp13-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > pp13-m2.out 2>&1 &
sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" pp13-m2.out; do sleep 20; done
grep -q "BUILD FAILED" pp13-m2.out && { echo BUILD_FAILED; wait; exit 1; }
sleep 20
SRC=$P bash run_native_src.sh pp13-m4 160 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > pp13-m4.out 2>&1 &
for c in "3 2" "0 2" "3 4" "0 4" "1 2" "2 2"; do set -- $c
  SRC=$H bash run_native_src.sh h13-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > h13-t$1-m$2.out 2>&1 &
  sleep 5; done
wait; echo ALL_DONE
