#!/bin/bash
# fix14: detached replay replies may not replace an ordinary-FSM data-port
# packet (lost victim read -> stale write-back). Uncapped fix13 matrix, plus
# cap 8 (with the display-only data trace) including the failing h-t0-m4.
cd "$(dirname "$0")"
ulimit -f 409600
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
export BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24
matrix() { # $1 prefix
  SRC=$P bash run_native_src.sh $1-pp-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > $1-pp-m2.out 2>&1 &
  sleep 5
  SRC=$P bash run_native_src.sh $1-pp-m4 160 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > $1-pp-m4.out 2>&1 &
  for c in "0 2" "0 4" "3 2" "3 4"; do set -- $c
    SRC=$H bash run_native_src.sh $PFX-h-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > $PFX-h-t$1-m$2.out 2>&1 &
    sleep 5; done
  wait; }
build_then() { # $1 prefix ; builds via the failing-case run first
  PFX=$1
  SRC=$H bash run_native_src.sh $1-h-t0-m4 160 256 -DTRIG=0 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > $1-h-t0-m4.out 2>&1 &
  sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" $1-h-t0-m4.out; do sleep 20; done
  grep -q "BUILD FAILED" $1-h-t0-m4.out && { echo "$1 BUILD_FAILED"; exit 1; }
  sleep 20
  SRC=$P bash run_native_src.sh $1-pp-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > $1-pp-m2.out 2>&1 &
  SRC=$P bash run_native_src.sh $1-pp-m4 160 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > $1-pp-m4.out 2>&1 &
  for c in "0 2" "3 2" "3 4"; do set -- $c
    SRC=$H bash run_native_src.sh $PFX-h-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > $PFX-h-t$1-m$2.out 2>&1 &
    sleep 5; done
  wait; }
( export DBG_DEFINES=BP_REPLAY_STATS MODEL_ROOT=/home/coyang/sim-models/fix14; BUILD_JOBS=5 build_then f14 ) &
sleep 30
( export CAP=8 DBG_DEFINES="BP_REPLAY_STATS BP_REPLAY_DATA_TRACE BP_DT_W0=33556936 BP_DT_W1=33555842" MODEL_ROOT=/home/coyang/sim-models/fix14-c8; BUILD_JOBS=5 build_then f14c8 ) &
wait; echo ALL_DONE
