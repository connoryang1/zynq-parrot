#!/bin/bash
# Demand-cap sweep on the fix13 RTL: while either cache has a demand miss
# outstanding, replay may keep at most CAP requests in flight (24 = no cap,
# from run_fix13).
cd "$(dirname "$0")"
ulimit -f 409600
H=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_hybrid_benchmark.c
P=/home/coyang/zynq-parrot-retained-preserve-20261124/testing/rtl/replay_pingpong_benchmark.c
B="BUFFER=0 PF_FULL=1 RINST=1 DRE=256 I_LINES=0 D_LINES=0 L2_SETS=64 HOLD=1 IBYP=1 PF_ELS=24 PF_OUT=24 IPF_ELS=24 DBG_DEFINES=BP_REPLAY_STATS"
for cap in 4 8 16; do
  ( export $B CAP=$cap MODEL_ROOT=/home/coyang/sim-models/cap13-c$cap
    BUILD_JOBS=4 SRC=$P bash run_native_src.sh c13-$cap-pp-m2 160 256 -DMODES=2 -DROUNDS=4 -DWARMUP=1 > c13-$cap-pp-m2.out 2>&1 &
    sleep 5; until ls $MODEL_ROOT/*/design/verilator/obj_dir/Vbsg_nonsynth_zynq_testbench >/dev/null 2>&1 || grep -q "BUILD FAILED" c13-$cap-pp-m2.out; do sleep 20; done
    grep -q "BUILD FAILED" c13-$cap-pp-m2.out && { echo "CAP $cap BUILD_FAILED"; exit 1; }
    sleep 20
    SRC=$P bash run_native_src.sh c13-$cap-pp-m4 160 256 -DMODES=4 -DROUNDS=4 -DWARMUP=1 > c13-$cap-pp-m4.out 2>&1 &
    for c in "0 2" "0 4" "3 2" "3 4"; do set -- $c
      SRC=$H bash run_native_src.sh c13-$cap-h-t$1-m$2 160 256 -DTRIG=$1 -DMODES=$2 -DROUNDS=4 -DWARMUP=1 > c13-$cap-h-t$1-m$2.out 2>&1 &
      sleep 5; done
    wait ) &
  sleep 30
done
wait; echo ALL_DONE
