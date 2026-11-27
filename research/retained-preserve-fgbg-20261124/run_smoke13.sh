#!/bin/bash
# (1) Reproducibility rerun of the cap-8 early/TRIG0 failure on the cap13-c8 model.
# (2) Clean rebuild of the committed (debug-stripped) BP tree, no cap: smoke runs.
cd "$(dirname "$0")"
ulimit -f 409600
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
B="BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24"
( export $B CAP=8 DBG_DEFINES=BP_REPLAY_STATS MODEL_ROOT=/home/coyang/sim-models/cap13-c8
  SRC=$H bash run_native_src.sh c13-8-h-t0-m4-r2 160 256 -DTRIG=0 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > c13-8-h-t0-m4-r2.out 2>&1 ) &
( export $B MODEL_ROOT=/home/coyang/sim-models/commit-smoke
  BUILD_JOBS=8 SRC=$H bash run_native_src.sh cs-h-t3-m4 160 256 -DTRIG=3 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > cs-h-t3-m4.out 2>&1 &
  sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" cs-h-t3-m4.out; do sleep 20; done
  grep -q "BUILD FAILED" cs-h-t3-m4.out && { echo "SMOKE BUILD_FAILED"; exit 1; }
  sleep 20
  SRC=$P bash run_native_src.sh cs-pp-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > cs-pp-m2.out 2>&1 &
  SRC=$H bash run_native_src.sh cs-h-t0-m2 160 256 -DTRIG=0 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > cs-h-t0-m2.out 2>&1 &
  wait ) &
wait; echo ALL_DONE
